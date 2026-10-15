"""Only human decision endpoints call execution. Agent tools can only propose."""

import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.agent.audit import audit
from app.agent.service import configuration, run_access
from app.channels.models import Channel, Message
from app.channels.service import channel_access, record_event
from app.core.config import settings
from app.core.models import User, Workspace
from app.core.security import now
from app.proposals.models import Proposal, ProposalItem
from app.proposals.schemas import PAYLOADS, Source
from app.tasks.models import Task
from app.tasks.schemas import LinkInput, TaskInput
from app.tasks.service import (
    access,
    activity,
    add_task_comment,
    create_link,
    create_task,
    get_project,
    get_task,
    soft_delete_task,
    update_task,
    valid_assignee,
)
from app.workspaces.permissions import LEVEL

HIGH = {"reassign_task", "change_priority", "delete_task"}
TERMINAL = {"completed", "rejected", "failed", "expired", "stale"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_payload(db, wid, uid, kind, payload, *, creation=False, check_duplicates=True):
    access(db, wid, uid)
    try:
        parsed = PAYLOADS[kind].model_validate(payload)
    except (KeyError, ValidationError):
        raise HTTPException(422, "Invalid proposal payload") from None
    versions = {}
    if kind == "create_tasks":
        seen = set()
        for item in parsed.items:
            get_project(db, wid, item.project_id, writable=True)
            valid_assignee(db, wid, item.assignee_id)
            key = (item.project_id, item.title.casefold())
            if key in seen:
                raise HTTPException(409, "Duplicate task titles in proposal")
            seen.add(key)
            if check_duplicates and db.scalar(
                select(Task.id)
                .where(
                    Task.workspace_id == wid,
                    Task.project_id == item.project_id,
                    func.lower(func.trim(Task.title)) == item.title.lower(),
                    Task.deleted_at.is_(None),
                    Task.status != "done",
                )
                .limit(1)
            ):
                raise HTTPException(409, "An open task already matches this title")
    else:
        task = get_task(db, wid, parsed.task_id)
        get_project(db, wid, task.project_id, writable=True)
        versions[task.id] = parsed.version
        if creation and task.version != parsed.version:
            raise HTTPException(409, "Target changed; read it again before proposing")
        if kind == "reassign_task":
            valid_assignee(db, wid, parsed.assignee_id)
    # Changes uses exclude_unset to preserve exactly which fields are changed.
    result = parsed.model_dump(mode="json")
    if kind == "update_task":
        result["changes"] = parsed.changes.model_dump(mode="json", exclude_unset=True)
    if len(canonical(result)) > 55000:
        raise HTTPException(422, "Proposal is too large")
    return result, versions


def validate_sources(db, run, sources):
    values = sources or [{"type": "message", "id": run.trigger_message_id}]
    if len(values) > 10:
        raise HTTPException(422, "Too many sources")
    result = []
    for raw in values:
        try:
            source = Source.model_validate(raw)
        except ValidationError:
            raise HTTPException(422, "Invalid source") from None
        if source.type == "message":
            m = db.scalar(
                select(Message).where(
                    Message.workspace_id == run.workspace_id,
                    Message.id == source.id,
                    Message.channel_id == run.channel_id,
                    Message.deleted_at.is_(None),
                )
            )
            if not m:
                raise HTTPException(404, "Source unavailable")
            channel_access(db, run.workspace_id, m.channel_id, run.requester_id)
        else:
            get_task(db, run.workspace_id, source.id)
        result.append(source.model_dump())
    return result


def sync_items(db, p):
    db.execute(delete(ProposalItem).where(ProposalItem.proposal_id == p.id))
    for index, item in enumerate(p.payload.get("items", [])):
        db.add(
            ProposalItem(
                workspace_id=p.workspace_id,
                proposal_id=p.id,
                item_key=item["item_id"],
                position=index,
                payload=item,
            )
        )


def proposal_out(db, p):
    requester = db.get(User, p.requested_by)
    decider = db.get(User, p.decided_by) if p.decided_by else None
    sources = []
    for source in p.sources:
        if source["type"] == "task":
            t = db.get(Task, source["id"])
            if not t or t.deleted_at:
                continue
            sources.append({**source, "label": t.key, "url": "/tasks?task=" + t.id})
        else:
            m = db.get(Message, source["id"])
            if not m or m.deleted_at:
                continue
            sources.append(
                {
                    **source,
                    "label": "Conversation",
                    "url": f"/channels?channel={p.channel_id}&message={m.id}",
                }
            )
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "run_id": p.run_id,
        "channel_id": p.channel_id,
        "trigger_message_id": p.trigger_message_id,
        "kind": p.kind,
        "risk": p.risk,
        "status": p.status,
        "payload": p.payload,
        "payload_hash": p.payload_hash,
        "sources": sources,
        "requested_by": {"id": requester.id, "name": requester.name},
        "decided_by": {"id": decider.id, "name": decider.name} if decider else None,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "decision_reason": p.decision_reason,
        "execution_result": p.execution_result,
        "expires_at": p.expires_at.isoformat(),
        "created_at": p.created_at.isoformat(),
        "version": p.version,
        "required_role": required_role(db, p),
    }


