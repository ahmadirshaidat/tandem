"""Transactional invalidation, coalesced jobs and idempotent local indexing."""

import hashlib
import time
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.channels.models import Channel, Message
from app.core.db import SessionLocal
from app.core.models import Workspace
from app.core.security import now
from app.documents.models import Document
from app.memory.embeddings import ModelUnavailable, model
from app.memory.models import (
    MemoryEmbedding,
    MemoryForget,
    MemoryRecord,
    MemorySettings,
    MemorySource,
)
from app.tasks.models import Project, Task, TaskComment


def configuration(db, wid):
    value = db.get(MemorySettings, wid)
    if not value:
        value = MemorySettings(workspace_id=wid)
        db.add(value)
        db.flush()
    return value


def touch(db, wid, kind, sid):
    db.execute(text("SELECT memory_touch(:wid,:kind,:sid)"), {"wid": wid, "kind": kind, "sid": sid})


def backfill(db, wid):
    for kind, table in [("channel", Channel), ("project", Project), ("document", Document)]:
        for sid in db.scalars(select(table.id).where(table.workspace_id == wid)):
            touch(db, wid, kind, sid)


def chunks(value, size=900, overlap=120):
    # Character bounds keep mixed Arabic/English chunks small; every chunk overlaps.
    value = value.strip()
    for start in range(0, len(value), size - overlap):
        yield value[start : start + size]
        if start + size >= len(value):
            break


def snapshot(db, source, config):
    cutoff = now() - timedelta(days=config.retention_days) if config.retention_days else None
    output = []

    def add(item, body, title, cid, pid, typ):
        if cutoff and item.created_at < cutoff:
            return
        for index, chunk in enumerate(chunks(body)):
            key = hashlib.sha256(f"{typ}:{item.id}:{index}".encode()).hexdigest()
            output.append(
                {
                    "source_type": typ,
                    "source_id": item.id,
                    "channel_id": cid,
                    "project_id": pid,
                    "task_id": item.id if typ == "task" else None,
                    "document_id": item.id if typ == "document" else None,
                    "message_id": item.id if typ == "message" else None,
                    "chunk_number": index,
                    "record_key": key,
                    "content_hash": hashlib.sha256((title + "\n" + chunk).encode()).hexdigest(),
                    "title": title,
                    "chunk_text": chunk,
                    "visibility_scope": "channel" if cid else "project",
                    "source_created_at": item.created_at,
                }
            )

    if not source.enabled:
        return output
    if source.kind == "document":
        d = db.get(Document, source.source_id)
        if not d or d.archived or d.deleted_at or not config.include_documents:
            return output
        project = db.get(Project, d.project_id)
        if not project or project.archived or project.deleted_at:
            return output
        # Heading boundaries are preserved; existing chunker bounds long sections.
        import re

        for section in re.split(r"(?m)(?=^#{1,3} )", d.markdown):
            if section.strip():
                prior = len(output)
                add(d, section, d.title, None, d.project_id, "document")
                for offset, row in enumerate(output[prior:], prior):
                    row["chunk_number"] = offset
                    row["record_key"] = hashlib.sha256(
                        f"document:{d.id}:{offset}".encode()
                    ).hexdigest()
                    row["visibility_scope"] = "document"
        return output
    if source.kind == "channel":
        channel = db.get(Channel, source.source_id)
        if not channel or channel.archived or channel.is_private and not config.include_private:
            return output
        if channel.project_id:
            project = db.get(Project, channel.project_id)
            if not project or project.archived or project.deleted_at:
                return output
        # Group a thread or five-minute window. Rebuild the whole channel on any
        # constituent edit/delete, so an overlapped message can never survive stale.
        groups = defaultdict(list)
        for message in db.scalars(
            select(Message)
            .where(
                Message.workspace_id == source.workspace_id,
                Message.channel_id == channel.id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.seq)
        ):
            if cutoff and message.created_at < cutoff:
                continue
            key = message.thread_root_id or f"window:{int(message.created_at.timestamp()) // 300}"
            groups[key].append(message)
        for messages in groups.values():
            # Anchor each bounded window to a real message; never span channels.
            for start in range(0, len(messages), 6):
                window = messages[max(0, start - 1) : start + 6]
                anchor = messages[start]
                add(
                    anchor,
                    "\n".join(m.body for m in window),
                    f"#{channel.name}",
                    channel.id,
                    channel.project_id,
                    "message",
                )
    else:
        project = db.get(Project, source.source_id)
        if not project or project.archived or project.deleted_at:
            return output
        comments = defaultdict(list)
        for comment in db.scalars(
            select(TaskComment)
            .join(Task, TaskComment.task_id == Task.id)
            .where(
                TaskComment.workspace_id == source.workspace_id,
                Task.project_id == project.id,
                TaskComment.deleted_at.is_(None),
            )
            .order_by(TaskComment.created_at, TaskComment.id)
        ):
            comments[comment.task_id].append(comment.body)
        for task in db.scalars(
            select(Task)
            .where(
                Task.workspace_id == source.workspace_id,
                Task.project_id == project.id,
                Task.deleted_at.is_(None),
            )
            .order_by(Task.id)
        ):
            body = "\n".join(
                [task.title, task.description, f"Status: {task.status}", *comments[task.id]]
            )
            add(task, body, task.title, None, project.id, "task")
    return output


