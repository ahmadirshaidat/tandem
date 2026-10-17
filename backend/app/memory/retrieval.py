"""Permission predicates precede candidate selection, distance and rank fusion."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Literal

import jwt
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, exists, func, or_, select, text

from app.channels.models import Channel, ChannelMember, Message
from app.channels.service import channel_access
from app.core.config import settings
from app.core.models import Membership
from app.core.security import now
from app.documents.models import Document, DocumentMember
from app.memory.embeddings import ModelUnavailable, model
from app.memory.models import MemoryEmbedding, MemoryRecord, MemorySettings, MemorySource
from app.tasks.models import Project, Task
from app.tasks.service import access, get_project, get_task


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200)
    source_type: Literal["message", "task", "document"] | None = None
    project_id: str | None = Field(None, max_length=36)
    channel_id: str | None = Field(None, max_length=36)
    assignee_id: str | None = Field(None, max_length=36)
    task_id: str | None = Field(None, max_length=36)
    after: datetime | None = None
    before: datetime | None = None
    mode: Literal["full_text", "vector", "hybrid"] = "hybrid"
    limit: int = Field(10, ge=1, le=30)
    cursor: str | None = Field(None, max_length=2048)


def authorized(db, wid, uid, *, channel_ids=None, inputs=None, bugs_only=False):
    r = MemoryRecord
    current_project = case(
        (r.source_type == "message", Channel.project_id),
        (r.source_type == "document", Document.project_id),
        else_=Task.project_id,
    )
    q = (
        select(r)
        .join(
            MemorySource,
            and_(
                MemorySource.workspace_id == r.workspace_id,
                MemorySource.kind == r.group_kind,
                MemorySource.source_id == r.group_id,
            ),
        )
        .join(
            Membership, and_(Membership.workspace_id == r.workspace_id, Membership.user_id == uid)
        )
        .outerjoin(MemorySettings, MemorySettings.workspace_id == r.workspace_id)
        .outerjoin(
            Message, and_(Message.workspace_id == r.workspace_id, Message.id == r.message_id)
        )
        .outerjoin(
            Channel, and_(Channel.workspace_id == r.workspace_id, Channel.id == r.channel_id)
        )
        .outerjoin(
            Document, and_(Document.workspace_id == r.workspace_id, Document.id == r.document_id)
        )
        .outerjoin(Task, and_(Task.workspace_id == r.workspace_id, Task.id == r.task_id))
        .outerjoin(
            Project, and_(Project.workspace_id == r.workspace_id, Project.id == current_project)
        )
        .where(
            r.workspace_id == wid,
            r.status == "ready",
            MemorySource.enabled.is_(True),
            MemorySource.status == "idle",
            MemorySource.indexed_revision == MemorySource.revision,
        )
    )
    joined = exists(
        select(ChannelMember.id).where(
            ChannelMember.workspace_id == wid,
            ChannelMember.channel_id == Channel.id,
            ChannelMember.user_id == uid,
        )
    )
    message_ok = and_(
        r.source_type == "message",
        Message.deleted_at.is_(None),
        Message.id.is_not(None),
        Channel.archived.is_(False),
        or_(
            Channel.project_id.is_(None),
            and_(
                Project.id.is_not(None), Project.deleted_at.is_(None), Project.archived.is_(False)
            ),
        ),
        or_(Channel.is_private.is_(False), and_(MemorySettings.include_private.is_(True), joined)),
    )
    if channel_ids is not None:
        message_ok = and_(message_ok, Channel.id.in_(channel_ids))
    task_ok = and_(
        r.source_type == "task",
        Task.id.is_not(None),
        MemoryRecord.group_id == Task.project_id,
        Task.deleted_at.is_(None),
        Project.deleted_at.is_(None),
        Project.archived.is_(False),
    )
    document_ok = and_(
        r.source_type == "document",
        r.group_id == Document.id,
        Document.deleted_at.is_(None),
        Document.archived.is_(False),
        Project.deleted_at.is_(None),
        Project.archived.is_(False),
        MemorySettings.include_documents.is_(True),
        or_(
            Document.is_private.is_(False),
            exists(
                select(DocumentMember.user_id).where(
                    DocumentMember.workspace_id == wid,
                    DocumentMember.document_id == Document.id,
                    DocumentMember.user_id == uid,
                )
            ),
        ),
    )
    if channel_ids is not None:
        # Shared agent searches conservatively exclude private documents. Explicit get_document
        # separately checks the complete destination audience.
        document_ok = and_(document_ok, Document.is_private.is_(False))
    q = q.where(or_(message_ok, task_ok, document_ok))
    days = func.coalesce(MemorySettings.retention_days, 0)
    q = q.where(or_(days == 0, r.source_created_at >= func.now() - days * text("interval '1 day'")))
    if bugs_only:
        q = q.where(r.source_type == "task", Task.type == "bug")
    if inputs:
        if inputs.source_type:
            q = q.where(r.source_type == inputs.source_type)
        if inputs.project_id:
            q = q.where(current_project == inputs.project_id)
        if inputs.channel_id:
            q = q.where(Channel.id == inputs.channel_id, r.source_type == "message")
        if inputs.assignee_id:
            q = q.where(Task.assignee_id == inputs.assignee_id, r.source_type == "task")
        if inputs.task_id:
            q = q.where(Task.id == inputs.task_id, r.source_type == "task")
        if inputs.after:
            q = q.where(r.source_created_at >= inputs.after)
        if inputs.before:
            q = q.where(r.source_created_at <= inputs.before)
    return q.execution_options(populate_existing=True)


def reauthorize(db, record, wid, uid, *, channel_ids=None):
    access(db, wid, uid)
    if record.source_type == "message":
        channel, _ = channel_access(db, wid, record.channel_id, uid)
        if channel.archived or channel_ids is not None and channel.id not in channel_ids:
            raise HTTPException(404, "Source unavailable")
        if channel.project_id and get_project(db, wid, channel.project_id).archived:
            raise HTTPException(404, "Source unavailable")
        message = db.scalar(
            select(Message)
            .where(
                Message.workspace_id == wid,
                Message.id == record.message_id,
                Message.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        if not message:
            raise HTTPException(404, "Source unavailable")
    elif record.source_type == "document":
        from app.documents.service import document

        document(db, wid, record.document_id, uid)
    else:
        task = get_task(db, wid, record.task_id)
        if get_project(db, wid, task.project_id).archived:
            raise HTTPException(404, "Source unavailable")
    # Recheck revision/settings too, after service authorization. Never use a
    # precomputed list to authorize a later source-chip request.
    if not db.scalar(
        authorized(db, wid, uid, channel_ids=channel_ids)
        .where(MemoryRecord.id == record.id)
        .with_only_columns(MemoryRecord.id)
    ):
        raise HTTPException(404, "Source unavailable")


def result_out(record, query):
    snippet = record.chunk_text[:360]
    words = sorted({w for w in re.findall(r"\w+", query) if len(w) > 1}, key=len, reverse=True)
    ranges = []
    if words:
        ranges = [
            {"start": m.start(), "end": m.end()}
            for m in re.finditer("|".join(re.escape(w) for w in words), snippet, re.I)
        ]
    return {
        "id": record.id,
        "source_type": record.source_type,
        "source_id": record.source_id,
        "title": record.title,
        "snippet": snippet,
        "highlights": ranges,
        "channel_id": record.channel_id,
        "project_id": record.project_id,
        "created_at": record.source_created_at.isoformat(),
        "source": {"type": record.source_type, "id": record.source_id},
        "href": f"/channels?channel={record.channel_id}&message={record.source_id}"
        if record.source_type == "message"
        else f"/documents?document={record.source_id}"
        if record.source_type == "document"
        else f"/tasks?task={record.source_id}",
    }


def search(db, wid, uid, inputs, *, channel_ids=None, bugs_only=False, embedder=None):
    access(db, wid, uid)
    # Explicit target filters share REST's indistinguishable authorization errors.
    if inputs.channel_id:
        channel_access(db, wid, inputs.channel_id, uid)
    if inputs.project_id:
        get_project(db, wid, inputs.project_id)
    if inputs.task_id:
        get_task(db, wid, inputs.task_id)
    q = authorized(db, wid, uid, channel_ids=channel_ids, inputs=inputs, bugs_only=bugs_only)
    stopwords = set(
        "the a an is are was were to of on in why how and or for with our we it when after before does do did not can that this في من على الى الي و عن هل عند لماذا بعد قبل كيف كنا يتم كانت اذا ليس لا هذه هذا هي هو".split()
    )
    terms = [word for word in re.findall(r"\w+", inputs.query.lower()) if word not in stopwords]
    normalized = func.memory_normalize(" OR ".join(terms))
    tsq = func.websearch_to_tsquery("simple", normalized).op("||")(
        func.websearch_to_tsquery("english", normalized)
    )
    rank = func.ts_rank_cd(MemoryRecord.search_vector, tsq)
    fts = []
    if inputs.mode != "vector":
        fts = list(
            db.scalars(
                q.where(MemoryRecord.search_vector.op("@@")(tsq))
                .order_by(
                    rank.desc(),
                    MemoryRecord.source_type,
                    MemoryRecord.source_id,
                    MemoryRecord.chunk_number,
                )
                .limit(200)
            )
        )
    vector = []
    selected = embedder
    degraded = False
    try:
        if selected is None:
            selected = model()
        if inputs.mode != "full_text":
            query_vector = selected.encode([inputs.query], query=True)[0]
            distance = MemoryEmbedding.vector.cosine_distance(query_vector)
            vq = q.join(
                MemoryEmbedding,
                and_(
                    MemoryEmbedding.workspace_id == MemoryRecord.workspace_id,
                    MemoryEmbedding.record_id == MemoryRecord.id,
                    MemoryEmbedding.embedding_model == selected.identity[0],
                    MemoryEmbedding.model_version == selected.identity[1],
                ),
            )
            vector = list(
                db.scalars(
                    vq.order_by(
                        distance,
                        MemoryRecord.source_type,
                        MemoryRecord.source_id,
                        MemoryRecord.chunk_number,
                    ).limit(200)
                )
            )
    except (ModelUnavailable, ValueError, RuntimeError):
        degraded = True
        if inputs.mode == "vector":
            fts = list(
                db.scalars(
                    q.where(MemoryRecord.search_vector.op("@@")(tsq))
                    .order_by(
                        rank.desc(),
                        MemoryRecord.source_type,
                        MemoryRecord.source_id,
                        MemoryRecord.chunk_number,
                    )
                    .limit(200)
                )
            )
    # RRF is fixed before the held-out evaluation; no test-set weight tuning.
    scores = {}
    records = {}
    for candidates in [fts, vector]:
        for index, record in enumerate(candidates):
            scores[record.id] = scores.get(record.id, 0) + 1 / (60 + index + 1)
            records[record.id] = record
    ordered = sorted(
        records.values(),
        key=lambda r: (-scores[r.id], r.source_type, r.source_id, r.chunk_number, r.id),
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "wid": wid,
                "uid": uid,
                "inputs": inputs.model_dump(mode="json", exclude={"cursor"}),
                "channels": sorted(channel_ids) if channel_ids is not None else None,
                "bugs": bugs_only,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    offset = 0
    if inputs.cursor:
        try:
            cursor = jwt.decode(
                inputs.cursor,
                settings.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["exp"]},
            )
            if (
                cursor.get("fingerprint") != fingerprint
                or not isinstance(cursor.get("offset"), int)
                or not 0 <= cursor["offset"] <= 200
            ):
                raise ValueError
            offset = cursor["offset"]
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(400, "Search cursor is invalid; search again") from None
    items = []
    seen = set()
    for record in ordered:
        key = record.source_type, record.source_id
        if key in seen:
            continue
        try:
            reauthorize(db, record, wid, uid, channel_ids=channel_ids)
        except HTTPException:
            continue
        seen.add(key)
        items.append(result_out(record, inputs.query))
    page = items[offset : offset + inputs.limit]
    next_cursor = None
    if offset + inputs.limit < len(items):
        next_cursor = jwt.encode(
            {
                "fingerprint": fingerprint,
                "offset": offset + inputs.limit,
                "exp": now() + timedelta(minutes=10),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
    return {
        "items": page,
        "next_cursor": next_cursor,
        "degraded": degraded,
        "retrieval_mode": "full_text" if degraded else inputs.mode,
        "note": "Results are limited to what you can access",
    }
