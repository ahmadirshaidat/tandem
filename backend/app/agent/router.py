import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.agent.audit import audit
from app.agent.llm import availability
from app.agent.models import AgentChannelAccess, AgentRun, AuditEvent
from app.agent.service import allowed_channels, channel_enabled, configuration, run_out, usage
from app.channels.service import channel_access, visible_channels
from app.core.db import get_db
from app.core.models import User
from app.core.security import csrf_check, current_user
from app.tasks.models import Project
from app.tasks.service import access

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["agent and audit"])


class SettingsInput(BaseModel):
    enabled: bool
    provider_chain: list[Literal["groq", "gemini", "deepseek", "openai"]] = Field(
        min_length=1, max_length=4
    )
    monthly_run_limit: int = Field(ge=1, le=1000000)
    pause_at_limit: bool

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.provider_chain)) != len(self.provider_chain):
            raise ValueError("Choose each provider once")
        return self


class ChannelInput(BaseModel):
    enabled: bool


def settings_out(db, workspace_id, uid):
    c = configuration(db, workspace_id)
    return {
        "enabled": c.enabled,
        "provider_chain": c.provider_chain,
        "monthly_run_limit": c.monthly_run_limit,
        "pause_at_limit": c.pause_at_limit,
        "usage": usage(db, workspace_id),
        "channels": [
            {
                "id": ch.id,
                "name": ch.name,
                "is_private": ch.is_private,
                "enabled": channel_enabled(db, workspace_id, ch),
            }
            for ch in visible_channels(db, workspace_id, uid)
        ],
        "providers": availability,
    }


