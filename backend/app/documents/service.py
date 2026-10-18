import base64
import hashlib
import hmac
import json
from datetime import timedelta

import httpx
from fastapi import HTTPException
from pycrdt import Doc
from sqlalchemy import delete, exists, or_, select

from app.agent.audit import audit
from app.channels.models import ChannelMember
from app.channels.service import channel_access
from app.core.config import settings
from app.core.models import User
from app.core.security import now
from app.documents.models import Document, DocumentMember, DocumentUpdate, DocumentVersion
from app.tasks.models import Link, Project
from app.tasks.service import access, get_project, resolve_item
from app.workspaces.permissions import LEVEL

TEMPLATES = {
    "spec": "# Specification\n## Problem\nDescribe the problem.\n## Requirements\nDefine the expected behavior.\n## Acceptance\nDefine how to verify it.",
    "meeting_notes": "# Meeting notes\n## Agenda\n## Decisions\n## Actions",
    "adr": "# Architecture decision\n## Context\n## Decision\n## Consequences",
    "bug_postmortem": "# Bug postmortem\n## Impact\n## Timeline\n## Root cause\n## Resolution\n## Follow-up",
}


def sync_secret():
    return (
        settings.document_sync_secret.get_secret_value()
        if settings.document_sync_secret and settings.document_sync_secret.get_secret_value()
        else hmac.new(
            settings.jwt_secret.encode(), b"tandem-document-sync", hashlib.sha256
        ).hexdigest()
    )


def transform(state=b"", **action):
    try:
        with httpx.Client(trust_env=False, timeout=5) as client:
            result = client.post(
                settings.document_sync_url + "/transform",
                headers={"Authorization": "Bearer " + sync_secret()},
                json={"state": base64.b64encode(state).decode(), **action},
            )
        if result.status_code == 422:
            raise HTTPException(422, "Document content or anchor is invalid or ambiguous")
        if result.status_code != 200:
            raise ValueError
        return result.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Document synchronization service unavailable") from None


def visible(db, wid, uid):
    access(db, wid, uid)
    member = exists(
        select(DocumentMember.document_id).where(
            DocumentMember.workspace_id == wid,
            DocumentMember.document_id == Document.id,
            DocumentMember.user_id == uid,
        )
    )
    return (
        select(Document)
        .join(
            Project,
            (Project.id == Document.project_id) & (Project.workspace_id == Document.workspace_id),
        )
        .where(
            Document.workspace_id == wid,
            Document.deleted_at.is_(None),
            Project.deleted_at.is_(None),
            or_(Document.is_private.is_(False), member),
        )
    )


def document(db, wid, did, uid, minimum="viewer", lock=False):
    access(db, wid, uid, minimum, lock=lock)
    q = visible(db, wid, uid).where(Document.id == did).execution_options(populate_existing=True)
    if lock:
        q = q.with_for_update(of=Document)
    d = db.scalar(q)
    if not d:
        raise HTTPException(404, "Document not found or you do not have access")
    if minimum != "viewer" and (d.archived or get_project(db, wid, d.project_id).archived):
        raise HTTPException(409, "This document or project is archived")
    return d


def output(d):
    return {
        k: getattr(d, k)
        for k in [
            "id",
            "workspace_id",
            "project_id",
            "title",
            "type",
            "is_private",
            "archived",
            "revision",
            "created_by",
        ]
    }


def log(db, d, uid, kind, **args):
    audit(db, d.workspace_id, "user", uid, "document." + kind, "document", d.id, arguments=args)


def snapshot(db, d, uid, name=None, actor_type="user", proposal_id=None):
    v = DocumentVersion(
        workspace_id=d.workspace_id,
        document_id=d.id,
        state=d.state,
        markdown=d.markdown,
        revision=d.revision,
        name=name,
        created_by=uid,
        actor_type=actor_type,
        proposal_id=proposal_id,
    )
    db.add(v)
    d.snapshot_at = now()
    db.flush()
    return v


