"""Authorized global search and owner/admin memory controls."""

import hashlib
import json
from datetime import timedelta
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agent.audit import audit
from app.channels.models import Channel
from app.channels.service import channel_access, visible_channels
from app.core.config import settings
from app.core.db import get_db
from app.core.models import User
from app.core.security import csrf_check, current_user, now
from app.memory.embeddings import ModelUnavailable, model
from app.memory.indexing import backfill, configuration, touch
from app.memory.models import MemoryForget, MemoryRecord, MemorySource
from app.memory.retrieval import SearchInput, authorized, reauthorize, result_out, search
from app.tasks.models import Project
from app.tasks.service import access, get_project

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["memory and search"])


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_private: bool
    retention_days: Literal[0, 90, 365]
    offer_resolution_summaries: bool


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ForgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_kind: Literal["channel", "project"] | None = None
    source_id: str | None = Field(None, min_length=1, max_length=36)
    record_ids: list[str] = Field(default_factory=list, max_length=100)
    preview_token: str | None = Field(None, max_length=4096)

    @model_validator(mode="after")
    def selection(self):
        if bool(self.source_kind and self.source_id) == bool(self.record_ids):
            raise ValueError("Select one source or explicit records")
        if bool(self.source_kind) != bool(self.source_id) or any(
            len(i) > 36 for i in self.record_ids
        ):
            raise ValueError("Invalid memory selection")
        return self


def state_out(db, wid, uid):
    config = configuration(db, wid)
    try:
        selected = model()
        status = {"degraded": False, "model": selected.identity[0], "version": selected.identity[1]}
    except ModelUnavailable:
        status = {"degraded": True, "model": None, "version": None}
    q = authorized(db, wid, uid)
    records = list(db.scalars(q))
    counts = {}
    for record in records:
        key = (record.group_kind, record.group_id)
        counts[key] = counts.get(key, 0) + 1
    sources = []
    for kind, items in [
        ("channel", visible_channels(db, wid, uid)),
        (
            "project",
            db.scalars(
                select(Project).where(Project.workspace_id == wid, Project.deleted_at.is_(None))
            ),
        ),
    ]:
        for item in items:
            value = db.get(MemorySource, (wid, kind, item.id))
            if value:
                sources.append(
                    {
                        "kind": kind,
                        "id": item.id,
                        "name": item.name,
                        "is_private": getattr(item, "is_private", False),
                        "enabled": value.enabled,
                        "records": counts.get((kind, item.id), 0),
                        "status": value.status,
                        "indexed_at": value.indexed_at.isoformat() if value.indexed_at else None,
                        "lag_ms": value.lag_ms,
                        "duration_ms": value.duration_ms,
                        "error": value.last_error,
                    }
                )
    return {
        "include_private": config.include_private,
        "retention_days": config.retention_days,
        "offer_resolution_summaries": config.offer_resolution_summaries,
        "stats": {"records": len(records), "sources": len(sources)},
        "sources": sources,
        **status,
        "note": "Results are limited to what you can access",
    }


@router.get("/search")
def global_search(
    workspace_id: str,
    inputs: SearchInput = Depends(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return search(db, workspace_id, user.id, inputs)


@router.get("/memory/records/{record_id}")
def memory_record(
    workspace_id: str,
    record_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    record = db.scalar(authorized(db, workspace_id, user.id).where(MemoryRecord.id == record_id))
    if not record:
        raise HTTPException(404, "Source unavailable")
    reauthorize(db, record, workspace_id, user.id)
    return result_out(record, "")


@router.get("/memory/settings")
def get_settings(
    workspace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    access(db, workspace_id, user.id, "admin")
    value = state_out(db, workspace_id, user.id)
    db.commit()
    return value


@router.put("/memory/settings", dependencies=[Depends(csrf_check)])
def update_settings(
    workspace_id: str,
    data: SettingsInput,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    config = configuration(db, workspace_id)
    changed = False
    for key, value in data.model_dump().items():
        if getattr(config, key) != value:
            if key == "offer_resolution_summaries":
                config.resolution_enabled_at = now() if value else None
            setattr(config, key, value)
            changed = True
            audit(
                db,
                workspace_id,
                "user",
                user.id,
                "memory.settings_changed",
                "workspace",
                workspace_id,
                arguments={key: value},
                request_id=request.state.request_id,
            )
    if changed:
        backfill(db, workspace_id)
    if not config.include_private:
        private = select(Channel.id).where(
            Channel.workspace_id == workspace_id, Channel.is_private.is_(True)
        )
        db.execute(
            delete(MemoryRecord).where(
                MemoryRecord.workspace_id == workspace_id, MemoryRecord.channel_id.in_(private)
            )
        )
    db.commit()
    return state_out(db, workspace_id, user.id)


def source_access(db, wid, uid, kind, sid):
    if kind == "channel":
        channel_access(db, wid, sid, uid)
    else:
        get_project(db, wid, sid)
    source = db.get(MemorySource, (wid, kind, sid))
    if not source:
        raise HTTPException(404, "Source unavailable")
    return source


@router.patch("/memory/sources/{kind}/{source_id}", dependencies=[Depends(csrf_check)])
def update_source(
    workspace_id: str,
    kind: Literal["channel", "project"],
    source_id: str,
    data: SourceInput,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    source = source_access(db, workspace_id, user.id, kind, source_id)
    if source.enabled != data.enabled:
        source.enabled = data.enabled
        db.flush()
        touch(db, workspace_id, kind, source_id)
        if not data.enabled:
            db.execute(
                delete(MemoryRecord).where(
                    MemoryRecord.workspace_id == workspace_id,
                    MemoryRecord.group_kind == kind,
                    MemoryRecord.group_id == source_id,
                )
            )
        audit(
            db,
            workspace_id,
            "user",
            user.id,
            "memory.source_changed",
            kind,
            source_id,
            arguments={"enabled": data.enabled},
            request_id=request.state.request_id,
        )
    db.commit()
    return {"enabled": data.enabled}


@router.post("/memory/reindex", dependencies=[Depends(csrf_check)], status_code=202)
def reindex(
    workspace_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    backfill(db, workspace_id)
    audit(
        db,
        workspace_id,
        "user",
        user.id,
        "memory.reindex_requested",
        "workspace",
        workspace_id,
        request_id=request.state.request_id,
    )
    db.commit()
    return {"status": "queued"}


@router.post("/memory/test-search", dependencies=[Depends(csrf_check)])
def test_search(
    workspace_id: str,
    data: SearchInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin")
    return search(db, workspace_id, user.id, data)


def forget_selection(db, wid, uid, data):
    q = authorized(db, wid, uid)
    if data.source_kind:
        source_access(db, wid, uid, data.source_kind, data.source_id)
        q = q.where(
            MemoryRecord.group_kind == data.source_kind, MemoryRecord.group_id == data.source_id
        )
    else:
        q = q.where(MemoryRecord.id.in_(data.record_ids))
    records = list(db.scalars(q.order_by(MemoryRecord.id)))
    if data.record_ids and {r.id for r in records} != set(data.record_ids):
        raise HTTPException(404, "Memory selection unavailable")
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "user": uid,
                "workspace": wid,
                "source": [data.source_kind, data.source_id],
                "records": [(r.id, r.content_hash) for r in records],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return records, fingerprint


@router.post("/memory/forget-preview", dependencies=[Depends(csrf_check)])
def forget_preview(
    workspace_id: str,
    data: ForgetInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin")
    records, fingerprint = forget_selection(db, workspace_id, user.id, data)
    token = jwt.encode(
        {"fingerprint": fingerprint, "exp": now() + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"count": len(records), "preview_token": token, "underlying_data_deleted": False}


@router.post("/memory/forget", dependencies=[Depends(csrf_check)])
def forget(
    workspace_id: str,
    data: ForgetInput,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    records, fingerprint = forget_selection(db, workspace_id, user.id, data)
    try:
        token = jwt.decode(
            data.preview_token or "",
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
        if token.get("fingerprint") != fingerprint:
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(409, "Memory changed; preview the selection again") from None
    # Lock all affected source rows before deleting, so a concurrently completed
    # indexing job cannot resurrect the selected records.
    keys = {(r.group_kind, r.group_id) for r in records}
    if data.source_kind:
        keys.add((data.source_kind, data.source_id))
    for kind, sid in sorted(keys):
        db.scalar(
            select(MemorySource)
            .where(
                MemorySource.workspace_id == workspace_id,
                MemorySource.kind == kind,
                MemorySource.source_id == sid,
            )
            .with_for_update()
        )
    # Recompute after locks to reject a changed preview rather than deleting new data.
    records, current = forget_selection(db, workspace_id, user.id, data)
    if current != fingerprint:
        raise HTTPException(409, "Memory changed; preview the selection again")
    for record in records:
        db.execute(
            insert(MemoryForget)
            .values(
                workspace_id=workspace_id,
                record_key=record.record_key,
                group_kind=record.group_kind,
                group_id=record.group_id,
            )
            .on_conflict_do_nothing()
        )
    if data.source_kind:
        source = source_access(db, workspace_id, user.id, data.source_kind, data.source_id)
        source.enabled = False
        source.revision += 1
        source.status = "queued"
    if records:
        db.execute(
            delete(MemoryRecord).where(
                MemoryRecord.workspace_id == workspace_id,
                MemoryRecord.id.in_([r.id for r in records]),
            )
        )
    audit(
        db,
        workspace_id,
        "user",
        user.id,
        "memory.forgotten",
        "memory",
        data.source_id,
        arguments={"count": len(records), "scope": data.source_kind or "records"},
        request_id=request.state.request_id,
    )
    db.commit()
    return {"forgotten": len(records), "underlying_data_deleted": False}


@router.get("/agent/runs/{run_id}/memory-sources")
def agent_sources(
    workspace_id: str,
    run_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import and_, or_

    from app.agent.models import AgentRun, AgentToolCall
    from app.agent.service import allowed_channels

    access(db, workspace_id, user.id)
    run = db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.workspace_id == workspace_id)
    )
    if not run:
        raise HTTPException(404, "Run unavailable")
    channel_access(db, workspace_id, run.channel_id, user.id)
    ids = [c.id for c in allowed_channels(db, workspace_id, user.id, run.channel_id)]
    refs = []
    for summary in db.scalars(
        select(AgentToolCall.result_summary).where(
            AgentToolCall.workspace_id == workspace_id, AgentToolCall.run_id == run_id
        )
    ):
        for ref in summary.get("sources", []):
            if (
                ref not in refs
                and ref.get("type") in {"message", "task"}
                and isinstance(ref.get("id"), str)
            ):
                refs.append(ref)
    if not refs:
        return {"sources": []}
    query = authorized(db, workspace_id, user.id, channel_ids=ids).where(
        or_(
            *[
                and_(MemoryRecord.source_type == r["type"], MemoryRecord.source_id == r["id"])
                for r in refs[:30]
            ]
        )
    )
    sources = []
    seen = set()
    for record in db.scalars(query.order_by(MemoryRecord.id)):
        key = record.source_type, record.source_id
        if key in seen:
            continue
        reauthorize(db, record, workspace_id, user.id, channel_ids=ids)
        seen.add(key)
        item = result_out(record, "")
        sources.append({"id": item["id"], "label": item["title"], "href": item["href"]})
    return {"sources": sources[:10]}