@router.get("/agent/settings")
def get_settings(
    workspace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    access(db, workspace_id, user.id, "admin")
    out = settings_out(db, workspace_id, user.id)
    db.commit()
    return out


@router.put("/agent/settings", dependencies=[Depends(csrf_check)])
def update_settings(
    workspace_id: str,
    data: SettingsInput,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    member = access(db, workspace_id, user.id, "admin", lock=True)
    c = configuration(db, workspace_id)
    if member.role != "owner" and any(
        p in data.provider_chain and p not in c.provider_chain for p in ["openai", "deepseek"]
    ):
        raise HTTPException(403, "Only an Owner can opt in to additional providers")
    for key, value in data.model_dump().items():
        if getattr(c, key) != value:
            audit(
                db,
                workspace_id,
                "user",
                user.id,
                {
                    "enabled": "agent.enabled" if value else "agent.disabled",
                    "provider_chain": "agent.provider_chain_changed",
                    "monthly_run_limit": "agent.limit_changed",
                    "pause_at_limit": "agent.limit_changed",
                }[key],
                "workspace",
                workspace_id,
                arguments={key: value},
                request_id=request.state.request_id,
            )
            setattr(c, key, value)
    audit(
        db,
        workspace_id,
        "user",
        user.id,
        "agent.settings_updated",
        "workspace",
        workspace_id,
        request_id=request.state.request_id,
    )
    db.commit()
    return settings_out(db, workspace_id, user.id)


@router.put("/agent/channels/{channel_id}", dependencies=[Depends(csrf_check)])
def set_channel(
    workspace_id: str,
    channel_id: str,
    data: ChannelInput,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    channel_access(db, workspace_id, channel_id, user.id)
    entry = db.get(AgentChannelAccess, (workspace_id, channel_id))
    if not entry:
        entry = AgentChannelAccess(workspace_id=workspace_id, channel_id=channel_id)
        db.add(entry)
    entry.enabled = data.enabled
    audit(
        db,
        workspace_id,
        "user",
        user.id,
        "agent.channel_access_changed",
        "channel",
        channel_id,
        arguments={"enabled": data.enabled},
        request_id=request.state.request_id,
    )
    db.commit()
    return {"enabled": entry.enabled}


@router.get("/agent/context")
def context(
    workspace_id: str,
    channel_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    if channel_id:
        channel_access(db, workspace_id, channel_id, user.id)
    return {
        "channels": [
            {"id": c.id, "name": c.name}
            for c in allowed_channels(db, workspace_id, user.id, channel_id)
        ],
        "projects": [
            {"id": p.id, "name": p.name}
            for p in db.scalars(
                select(Project)
                .where(Project.workspace_id == workspace_id, Project.deleted_at.is_(None))
                .limit(100)
            )
        ],
        "private_notice": "Private channels you cannot open are never available. Other private channels are excluded from shared answers.",
    }


@router.get("/agent/runs")
def runs(
    workspace_id: str,
    channel_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    channel_access(db, workspace_id, channel_id, user.id)
    return [
        run_out(db, r)
        for r in db.scalars(
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id, AgentRun.channel_id == channel_id)
            .order_by(AgentRun.created_at.desc())
            .limit(30)
        )
    ]


@router.get("/agent/recent")
def recent(workspace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    visible = [c.id for c in visible_channels(db, workspace_id, user.id)]
    # Narrow projection of this user's runs, not general audit access.
    return [
        run_out(db, r)
        for r in db.scalars(
            select(AgentRun)
            .where(
                AgentRun.workspace_id == workspace_id,
                AgentRun.requester_id == user.id,
                AgentRun.channel_id.in_(visible),
            )
            .order_by(AgentRun.created_at.desc())
            .limit(10)
        )
    ]


def audit_query(db, wid, before, after, until, actor, action, status):
    q = select(AuditEvent).where(AuditEvent.workspace_id == wid)
    for value, column, operator in [
        (after, AuditEvent.created_at, "ge"),
        (until, AuditEvent.created_at, "le"),
        (actor, AuditEvent.actor_type, "eq"),
        (action, AuditEvent.action, "eq"),
        (status, AuditEvent.result_status, "eq"),
    ]:
        if value is not None:
            q = q.where(
                {"ge": column.__ge__, "le": column.__le__, "eq": column.__eq__}[operator](value)
            )
    if before:
        anchor = db.scalar(
            select(AuditEvent).where(AuditEvent.workspace_id == wid, AuditEvent.id == before)
        )
        if not anchor:
            raise HTTPException(422, "Invalid audit cursor")
        q = q.where(
            or_(
                AuditEvent.created_at < anchor.created_at,
                and_(AuditEvent.created_at == anchor.created_at, AuditEvent.id < anchor.id),
            )
        )
    return q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())


def audit_out(e):
    return {
        k: getattr(e, k)
        for k in [
            "id",
            "actor_type",
            "actor_id",
            "action",
            "target_type",
            "target_id",
            "redacted_arguments",
            "result_status",
            "approval_id",
            "approval_status",
            "request_id",
        ]
    } | {"created_at": e.created_at.isoformat()}


@router.get("/audit")
@router.get("/audit/export.csv")
def read_audit(
    workspace_id: str,
    request: Request,
    before: str | None = Query(None, max_length=36),
    after: datetime | None = None,
    until: datetime | None = None,
    actor: Literal["user", "agent", "system"] | None = None,
    action: str | None = Query(None, max_length=64),
    status: str | None = Query(None, max_length=24),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin")
    export = request.url.path.endswith(".csv")
    rows = list(
        db.scalars(
            audit_query(db, workspace_id, before, after, until, actor, action, status).limit(
                (10000 if export else limit) + 1
            )
        )
    )
    if export:
        if len(rows) > 10000:
            raise HTTPException(422, "Narrow the time filter to export at most 10000 rows")
        stream = io.StringIO()
        writer = csv.writer(stream)
        keys = [
            "created_at",
            "actor_type",
            "actor_id",
            "action",
            "target_type",
            "target_id",
            "result_status",
            "request_id",
            "redacted_arguments",
        ]
        writer.writerow(keys)
        for row in rows:
            values = audit_out(row)
            writer.writerow(
                [
                    ("'" + str(values[k]))
                    if str(values[k]).startswith(("=", "+", "-", "@"))
                    else values[k]
                    for k in keys
                ]
            )
        return Response(
            stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="tandem-audit.csv"'},
        )
    return {
        "events": [audit_out(e) for e in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }
