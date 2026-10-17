"""Opt-in extractive resolution suggestions use the existing approval service."""

from fastapi import HTTPException
from sqlalchemy import String, select

from app.agent.models import AgentRun, AgentSettings
from app.agent.service import channel_enabled, usage
from app.channels.models import Channel, Message
from app.channels.service import message_out, record_event
from app.core.models import Membership, new_id
from app.core.security import now
from app.memory.models import MemorySettings, ResolutionOffer
from app.proposals.models import Proposal
from app.tasks.models import Task, TaskActivity, TaskComment


def offer_for_project(db, workspace_id, project_id):
    config = db.get(MemorySettings, workspace_id)
    agent = db.get(AgentSettings, workspace_id)
    if (
        not config
        or not config.offer_resolution_summaries
        or not config.resolution_enabled_at
        or not agent
        or not agent.enabled
    ):
        return
    if agent.pause_at_limit and usage(db, workspace_id) >= agent.monthly_run_limit:
        return
    channel = next(
        (
            c
            for c in db.scalars(
                select(Channel)
                .where(
                    Channel.workspace_id == workspace_id,
                    Channel.project_id == project_id,
                    Channel.is_private.is_(False),
                    Channel.archived.is_(False),
                )
                .order_by(Channel.id)
            )
            if channel_enabled(db, workspace_id, c)
        ),
        None,
    )
    if not channel:
        return
    for task in db.scalars(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.project_id == project_id,
            Task.type == "bug",
            Task.status == "done",
            Task.deleted_at.is_(None),
        )
    ):
        completed = db.scalar(
            select(TaskActivity)
            .where(
                TaskActivity.workspace_id == workspace_id,
                TaskActivity.task_id == task.id,
                TaskActivity.field == "status",
                TaskActivity.new_value.cast(String) == '"done"',
                TaskActivity.created_at >= config.resolution_enabled_at,
            )
            .order_by(TaskActivity.created_at.desc(), TaskActivity.id.desc())
            .limit(1)
        )
        if not completed:
            continue
        prior = db.scalar(
            select(ResolutionOffer.task_id)
            .join(Proposal, ResolutionOffer.proposal_id == Proposal.id)
            .where(
                ResolutionOffer.workspace_id == workspace_id,
                ResolutionOffer.task_id == task.id,
                Proposal.created_at >= completed.created_at,
            )
            .limit(1)
        )
        member = db.scalar(
            select(Membership).where(
                Membership.workspace_id == workspace_id, Membership.user_id == completed.actor_id
            )
        )
        if prior or not member or member.role == "viewer":
            continue
        comment = db.scalar(
            select(TaskComment)
            .where(
                TaskComment.workspace_id == workspace_id,
                TaskComment.task_id == task.id,
                TaskComment.deleted_at.is_(None),
            )
            .order_by(TaskComment.created_at.desc(), TaskComment.id.desc())
            .limit(1)
        )
        # Extract recorded facts only. No parallel LLM path, invented cause, direct
        # comment write or implicit approval. The human sees and can edit this text.
        body = f"Resolution review: {task.title}\nTask status was marked done.\nRecorded context: {task.description[:1200]}"
        if comment:
            body += f"\nLatest recorded discussion: {comment.body[:1200]}"
        try:
            with db.begin_nested():
                from app.proposals.service import create_proposal

                run_id = new_id()
                message = Message(
                    workspace_id=workspace_id,
                    channel_id=channel.id,
                    actor_type="agent",
                    author_id=None,
                    body="A resolution summary is proposed for human review. No comment has been added.",
                    seq=channel.last_seq + 1,
                    client_message_id=run_id,
                )
                db.add(message)
                db.flush()
                run = AgentRun(
                    id=run_id,
                    workspace_id=workspace_id,
                    channel_id=channel.id,
                    trigger_message_id=message.id,
                    requester_id=completed.actor_id,
                    status="completed",
                    provider="local",
                    model="extractive-resolution-v1",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0,
                    finished_at=now(),
                )
                db.add(run)
                db.flush()
                proposal = create_proposal(
                    db,
                    run,
                    "add_comment",
                    {"task_id": task.id, "version": task.version, "body": body},
                    [{"type": "task", "id": task.id}],
                )
                db.add(
                    ResolutionOffer(
                        workspace_id=workspace_id,
                        task_id=task.id,
                        task_version=task.version,
                        proposal_id=proposal.id,
                    )
                )
                record_event(
                    db, channel, "agent.message_created", {"message": message_out(db, message)}
                )
        except HTTPException:
            # Pending caps or changed permissions fail closed; no task write.
            continue