def process_one(*, embedder=None, raise_errors=False):
    tick = time.perf_counter()
    key = None
    with SessionLocal() as db:
        # Stale claims are recoverable after a worker/process restart.
        for stale in db.scalars(
            select(MemorySource)
            .where(
                MemorySource.status == "indexing",
                MemorySource.started_at < now() - timedelta(minutes=5),
            )
            .with_for_update(skip_locked=True)
        ):
            stale.status = "queued"
        source = db.scalar(
            select(MemorySource)
            .where(MemorySource.status == "queued")
            .order_by(MemorySource.queued_at, MemorySource.workspace_id, MemorySource.source_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not source:
            db.commit()
            return False
        source.status, source.started_at = "indexing", now()
        source.attempts += 1
        key = (source.workspace_id, source.kind, source.source_id)
        revision, queued_at = source.revision, source.queued_at
        config = db.get(MemorySettings, source.workspace_id) or MemorySettings(
            workspace_id=source.workspace_id,
            include_private=False,
            retention_days=0,
            offer_resolution_summaries=False,
        )
        data = snapshot(db, source, config)
        db.commit()
    try:
        selected = embedder
        error = None
        if selected is None:
            try:
                selected = model()
            except ModelUnavailable:
                error = "embedding_unavailable"
        with SessionLocal() as db:
            existing = {
                r.record_key: r
                for r in db.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.workspace_id == key[0],
                        MemoryRecord.group_kind == key[1],
                        MemoryRecord.group_id == key[2],
                    )
                )
            }
            forgotten = set(
                db.scalars(
                    select(MemoryForget.record_key).where(
                        MemoryForget.workspace_id == key[0],
                        MemoryForget.record_key.in_([d["record_key"] for d in data]),
                    )
                )
            )
            data = [d for d in data if d["record_key"] not in forgotten]
            identity = selected.identity if selected else None
            ready = set()
            if identity:
                ready = set(
                    db.scalars(
                        select(MemoryEmbedding.record_id).where(
                            MemoryEmbedding.workspace_id == key[0],
                            MemoryEmbedding.embedding_model == identity[0],
                            MemoryEmbedding.model_version == identity[1],
                        )
                    )
                )
            needed = [
                d
                for d in data
                if selected
                and (
                    d["record_key"] not in existing
                    or existing[d["record_key"]].content_hash != d["content_hash"]
                    or existing[d["record_key"]].id not in ready
                )
            ]
        try:
            vectors = (
                selected.encode([d["title"] + "\n" + d["chunk_text"] for d in needed])
                if selected
                else []
            )
        except ModelUnavailable:
            selected, identity, needed, vectors = None, None, [], []
            error = "embedding_unavailable"
        with SessionLocal() as db:
            # Match domain/settings lock order: workspace, then source.
            db.scalar(select(Workspace).where(Workspace.id == key[0]).with_for_update())
            source = db.scalar(
                select(MemorySource)
                .where(
                    MemorySource.workspace_id == key[0],
                    MemorySource.kind == key[1],
                    MemorySource.source_id == key[2],
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not source:
                return True
            if source.revision != revision:
                source.status = "queued"
                db.commit()
                return True
            # A task moved between projects must not leave stale content or clash
            # with its stable record key in the destination project.
            moved = (
                select(Task.id)
                .where(Task.workspace_id == key[0], Task.project_id != MemoryRecord.group_id)
                .correlate(MemoryRecord)
            )
            db.execute(
                delete(MemoryRecord).where(
                    MemoryRecord.workspace_id == key[0],
                    MemoryRecord.source_type == "task",
                    MemoryRecord.task_id.in_(moved),
                )
            )
            keep = {d["record_key"] for d in data}
            db.execute(
                delete(MemoryRecord).where(
                    MemoryRecord.workspace_id == key[0],
                    MemoryRecord.group_kind == key[1],
                    MemoryRecord.group_id == key[2],
                    MemoryRecord.record_key.not_in(keep),
                )
            )
            current = {
                r.record_key: r
                for r in db.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.workspace_id == key[0],
                        MemoryRecord.group_kind == key[1],
                        MemoryRecord.group_id == key[2],
                    )
                )
            }
            vector_map = {d["record_key"]: v for d, v in zip(needed, vectors, strict=True)}
            for values in data:
                record = current.get(values["record_key"])
                if not record:
                    record = MemoryRecord(
                        workspace_id=key[0], group_kind=key[1], group_id=key[2], **values
                    )
                    db.add(record)
                    db.flush()
                elif record.content_hash != values["content_hash"]:
                    db.execute(
                        delete(MemoryEmbedding).where(
                            MemoryEmbedding.workspace_id == key[0],
                            MemoryEmbedding.record_id == record.id,
                        )
                    )
                    for name, value in values.items():
                        setattr(record, name, value)
                    record.indexed_at = now()
                if values["record_key"] in vector_map:
                    db.execute(
                        insert(MemoryEmbedding)
                        .values(
                            workspace_id=key[0],
                            record_id=record.id,
                            embedding_model=identity[0],
                            model_version=identity[1],
                            dimension=384,
                            vector=vector_map[values["record_key"]],
                        )
                        .on_conflict_do_nothing()
                    )
            source.indexed_revision, source.status, source.indexed_at = revision, "idle", now()
            source.last_error = error
            source.duration_ms = round((time.perf_counter() - tick) * 1000, 2)
            source.lag_ms = round((now() - queued_at).total_seconds() * 1000, 2)
            from app.memory.resolution import offer_for_project

            if source.kind == "project" and source.enabled:
                offer_for_project(db, source.workspace_id, source.source_id)
            db.commit()
        return True
    except Exception:
        if raise_errors:
            raise
        with SessionLocal() as db:
            source = db.get(MemorySource, key)
            if source:
                source.status = "failed"
                source.last_error = "index_failed"
                db.commit()
        # Never log a source, chunk, model input or upstream exception body.
        return True


