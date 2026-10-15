from sqlalchemy import func, select

from app.agent.models import AgentChannelAccess, AgentRun, AgentSettings, AgentToolCall
from app.channels.service import channel_access, visible_channels
from app.core.security import now


def configuration(db, wid):
    config = db.get(AgentSettings, wid)
    if not config:
        config = AgentSettings(
            workspace_id=wid,
            enabled=False,
            provider_chain=["groq", "gemini"],
            monthly_run_limit=1000,
            pause_at_limit=True,
        )
        db.add(config)
        db.flush()
    return config


def channel_enabled(db, wid, channel):
    value = db.get(AgentChannelAccess, (wid, channel.id))
    return value.enabled if value else not channel.is_private


def allowed_channels(db, wid, uid, destination=None):
    # A public answer must never quote a different private audience.
    return [
        c
        for c in visible_channels(db, wid, uid)
        if channel_enabled(db, wid, c)
        and not c.archived
        and (not c.is_private or c.id == destination)
    ]


def usage(db, wid):
    return db.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.workspace_id == wid,
            AgentRun.created_at >= now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            AgentRun.status != "blocked",
        )
    )


def run_out(db, run):
    calls = list(
        db.scalars(
            select(AgentToolCall)
            .where(AgentToolCall.run_id == run.id)
            .order_by(AgentToolCall.created_at, AgentToolCall.id)
        )
    )
    return {
        "id": run.id,
        "channel_id": run.channel_id,
        "trigger_message_id": run.trigger_message_id,
        "status": run.status,
        "error_category": run.error_category,
        "provider": run.provider,
        "model": run.model,
        "latency_ms": run.latency_ms,
        "steps": [
            {
                "name": c.tool_name,
                "status": c.status,
                "duration_ms": c.duration_ms,
                "count": c.result_summary.get("count", 0),
            }
            for c in calls
        ],
    }


def run_access(db, run):
    channel, _ = channel_access(db, run.workspace_id, run.channel_id, run.requester_id)
    if channel.archived:
        from fastapi import HTTPException

        raise HTTPException(404, "Context unavailable")
    return channel