def links(db, d, uid, mentions):
    # Only accessible targets are accepted. Backlinks are authorized again on read.
    ids = set()
    for ref in mentions:
        item = resolve_item(db, d.workspace_id, ref["type"], ref["id"], uid)
        if item["id"] == d.id and ref["type"] == "document":
            continue
        ids.add((ref["type"], ref["id"]))
    db.execute(
        delete(Link).where(
            Link.workspace_id == d.workspace_id,
            Link.source_type == "document",
            Link.source_id == d.id,
        )
    )
    for typ, sid in ids:
        db.add(
            Link(
                workspace_id=d.workspace_id,
                source_type="document",
                source_id=d.id,
                target_type=typ,
                target_id=sid,
                relation="related",
                created_by=uid,
            )
        )


def persist(db, d, uid, update, *, snapshot_actor=None, proposal_id=None):
    if len(update) > settings.document_update_bytes:
        raise HTTPException(413, "Document update exceeds limit")
    try:
        crdt = Doc()
        crdt.apply_update(d.state)
        crdt.apply_update(update)
        if set(crdt.keys()) - {"default"}:
            raise ValueError
        merged = crdt.get_update()
        if len(merged) > settings.document_max_bytes:
            raise HTTPException(413, "Document exceeds size limit")
    except (ValueError, RuntimeError, TypeError):
        raise HTTPException(422, "Invalid document update") from None
    if merged == d.state:
        return d
    projected = transform(merged)
    links(db, d, uid, projected["mentions"])
    d.state = merged
    d.plain_text = projected["text"]
    d.markdown = projected["markdown"]
    d.revision += 1
    d.updated_at = now()
    d.last_editor = uid
    db.add(
        DocumentUpdate(
            workspace_id=d.workspace_id,
            document_id=d.id,
            revision=d.revision,
            update=update,
            created_by=uid,
        )
    )
    if snapshot_actor or d.snapshot_at + timedelta(minutes=2) <= now():
        snapshot(db, d, uid, actor_type=snapshot_actor or "user", proposal_id=proposal_id)
    # State is compacted on every commit; retain at most 100 incremental frames.
    db.execute(
        delete(DocumentUpdate).where(
            DocumentUpdate.workspace_id == d.workspace_id,
            DocumentUpdate.document_id == d.id,
            DocumentUpdate.revision < d.revision - 100,
        )
    )
    db.flush()
    return d


def create(db, wid, uid, data):
    access(db, wid, uid, "editor", lock=True)
    get_project(db, wid, data.project_id, writable=True)
    result = transform(action="template", text=TEMPLATES[data.type])
    d = Document(
        workspace_id=wid,
        project_id=data.project_id,
        title=data.title,
        type=data.type,
        is_private=data.is_private,
        state=base64.b64decode(result["state"]),
        plain_text=result["text"],
        markdown=result["markdown"],
        created_by=uid,
        last_editor=uid,
        snapshot_at=now(),
    )
    db.add(d)
    db.flush()
    if d.is_private:
        db.add(DocumentMember(workspace_id=wid, document_id=d.id, user_id=uid))
    snapshot(db, d, uid, "Created from template")
    log(db, d, uid, "created")
    db.flush()
    return d


def shared_access(db, wid, did, uid, cid):
    d = document(db, wid, did, uid)
    if d.is_private:
        channel, _ = channel_access(db, wid, cid, uid)
        if not channel.is_private:
            raise HTTPException(404, "Document unavailable")
        audience = set(
            db.scalars(
                select(ChannelMember.user_id).where(
                    ChannelMember.workspace_id == wid, ChannelMember.channel_id == cid
                )
            )
        )
        members = set(
            db.scalars(
                select(DocumentMember.user_id).where(
                    DocumentMember.workspace_id == wid, DocumentMember.document_id == did
                )
            )
        )
        if audience - members:
            raise HTTPException(404, "Document unavailable")
    return d


def state_out(db, d, uid):
    member = access(db, d.workspace_id, uid)
    editable = (
        LEVEL[member.role] >= LEVEL["editor"]
        and not d.archived
        and not get_project(db, d.workspace_id, d.project_id).archived
    )
    stamp = hashlib.sha256(
        json.dumps(
            [
                member.role,
                d.is_private,
                d.archived,
                get_project(db, d.workspace_id, d.project_id).archived,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        **output(d),
        "state": base64.b64encode(d.state).decode(),
        "can_edit": editable,
        "permission_stamp": stamp,
        "user_id": uid,
        "user_name": db.get(User, uid).name,
    }