def maintenance(db):
    for config in db.scalars(select(MemorySettings)):
        if config.retention_days:
            db.execute(
                delete(MemoryRecord).where(
                    MemoryRecord.workspace_id == config.workspace_id,
                    MemoryRecord.source_created_at < now() - timedelta(days=config.retention_days),
                )
            )
    for source in db.scalars(
        select(MemorySource).where(
            MemorySource.status == "failed",
            MemorySource.attempts < 3,
            MemorySource.started_at < now() - timedelta(seconds=30),
        )
    ):
        source.status = "queued"
    try:
        selected = model()
    except ModelUnavailable:
        return
    # A new model revision is an explicit reindex path; old vectors stay until
    # replaced, but queries use only the configured verified model/version.
    missing = (
        select(MemoryRecord.group_id)
        .outerjoin(
            MemoryEmbedding,
            (MemoryEmbedding.record_id == MemoryRecord.id)
            & (MemoryEmbedding.embedding_model == selected.identity[0])
            & (MemoryEmbedding.model_version == selected.identity[1]),
        )
        .where(MemoryEmbedding.record_id.is_(None))
        .distinct()
    )
    for source in db.scalars(
        select(MemorySource).where(
            MemorySource.source_id.in_(missing),
            MemorySource.status == "idle",
            MemorySource.enabled.is_(True),
        )
    ):
        source.revision += 1
        source.status, source.queued_at = "queued", now()


def run_maintenance():
    with SessionLocal() as db:
        maintenance(db)
        db.commit()