def required_role(db, p):
    return (
        "admin"
        if p.risk == "high"
        else configuration(db, p.workspace_id).create_tasks_approver
        if p.kind == "create_tasks"
        else "editor"
    )


def proposal_audit(db, p, action, actor_type, actor_id, request_id, arguments=None):
    event = audit(
        db,
        p.workspace_id,
        actor_type,
        actor_id,
        action,
        "proposal",
        p.id,
        status=p.status,
        arguments={
            "kind": p.kind,
            "risk": p.risk,
            "version": p.version,
            "payload_hash": p.payload_hash,
            **(arguments or {}),
        },
        request_id=request_id,
    )
    event.approval_id, event.approval_status = p.id, p.status


def publish(db, p, kind="proposal.updated"):
    record_event(db, db.get(Channel, p.channel_id), kind, {"proposal": proposal_out(db, p)})


def transition(db, p, status, actor_type, actor_id, request_id, *, action=None, arguments=None):
    p.status = status
    p.version += 1
    proposal_audit(
        db, p, action or "proposal." + status, actor_type, actor_id, request_id, arguments
    )
    db.flush()
    publish(db, p, "proposal.executed" if status == "completed" else "proposal.updated")


def create_proposal(db, run, kind, payload, sources=None):
    access(db, run.workspace_id, run.requester_id, lock=True)
    run_access(db, run)
    data, versions = validate_payload(
        db, run.workspace_id, run.requester_id, kind, payload, creation=True, check_duplicates=False
    )
    refs = validate_sources(db, run, sources)
    key = digest({"kind": kind, "payload": data, "sources": refs})
    existing = db.scalar(
        select(Proposal).where(Proposal.run_id == run.id, Proposal.tool_key == key)
    )
    if existing:
        return existing
    validate_payload(db, run.workspace_id, run.requester_id, kind, data, creation=True)
    pending = db.scalar(
        select(func.count())
        .select_from(Proposal)
        .where(
            Proposal.workspace_id == run.workspace_id,
            Proposal.channel_id == run.channel_id,
            Proposal.status == "proposed",
            Proposal.expires_at > now(),
        )
    )
    if pending >= settings.proposal_pending_per_channel:
        raise HTTPException(429, "Review existing proposals in this channel first")
    p = Proposal(
        workspace_id=run.workspace_id,
        run_id=run.id,
        trigger_message_id=run.trigger_message_id,
        channel_id=run.channel_id,
        kind=kind,
        risk="high" if kind in HIGH else "low",
        payload=data,
        payload_hash=digest(data),
        tool_key=key,
        sources=refs,
        target_versions=versions,
        requested_by=run.requester_id,
        status="proposed",
        version=1,
        expires_at=now() + timedelta(days=settings.proposal_expiry_days),
    )
    db.add(p)
    db.flush()
    sync_items(db, p)
    proposal_audit(db, p, "proposal.created", "agent", run.workspace_id, run.request_id)
    publish(db, p, "proposal.created")
    return p


