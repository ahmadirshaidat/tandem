"""Postgres queue; locks serialize admission and claims without holding DB during LLM IO."""

import asyncio
import logging
import re
import time
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.agent.audit import audit
from app.agent.llm import FakeLLM, WorkspaceLLM
from app.agent.models import AgentRun
from app.agent.service import (
    allowed_channels,
    channel_enabled,
    configuration,
    run_access,
    run_out,
    usage,
)
from app.agent.tools import descriptors, execute
from app.ai.providers import ProviderFailure, provider_model
from app.channels.models import Channel, Message, MessageMention
from app.channels.service import message_out, record_event
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import Workspace, new_id
from app.core.security import now

FRIENDLY = {
    "agent_off": "The workspace agent is off. Ask an Owner or Admin to enable it in Agent settings.",
    "channel_not_allowed": "The agent is not enabled in this channel. Ask an Owner or Admin to allow it.",
    "rate_limited": "The agent is busy with recent requests. Wait a minute, then mention @Agent again.",
    "limit_reached": "The workspace's monthly agent limit has been reached. Ask an Owner or Admin to review the limit.",
    "timeout": "The agent took too long. Please mention @Agent again to retry.",
    "unavailable": "The agent's providers are unavailable. Please mention @Agent again to retry.",
    "access_changed": "The available context changed. Please mention @Agent again to retry.",
}


def run_event(db, run, kind):
    channel = db.get(Channel, run.channel_id)
    record_event(db, channel, kind, {"run": run_out(db, run)})


def post_answer(db, run, body):
    channel = db.get(Channel, run.channel_id)
    trigger = db.get(Message, run.trigger_message_id)
    message = Message(
        workspace_id=run.workspace_id,
        channel_id=channel.id,
        author_id=None,
        actor_type="agent",
        body=body[:4000],
        seq=channel.last_seq + 1,
        client_message_id=run.id,
        thread_root_id=trigger.thread_root_id,
    )
    db.add(message)
    db.flush()
    data = {"message": message_out(db, message), "run": run_out(db, run)}
    if message.thread_root_id:
        data["thread_root"] = message_out(db, db.get(Message, message.thread_root_id))
    record_event(db, channel, "agent.message_created", data)


def enqueue(db, channel, message, request_id):
    if message.actor_type != "user" or not db.scalar(
        select(MessageMention.id).where(
            MessageMention.message_id == message.id, MessageMention.is_agent.is_(True)
        )
    ):
        return None
    existing = db.scalar(select(AgentRun).where(AgentRun.trigger_message_id == message.id))
    if existing:
        return existing
    config = configuration(db, channel.workspace_id)
    category = None
    if not config.enabled:
        category = "agent_off"
    elif not channel_enabled(db, channel.workspace_id, channel):
        category = "channel_not_allowed"
    elif config.pause_at_limit and usage(db, channel.workspace_id) >= config.monthly_run_limit:
        category = "limit_reached"
    else:
        recent = select(AgentRun).where(
            AgentRun.workspace_id == channel.workspace_id,
            AgentRun.created_at >= now() - timedelta(minutes=1),
        )
        total = db.scalar(select(func.count()).select_from(recent.subquery()))
        user_total = db.scalar(
            select(func.count()).select_from(
                recent.where(AgentRun.requester_id == message.author_id).subquery()
            )
        )
        if (
            total >= settings.agent_workspace_runs_per_minute
            or user_total >= settings.agent_user_runs_per_minute
        ):
            category = "rate_limited"
    run = AgentRun(
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        trigger_message_id=message.id,
        requester_id=message.author_id,
        status="blocked" if category else "queued",
        error_category=category,
        request_id=request_id,
    )
    db.add(run)
    db.flush()
    audit(
        db,
        run.workspace_id,
        "user",
        run.requester_id,
        "agent.run_queued",
        "run",
        run.id,
        status=run.status,
        request_id=run.request_id,
    )
    if category:
        run.finished_at = now()
        audit(
            db,
            run.workspace_id,
            "agent",
            run.workspace_id,
            "agent.run_blocked",
            "run",
            run.id,
            status=category,
            request_id=run.request_id,
        )
        post_answer(db, run, FRIENDLY[category])
        run_event(db, run, "agent.run_failed")
    return run


def claim():
    with SessionLocal() as db:
        # Workspace lock is shared with membership changes, settings and enqueue.
        workspace = db.scalar(
            select(Workspace)
            .where(
                Workspace.id.in_(select(AgentRun.workspace_id).where(AgentRun.status == "queued")),
                Workspace.id.not_in(
                    select(AgentRun.workspace_id)
                    .where(AgentRun.status == "running")
                    .group_by(AgentRun.workspace_id)
                    .having(func.count() >= settings.agent_workspace_concurrency)
                ),
            )
            .order_by(Workspace.id)
            .with_for_update(skip_locked=True)
        )
        if not workspace:
            return None
        active = db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.workspace_id == workspace.id, AgentRun.status == "running")
        )
        if active >= settings.agent_workspace_concurrency:
            return None
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace.id, AgentRun.status == "queued")
            .order_by(AgentRun.created_at, AgentRun.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not run:
            return None
        run.status, run.started_at = "running", now()
        audit(
            db,
            run.workspace_id,
            "agent",
            run.workspace_id,
            "agent.run_started",
            "run",
            run.id,
            request_id=run.request_id,
        )
        run_event(db, run, "agent.run_started")
        db.commit()
        return run.id


def locked_run(db, rid):
    wid = db.scalar(select(AgentRun.workspace_id).where(AgentRun.id == rid))
    db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    return db.scalar(
        select(AgentRun)
        .where(AgentRun.id == rid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def guard(db, run):
    channel = run_access(db, run)
    config = configuration(db, run.workspace_id)
    if not config.enabled:
        raise ProviderFailure("agent_off")
    if not channel_enabled(db, run.workspace_id, channel):
        raise ProviderFailure("channel_not_allowed")
    trigger = db.get(Message, run.trigger_message_id)
    if trigger.deleted_at:
        raise ProviderFailure("access_changed")
    return config


def finish(rid, answer=None, category=None, fingerprint=None):
    with SessionLocal() as db:
        run = locked_run(db, rid)
        if not run or run.status != "running":
            return
        try:
            guard(db, run)
            if fingerprint is not None and fingerprint != {
                c.id
                for c in allowed_channels(db, run.workspace_id, run.requester_id, run.channel_id)
            }:
                raise ProviderFailure("access_changed")
        except HTTPException:
            category, answer = "access_changed", None
        except ProviderFailure as e:
            category, answer = e.category, FRIENDLY.get(e.category, FRIENDLY["unavailable"])
        run.status = "failed" if category else "completed"
        run.error_category, run.finished_at = category, now()
        run.latency_ms = round((run.finished_at - run.started_at).total_seconds() * 1000)
        audit(
            db,
            run.workspace_id,
            "agent",
            run.workspace_id,
            "agent.run_" + run.status,
            "run",
            run.id,
            status=category or "ok",
            arguments={
                "latency_ms": run.latency_ms,
                "provider": run.provider,
                "model": run.model,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
            },
            request_id=run.request_id,
        )
        if answer:
            post_answer(db, run, answer)
        if category:
            run_event(db, run, "agent.run_failed")
        db.commit()


async def orchestrate(rid, llm):
    tick = time.monotonic()
    with SessionLocal() as db:
        run = locked_run(db, rid)
        config = guard(db, run)
        prompt = db.get(Message, run.trigger_message_id).body
        chain = list(config.provider_chain)
        fingerprint = {
            c.id for c in allowed_channels(db, run.workspace_id, run.requester_id, run.channel_id)
        }
        # Deterministic refusal before a provider is contacted; tools cannot mutate in any case.
        if re.search(
            r"\b(create|delete|remove|assign|move|update|edit|change)\b.{0,60}\b(project|channel|member|document)s?\b",
            prompt,
            re.I,
        ):
            db.commit()
            finish(
                rid,
                "I cannot make changes yet. Use Tasks to create or edit tasks, or the channel controls to manage conversations manually.",
            )
            return
        payload = {"question": prompt, "tools": descriptors(), "results": []}
        db.commit()
    for provider_index, provider in enumerate(chain):
        try:
            for _ in range(4):
                remaining = settings.agent_run_timeout_seconds - (time.monotonic() - tick)
                if remaining <= 0:
                    raise TimeoutError
                with SessionLocal() as db:
                    run = locked_run(db, rid)
                    if run.status != "running":
                        return
                    current = guard(db, run)
                    if provider not in current.provider_chain or fingerprint != {
                        c.id
                        for c in allowed_channels(
                            db, run.workspace_id, run.requester_id, run.channel_id
                        )
                    }:
                        raise ProviderFailure("access_changed")
                    run.provider, run.model = provider, provider_model(provider)
                    db.commit()
                turn, completion = await asyncio.wait_for(
                    asyncio.to_thread(llm.turn, provider, payload),
                    timeout=min(remaining, settings.ai_provider_timeout_seconds + 1),
                )
                with SessionLocal() as db:
                    run = locked_run(db, rid)
                    if run.status != "running":
                        return
                    guard(db, run)
                    if fingerprint != {
                        c.id
                        for c in allowed_channels(
                            db, run.workspace_id, run.requester_id, run.channel_id
                        )
                    }:
                        raise ProviderFailure("access_changed")
                    run.input_tokens += completion.input_tokens or 0
                    run.output_tokens += completion.output_tokens or 0
                    if turn.calls:
                        for call in turn.calls:
                            result = execute(db, run, call.name, call.arguments)
                            payload["results"].append(result)
                            db.flush()
                            run_event(db, run, "agent.step")
                            # Stop on denial; never send denied arguments or provider answer onward.
                            if result["status"] != "ok":
                                db.commit()
                                finish(
                                    rid,
                                    "That tool or context is unavailable. I can only read permitted workspace content.",
                                    "access_changed",
                                )
                                return
                    elif turn.answer:
                        db.commit()
                        finish(rid, turn.answer, fingerprint=fingerprint)
                        return
                    else:
                        raise ProviderFailure("invalid_response")
                    db.commit()
            raise ProviderFailure("step_limit")
        except (ProviderFailure, TimeoutError) as e:
            category = e.category if isinstance(e, ProviderFailure) else "timeout"
            if category in {"access_changed", "agent_off", "channel_not_allowed"}:
                finish(rid, FRIENDLY[category], category)
                return
            if (
                provider_index + 1 < len(chain)
                and time.monotonic() - tick < settings.agent_run_timeout_seconds
            ):
                with SessionLocal() as db:
                    run = locked_run(db, rid)
                    audit(
                        db,
                        run.workspace_id,
                        "agent",
                        run.workspace_id,
                        "agent.provider_switched",
                        "run",
                        run.id,
                        status=category,
                        arguments={"from": provider, "to": chain[provider_index + 1]},
                        request_id=run.request_id,
                    )
                    db.commit()
            else:
                final = "timeout" if category == "timeout" else "unavailable"
                finish(rid, FRIENDLY[final], final)
                return


async def process_run(rid, llm=None):
    try:
        await asyncio.wait_for(
            orchestrate(
                rid, llm or (FakeLLM() if settings.agent_fake_provider else WorkspaceLLM())
            ),
            timeout=settings.agent_run_timeout_seconds,
        )
    except TimeoutError:
        finish(rid, FRIENDLY["timeout"], "timeout")
    except HTTPException:
        finish(rid, None, "access_changed")
    except Exception:
        logging.getLogger("tandem").error("agent_worker_error: internal failure (content redacted)")
        finish(rid, FRIENDLY["unavailable"], "unavailable")


def recover_stale():
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(AgentRun.id).where(
                    AgentRun.status == "running",
                    AgentRun.started_at
                    < now() - timedelta(seconds=settings.agent_run_timeout_seconds + 5),
                )
            )
        )
    for rid in ids:
        finish(rid, FRIENDLY["timeout"], "timeout")


async def worker_loop():
    next_expiry = 0.0
    while True:
        try:
            if time.monotonic() >= next_expiry:
                from app.proposals.service import expire_pending

                with SessionLocal() as db:
                    expire_pending(db, new_id())
                    db.commit()
                next_expiry = time.monotonic() + 30
            recover_stale()
            rid = claim()
            if rid:
                await process_run(rid)
            else:
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("tandem").error(
                "agent_queue_error: internal failure (content redacted)"
            )
            await asyncio.sleep(1)
