from datetime import date, datetime
from decimal import Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy import select

from app.channels.models import Message
from app.channels.service import channel_access
from app.core.models import User, Workspace, new_id
from app.core.security import now
from app.tasks.models import (
    Link,
    Project,
    Task,
    TaskActivity,
    TaskComment,
    WorkspaceEvent,
    WorkspaceTaskState,
)
from app.workspaces.permissions import membership

RANK_STEP = Decimal(1024)
MIN_RANK_GAP = Decimal("0.000000000000001")
NOT_FOUND = "Task not found or you do not have access"
LINK_NOT_FOUND = "Linked item not found or you do not have access"


def access(db, workspace_id, user_id, minimum="viewer", *, lock=False):
    if lock:
        db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    return membership(db, workspace_id, user_id, minimum)


def get_project(db, workspace_id, project_id, *, writable=False):
    project = db.scalar(
        select(Project)
        .where(
            Project.workspace_id == workspace_id,
            Project.id == project_id,
            Project.deleted_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if not project:
        raise HTTPException(404, "Project not found or you do not have access")
    if writable and project.archived:
        raise HTTPException(409, "This project is archived")
    return project


def get_task(db, workspace_id, task_id):
    task = db.scalar(
        select(Task)
        .where(Task.workspace_id == workspace_id, Task.id == task_id, Task.deleted_at.is_(None))
        .execution_options(populate_existing=True)
    )
    if not task:
        raise HTTPException(404, NOT_FOUND)
    return task


def project_out(project):
    return {
        key: iso(getattr(project, key))
        for key in [
            "id",
            "workspace_id",
            "name",
            "key",
            "color",
            "description",
            "archived",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
    }


def iso(value):
    return (
        value.isoformat()
        if isinstance(value, (date, datetime))
        else str(value)
        if isinstance(value, Decimal)
        else value
    )


def actor_out(user):
    return {"id": user.id, "name": user.name} if user else None


def tasks_out(db, tasks):
    if not tasks:
        return []
    ids = {task.reporter_id for task in tasks} | {
        task.assignee_id for task in tasks if task.assignee_id
    }
    actors = {user.id: actor_out(user) for user in db.scalars(select(User).where(User.id.in_(ids)))}
    return [task_out(db, task, actors) for task in tasks]


def task_out(db, task, actors=None):
    if actors is None:
        actors = {
            user.id: actor_out(user)
            for user in db.scalars(
                select(User).where(User.id.in_([task.reporter_id, task.assignee_id]))
            )
        }
    fields = [
        "id",
        "workspace_id",
        "project_id",
        "key",
        "number",
        "title",
        "description",
        "type",
        "status",
        "priority",
        "assignee_id",
        "due_date",
        "created_by_agent",
        "version",
        "rank",
        "comment_count",
        "last_event_seq",
        "created_at",
        "updated_at",
        "deleted_at",
    ]
    return {
        **{key: iso(getattr(task, key)) for key in fields},
        "reporter": actors[task.reporter_id],
        "assignee": actors.get(task.assignee_id),
    }


def comment_out(db, comment):
    return {
        "id": comment.id,
        "task_id": comment.task_id,
        "author": actor_out(db.get(User, comment.author_id)),
        "body": "" if comment.deleted_at else comment.body,
        "version": comment.version,
        "created_at": iso(comment.created_at),
        "edited_at": iso(comment.edited_at),
        "deleted_at": iso(comment.deleted_at),
    }


class TaskConflict(HTTPException):
    def __init__(self, current):
        super().__init__(409, "This task changed. Choose Keep mine or Take server's.")
        self.current_task = current


def require_version(db, task, expected):
    if task.version != expected:
        raise TaskConflict(task_out(db, task))


def state(db, workspace_id):
    record = db.get(WorkspaceTaskState, workspace_id)
    if not record:
        record = WorkspaceTaskState(workspace_id=workspace_id, last_number=0, last_seq=0)
        db.add(record)
        db.flush()
    return record


def event(db, workspace_id, kind, payload, task=None):
    counter = state(db, workspace_id)
    counter.last_seq += 1
    if task:
        task.last_event_seq = counter.last_seq
        db.flush()
        payload = {**payload, "task": task_out(db, task)}
    db.add(
        WorkspaceEvent(workspace_id=workspace_id, seq=counter.last_seq, type=kind, payload=payload)
    )
    return counter.last_seq


def activity(db, task, actor_id, kind, field, old, new, link_id=None):
    db.add(
        TaskActivity(
            workspace_id=task.workspace_id,
            task_id=task.id,
            actor_id=actor_id,
            kind=kind,
            field=field,
            old_value=iso(old),
            new_value=iso(new),
            link_id=link_id,
        )
    )


def valid_assignee(db, workspace_id, user_id):
    if user_id is not None:
        membership(db, workspace_id, user_id)


def rebalance(db, workspace_id, project_id, status, actor_id):
    rows = list(
        db.scalars(
            select(Task)
            .where(
                Task.workspace_id == workspace_id,
                Task.project_id == project_id,
                Task.status == status,
                Task.deleted_at.is_(None),
            )
            .order_by(Task.rank, Task.id)
        )
    )
    for index, task in enumerate(rows, 1):
        new_rank = RANK_STEP * index
        if task.rank == new_rank:
            continue
        activity(db, task, actor_id, "edited", "rank", task.rank, new_rank)
        task.rank = new_rank
        task.version += 1
        task.updated_at = now()
        event(db, workspace_id, "task.moved", {}, task)
    db.flush()


def rank_for(db, task, status, before_id=None, after_id=None, *, actor_id, rebalanced=False):
    query = select(Task).where(
        Task.workspace_id == task.workspace_id,
        Task.project_id == task.project_id,
        Task.status == status,
        Task.deleted_at.is_(None),
        Task.id != task.id,
    )

    def neighbor(task_id):
        other = get_task(db, task.workspace_id, task_id)
        if other.id == task.id or other.project_id != task.project_id or other.status != status:
            raise HTTPException(
                422, "Choose a neighboring task in this project's destination column"
            )
        return other

    before = neighbor(before_id) if before_id else None
    after = neighbor(after_id) if after_id else None
    if before and after and after.rank >= before.rank:
        raise HTTPException(409, "The column order changed. Choose a new position.")
    if before:
        previous = db.scalar(
            query.where(Task.rank < before.rank).order_by(Task.rank.desc()).limit(1)
        )
        if after and (not previous or previous.id != after.id):
            raise HTTPException(409, "The column order changed. Choose adjacent cards.")
        left, right = (previous.rank if previous else before.rank - RANK_STEP * 2), before.rank
    elif after:
        following = db.scalar(query.where(Task.rank > after.rank).order_by(Task.rank).limit(1))
        left, right = after.rank, following.rank if following else after.rank + RANK_STEP * 2
    else:
        last = db.scalar(query.order_by(Task.rank.desc()).limit(1))
        return (last.rank if last else Decimal(0)) + RANK_STEP
    if right - left < MIN_RANK_GAP:
        if rebalanced:
            raise HTTPException(409, "The column order changed. Please try again.")
        rebalance(db, task.workspace_id, task.project_id, status, actor_id)
        return rank_for(db, task, status, before_id, after_id, actor_id=actor_id, rebalanced=True)
    with localcontext() as context:
        context.prec = 50
        return (left + right) / 2


def create_task(db, workspace_id, data, user_id, *, created_by_agent=False):
    access(db, workspace_id, user_id, "editor", lock=True)
    get_project(db, workspace_id, data.project_id, writable=True)
    valid_assignee(db, workspace_id, data.assignee_id)
    counter = state(db, workspace_id)
    counter.last_number += 1
    values = data.model_dump(exclude={"message_id"})
    task = Task(
        workspace_id=workspace_id,
        reporter_id=user_id,
        number=counter.last_number,
        key=f"{'BUG' if data.type == 'bug' else 'TASK'}-{counter.last_number}",
        version=1,
        comment_count=0,
        created_by_agent=created_by_agent,
        last_event_seq=0,
        **values,
    )
    # A new card has no ID yet; rank_for excludes its generated identity safely.
    task.id = new_id()
    task.rank = rank_for(db, task, data.status, actor_id=user_id)
    db.add(task)
    db.flush()
    activity(db, task, user_id, "created", "task", None, {"title": task.title, "key": task.key})
    event(db, workspace_id, "task.created", {}, task)
    return task


def update_task(
    db, task, changes, user_id, expected, *, moving=False, before_id=None, after_id=None
):
    require_version(db, task, expected)
    get_project(db, task.workspace_id, changes.get("project_id", task.project_id), writable=True)
    if "assignee_id" in changes:
        valid_assignee(db, task.workspace_id, changes["assignee_id"])
    if "title" in changes:
        if not changes["title"] or not changes["title"].strip():
            raise HTTPException(422, "Enter a task title")
        changes["title"] = changes["title"].strip()
    for field in ["project_id", "description", "type", "status", "priority"]:
        if field in changes and changes[field] is None:
            raise HTTPException(422, "This task field cannot be null")
    changed = False
    kinds = {
        "status": "status_changed",
        "assignee_id": "assignee_changed",
        "priority": "priority_changed",
        "due_date": "due_date_changed",
    }
    old_status, old_project = task.status, task.project_id
    for field, value in changes.items():
        old = getattr(task, field)
        if old != value:
            activity(db, task, user_id, kinds.get(field, "edited"), field, old, value)
            setattr(task, field, value)
            changed = True
    if moving or old_status != task.status or old_project != task.project_id:
        rank = rank_for(db, task, task.status, before_id, after_id, actor_id=user_id)
        if rank != task.rank:
            activity(db, task, user_id, "edited", "rank", task.rank, rank)
            task.rank = rank
            changed = True
    if changed:
        task.version += 1
        task.updated_at = now()
        event(
            db,
            task.workspace_id,
            "task.moved" if moving or old_status != task.status else "task.updated",
            {},
            task,
        )
    return task


def resolve_item(db, workspace_id, kind, item_id, user_id):
    if kind == "task":
        task = get_task(db, workspace_id, item_id)
        return {
            "type": "task",
            "id": task.id,
            "label": f"{task.key}: {task.title}",
            "url": f"/tasks?task={task.id}",
            "task": task,
        }
    if kind == "message":
        message = db.scalar(
            select(Message).where(Message.workspace_id == workspace_id, Message.id == item_id)
        )
        if message:
            channel, _ = channel_access(db, workspace_id, message.channel_id, user_id)
            return {
                "type": "message",
                "id": message.id,
                "label": f"Conversation in #{channel.name}",
                "url": f"/channels?channel={channel.id}&message={message.id}",
                "message": message,
            }
    raise HTTPException(404, LINK_NOT_FOUND)


def visible_link(db, link, user_id):
    if not link:
        return None
    try:
        source = resolve_item(db, link.workspace_id, link.source_type, link.source_id, user_id)
        target = resolve_item(db, link.workspace_id, link.target_type, link.target_id, user_id)
    except HTTPException:
        return None
    return {
        "id": link.id,
        "relation": link.relation,
        "source": {key: value for key, value in source.items() if key not in {"message", "task"}},
        "target": {key: value for key, value in target.items() if key not in {"message", "task"}},
    }


def create_link(db, workspace_id, data, user_id, *, check_version=True):
    source = resolve_item(db, workspace_id, data.source_type, data.source_id, user_id)
    target = resolve_item(db, workspace_id, data.target_type, data.target_id, user_id)
    tasks = [item["task"] for item in [source, target] if "task" in item]
    if not tasks or (data.source_type == data.target_type and data.source_id == data.target_id):
        raise HTTPException(422, "A link must connect a task to a different task or message")
    existing = db.scalar(
        select(Link).where(
            Link.workspace_id == workspace_id,
            Link.source_type == data.source_type,
            Link.source_id == data.source_id,
            Link.target_type == data.target_type,
            Link.target_id == data.target_id,
            Link.relation == data.relation,
        )
    )
    if existing:
        return existing
    if check_version:
        require_version(db, tasks[0], data.version)
    link = Link(
        workspace_id=workspace_id,
        source_type=data.source_type,
        source_id=data.source_id,
        target_type=data.target_type,
        target_id=data.target_id,
        created_by=user_id,
        relation=data.relation,
    )
    db.add(link)
    db.flush()
    for task in tasks:
        activity(
            db,
            task,
            user_id,
            "linked",
            "link",
            None,
            {
                "source_type": link.source_type,
                "source_id": link.source_id,
                "target_type": link.target_type,
                "target_id": link.target_id,
            },
            link.id,
        )
        task.version += 1
        task.updated_at = now()
        event(db, workspace_id, "task.updated", {}, task)
    return link


def unassign_removed_member(db, workspace_id, user_id, actor_id):
    for task in db.scalars(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.assignee_id == user_id,
            Task.deleted_at.is_(None),
        )
    ):
        activity(db, task, actor_id, "assignee_changed", "assignee_id", user_id, None)
        task.assignee_id = None
        task.version += 1
        task.updated_at = now()
        event(db, workspace_id, "task.updated", {}, task)


def add_task_comment(db, task, body, user_id):
    access(db, task.workspace_id, user_id, "editor", lock=True)
    get_project(db, task.workspace_id, task.project_id, writable=True)
    comment = TaskComment(
        workspace_id=task.workspace_id, task_id=task.id, author_id=user_id, body=body
    )
    db.add(comment)
    db.flush()
    activity(
        db, task, user_id, "commented", "comment", None, {"id": comment.id, "body": comment.body}
    )
    task.comment_count += 1
    task.version += 1
    task.updated_at = now()
    event(
        db, task.workspace_id, "task.comment_created", {"comment": comment_out(db, comment)}, task
    )
    return comment


def soft_delete_task(db, task, user_id, version):
    access(db, task.workspace_id, user_id, "admin", lock=True)
    require_version(db, task, version)
    activity(db, task, user_id, "deleted", "deleted_at", None, now())
    task.deleted_at, task.updated_at = now(), now()
    task.version += 1
    event(db, task.workspace_id, "task.deleted", {}, task)