def get_proposal(db, wid, pid, uid, *, lock=False):
    access(db, wid, uid, lock=lock)
    query = (
        select(Proposal)
        .where(Proposal.workspace_id == wid, Proposal.id == pid)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    p = db.scalar(query)
    if not p:
        raise HTTPException(404, "Proposal unavailable")
    channel_access(db, wid, p.channel_id, uid, lock=lock)
    return p


def execute_payload(db, p, uid):
    data = p.payload
    changed, comments = [], []
    if p.kind == "create_tasks":
        mapping = {}
        for item in data["items"]:
            task = create_task(
                db,
                p.workspace_id,
                TaskInput.model_validate(
                    {k: v for k, v in item.items() if k not in {"item_id", "depends_on"}}
                ),
                uid,
                created_by_agent=True,
            )
            mapping[item["item_id"]] = task
            changed.append(task)
        for item in data["items"]:
            for dependency in item["depends_on"]:
                source, target = mapping[item["item_id"]], mapping[dependency]
                create_link(
                    db,
                    p.workspace_id,
                    LinkInput(
                        source_type="task",
                        source_id=source.id,
                        target_type="task",
                        target_id=target.id,
                        relation="depends_on",
                        version=source.version,
                    ),
                    uid,
                    check_version=False,
                )
    else:
        task = get_task(db, p.workspace_id, data["task_id"])
        if p.kind == "delete_task":
            soft_delete_task(db, task, uid, data["version"])
        elif p.kind == "add_comment":
            comments.append(add_task_comment(db, task, data["body"], uid).id)
        else:
            changes = (
                data["changes"]
                if p.kind == "update_task"
                else {"assignee_id": data["assignee_id"]}
                if p.kind == "reassign_task"
                else {"priority": data["priority"]}
            )
            update_task(db, task, changes, uid, data["version"])
        changed.append(task)
    for task in changed:
        # Public task activity contains attribution, never private channel/source text.
        activity(
            db,
            task,
            uid,
            "agent_approved",
            "proposal",
            None,
            {"proposal_id": p.id, "proposed_by": "Agent", "approved_by": uid},
        )
    return {"task_ids": [t.id for t in changed], "comment_ids": comments}


def decide(db, p, uid, data, action, request_id):
    member = access(db, p.workspace_id, uid)
    if action == "cancel":
        if uid != p.requested_by and LEVEL[member.role] < LEVEL["admin"]:
            raise HTTPException(403, "Only the requester or an Admin can cancel")
    elif LEVEL[member.role] < LEVEL[required_role(db, p)]:
        raise HTTPException(
            403,
            "Only an Admin can approve this"
            if required_role(db, p) == "admin"
            else "An Editor or Admin must decide this proposal",
        )
    # Only an exact retry of a successful operation is idempotently acknowledged.
    if (
        p.status == "completed"
        and action in {"approve", "edit-approve"}
        and p.decision_key == data.idempotency_key
        and p.decided_by == uid
    ):
        return p
    if p.status != "proposed":
        raise HTTPException(409, "This proposal has already been decided")
    if p.expires_at <= now():
        transition(db, p, "expired", "system", None, request_id)
        return p
    if (
        p.version != data.version
        or p.payload_hash != data.payload_hash
        or digest(p.payload) != p.payload_hash
    ):
        raise HTTPException(409, "Proposal changed. Reload and review it again.")
    p.decided_by, p.decided_at, p.decision_reason, p.decision_key = (
        uid,
        now(),
        data.reason,
        data.idempotency_key,
    )
    if action in {"reject", "cancel"}:
        transition(
            db,
            p,
            "rejected",
            "user",
            uid,
            request_id,
            action="proposal.cancelled" if action == "cancel" else None,
        )
        return p
    # Compare captured target versions before edits; edits cannot silently rebase a stale target.
    for task_id, version in p.target_versions.items():
        t = db.scalar(select(Task).where(Task.workspace_id == p.workspace_id, Task.id == task_id))
        if not t or t.deleted_at or t.version != version:
            transition(db, p, "stale", "system", None, request_id)
            return p
    if action == "edit-approve":
        payload, _ = validate_payload(db, p.workspace_id, uid, p.kind, data.payload)
        if p.kind == "create_tasks":
            if not {i["item_id"] for i in payload["items"]} <= {
                i["item_id"] for i in p.payload["items"]
            }:
                raise HTTPException(422, "Only edit or remove existing proposal items")
        elif (
            payload["task_id"] != p.payload["task_id"] or payload["version"] != p.payload["version"]
        ):
            raise HTTPException(
                422, "A reviewed proposal cannot be redirected to a different target"
            )
        previous_hash = p.payload_hash
        p.payload, p.payload_hash = payload, digest(payload)
        sync_items(db, p)
        p.version += 1
        proposal_audit(
            db,
            p,
            "proposal.edited",
            "user",
            uid,
            request_id,
            {"previous_payload_hash": previous_hash},
        )
        publish(db, p)
    transition(db, p, "approved", "user", uid, request_id)
    try:
        # Roll back *all* domain changes on any failed item, retaining the failed lifecycle.
        with db.begin_nested():
            validate_payload(db, p.workspace_id, uid, p.kind, p.payload)
            result = execute_payload(db, p, uid)
            db.flush()
    except (HTTPException, SQLAlchemyError):
        transition(db, p, "failed", "system", None, request_id)
        return p
    p.execution_result, p.executed_at = result, now()
    transition(
        db,
        p,
        "completed",
        "system",
        None,
        request_id,
        arguments={"approver": uid, "task_count": len(result["task_ids"])},
    )
    return p


def expire_pending(db, request_id):
    workspaces = list(
        db.scalars(
            select(Proposal.workspace_id)
            .where(Proposal.status == "proposed", Proposal.expires_at <= now())
            .distinct()
            .limit(20)
        )
    )
    for wid in workspaces:
        locked = db.scalar(
            select(Workspace.id).where(Workspace.id == wid).with_for_update(skip_locked=True)
        )
        if not locked:
            continue
        for p in db.scalars(
            select(Proposal)
            .where(
                Proposal.workspace_id == wid,
                Proposal.status == "proposed",
                Proposal.expires_at <= now(),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        ):
            transition(db, p, "expired", "system", None, request_id)
