import base64
import json
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.models import Channel
from app.channels.service import channel_access, channel_out, record_event
from app.core.db import get_db
from app.core.models import User
from app.core.security import csrf_check, current_user, now
from app.tasks.models import Link, Project, Task, TaskActivity, TaskComment, WorkspaceTaskState
from app.tasks.schemas import (
    BulkTaskInput,
    ChannelProjectInput,
    CommentInput,
    CommentUpdate,
    FromMessageInput,
    LinkInput,
    Priority,
    ProjectInput,
    ProjectUpdate,
    Status,
    TaskDelete,
    TaskInput,
    TaskMove,
    TaskType,
    TaskUpdate,
)
from app.tasks.service import (
    LINK_NOT_FOUND,
    access,
    activity,
    actor_out,
    add_task_comment,
    comment_out,
    create_link,
    create_task,
    event,
    get_project,
    get_task,
    iso,
    project_out,
    require_version,
    resolve_item,
    soft_delete_task,
    task_out,
    tasks_out,
    update_task,
    visible_link,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["projects and tasks"])
write = [Depends(csrf_check)]


@router.get("/projects")
def list_projects(
    workspace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    access(db, workspace_id, user.id)
    return [
        project_out(p)
        for p in db.scalars(
            select(Project)
            .where(Project.workspace_id == workspace_id, Project.deleted_at.is_(None))
            .order_by(Project.created_at, Project.id)
        )
    ]


@router.post("/projects", status_code=201, dependencies=write)
def new_project(
    workspace_id: str,
    data: ProjectInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    project = Project(workspace_id=workspace_id, **data.model_dump())
    db.add(project)
    try:
        db.flush()
        event(db, workspace_id, "project.updated", {"project": project_out(project)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This project key is unavailable") from None
    return project_out(project)


@router.get("/projects/{project_id}")
def project_detail(
    workspace_id: str,
    project_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    return project_out(get_project(db, workspace_id, project_id))


@router.patch("/projects/{project_id}", dependencies=write)
def edit_project(
    workspace_id: str,
    project_id: str,
    data: ProjectUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    project = get_project(db, workspace_id, project_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None or (key == "name" and not value.strip()):
            raise HTTPException(422, "Project fields cannot be blank")
        setattr(project, key, value.strip() if key == "name" else value)
    project.updated_at = now()
    event(db, workspace_id, "project.updated", {"project": project_out(project)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This project key is unavailable") from None
    return project_out(project)


@router.delete("/projects/{project_id}", status_code=204, dependencies=write)
def delete_project(
    workspace_id: str,
    project_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    project = get_project(db, workspace_id, project_id)
    if db.scalar(
        select(Task.id).where(Task.project_id == project.id, Task.deleted_at.is_(None)).limit(1)
    ) or db.scalar(select(Channel.id).where(Channel.project_id == project.id).limit(1)):
        raise HTTPException(409, "This project still has work. Archive it instead.")
    project.deleted_at, project.updated_at = now(), now()
    event(db, workspace_id, "project.updated", {"project": project_out(project)})
    db.commit()


@router.patch("/channels/{channel_id}/project", dependencies=write)
def link_channel_project(
    workspace_id: str,
    channel_id: str,
    data: ChannelProjectInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    channel, _ = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    access(db, workspace_id, user.id, "admin")
    if data.project_id:
        get_project(db, workspace_id, data.project_id, writable=True)
    channel.project_id = data.project_id
    record_event(db, channel, "channel.updated", {"channel_id": channel.id})
    db.commit()
    return channel_out(db, channel, user.id)


def cursor_encode(sort, direction, value, task_id):
    return (
        base64.urlsafe_b64encode(json.dumps([sort, direction, iso(value), task_id]).encode())
        .decode()
        .rstrip("=")
    )


def cursor_decode(raw, sort, direction, column):
    try:
        a, b, value, task_id = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if a != sort or b != direction or not isinstance(task_id, str) or len(task_id) > 36:
            raise ValueError
        if sort == "rank":
            value = Decimal(value)
            if not value.is_finite():
                raise ValueError
        elif sort == "number":
            value = int(value)
        elif sort in {"updated", "created"}:
            value = datetime.fromisoformat(value)
        elif not isinstance(value, str) or len(value) > 240:
            raise ValueError
        predicate = column < value if direction == "desc" else column > value
        return or_(
            predicate,
            and_(column == value, Task.id < task_id if direction == "desc" else Task.id > task_id),
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(422, "Invalid task page cursor") from None


@router.get("/tasks")
def list_tasks(
    workspace_id: str,
    project_id: str | None = Query(default=None, max_length=36),
    status: Status | None = None,
    assignee: str | None = Query(default=None, max_length=36),
    priority: Priority | None = None,
    type: TaskType | None = None,
    text: str | None = Query(default=None, max_length=240),
    sort: str = Query(
        default="rank",
        pattern=r"^(rank|number|title|status|priority|assignee|due|updated|created)$",
    ),
    direction: str = Query(default="asc", pattern=r"^(asc|desc)$"),
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=100, ge=1, le=1000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    counter = db.get(WorkspaceTaskState, workspace_id)
    last_seq = counter.last_seq if counter else 0
    query = select(Task).where(Task.workspace_id == workspace_id, Task.deleted_at.is_(None))
    if project_id:
        get_project(db, workspace_id, project_id)
        query = query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status == status)
    if assignee:
        query = query.where(
            Task.assignee_id.is_(None) if assignee == "unassigned" else Task.assignee_id == assignee
        )
    if priority:
        query = query.where(Task.priority == priority)
    if type:
        query = query.where(Task.type == type)
    if text:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                Task.title.ilike(f"%{escaped}%", escape="\\"),
                Task.description.ilike(f"%{escaped}%", escape="\\"),
                Task.key.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    counts = dict(
        db.execute(
            select(Task.status, func.count()).where(query.whereclause).group_by(Task.status)
        ).all()
    )
    columns = {
        "rank": Task.rank,
        "number": Task.number,
        "title": Task.title,
        "status": Task.status,
        "priority": Task.priority,
        "assignee": func.coalesce(Task.assignee_id, ""),
        "due": func.coalesce(func.to_char(Task.due_date, "YYYY-MM-DD"), "9999-12-31"),
        "updated": Task.updated_at,
        "created": Task.created_at,
    }
    column = columns[sort]
    if cursor:
        query = query.where(cursor_decode(cursor, sort, direction, column))
    order = column.desc() if direction == "desc" else column.asc()
    rows = list(
        db.scalars(
            query.order_by(order, Task.id.desc() if direction == "desc" else Task.id).limit(
                limit + 1
            )
        )
    )
    page = rows[:limit]
    last = page[-1] if page else None
    value = (
        getattr(last, {"updated": "updated_at", "created": "created_at"}.get(sort, sort), None)
        if last
        else None
    )
    if last and sort == "assignee":
        value = last.assignee_id or ""
    if last and sort == "due":
        value = iso(last.due_date) or "9999-12-31"
    return {
        "tasks": tasks_out(db, page),
        "next_cursor": cursor_encode(sort, direction, value, last.id)
        if len(rows) > limit
        else None,
        "last_seq": last_seq,
        "total": sum(counts.values()),
        "counts": {key: counts.get(key, 0) for key in ["todo", "in_progress", "done"]},
    }


@router.post("/tasks", status_code=201, dependencies=write)
def new_task(
    workspace_id: str,
    data: TaskInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    task = create_task(db, workspace_id, data, user.id)
    db.commit()
    return task_out(db, task)


@router.post("/tasks/from-message", status_code=201, dependencies=write)
def task_from_message(
    workspace_id: str,
    data: FromMessageInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    resolve_item(db, workspace_id, "message", data.message_id, user.id)
    task = create_task(db, workspace_id, data, user.id)
    create_link(
        db,
        workspace_id,
        LinkInput(
            source_type="task",
            source_id=task.id,
            target_type="message",
            target_id=data.message_id,
            version=task.version,
        ),
        user.id,
        check_version=False,
    )
    db.commit()
    return task_out(db, task)


@router.post("/tasks/bulk", dependencies=write)
def bulk_tasks(
    workspace_id: str,
    data: BulkTaskInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    if len({item.id for item in data.tasks}) != len(data.tasks):
        raise HTTPException(422, "Select each task only once")
    changes = data.model_dump(exclude={"tasks"}, exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Choose a bulk change")
    tasks = [get_task(db, workspace_id, item.id) for item in data.tasks]
    for task, item in zip(tasks, data.tasks, strict=True):
        require_version(db, task, item.version)
    for task in tasks:
        update_task(db, task, changes.copy(), user.id, task.version)
    db.commit()
    return tasks_out(db, tasks)


@router.get("/tasks/{task_id}")
def task_detail(
    workspace_id: str,
    task_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    return task_out(db, get_task(db, workspace_id, task_id))


@router.patch("/tasks/{task_id}", dependencies=write)
def edit_task(
    workspace_id: str,
    task_id: str,
    data: TaskUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    task = get_task(db, workspace_id, task_id)
    update_task(
        db, task, data.model_dump(exclude_unset=True, exclude={"version"}), user.id, data.version
    )
    db.commit()
    return task_out(db, task)


@router.post("/tasks/{task_id}/move", dependencies=write)
def move_task(
    workspace_id: str,
    task_id: str,
    data: TaskMove,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    task = get_task(db, workspace_id, task_id)
    update_task(
        db,
        task,
        {"status": data.status},
        user.id,
        data.version,
        moving=True,
        before_id=data.before_id,
        after_id=data.after_id,
    )
    db.commit()
    return task_out(db, task)


@router.delete("/tasks/{task_id}", status_code=204, dependencies=write)
def delete_task(
    workspace_id: str,
    task_id: str,
    data: TaskDelete,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    task = get_task(db, workspace_id, task_id)
    soft_delete_task(db, task, user.id, data.version)
    db.commit()


@router.get("/tasks/{task_id}/comments")
def task_comments(
    workspace_id: str,
    task_id: str,
    before: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    task = get_task(db, workspace_id, task_id)
    query = select(TaskComment).where(TaskComment.task_id == task.id)
    if before:
        anchor = db.scalar(
            select(TaskComment).where(TaskComment.task_id == task.id, TaskComment.id == before)
        )
        if not anchor:
            raise HTTPException(422, "Invalid comment cursor")
        query = query.where(
            or_(
                TaskComment.created_at < anchor.created_at,
                and_(TaskComment.created_at == anchor.created_at, TaskComment.id < anchor.id),
            )
        )
    rows = list(
        db.scalars(
            query.order_by(TaskComment.created_at.desc(), TaskComment.id.desc()).limit(limit + 1)
        )
    )
    return {
        "comments": [comment_out(db, c) for c in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.post("/tasks/{task_id}/comments", status_code=201, dependencies=write)
def new_comment(
    workspace_id: str,
    task_id: str,
    data: CommentInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    task = get_task(db, workspace_id, task_id)
    comment = add_task_comment(db, task, data.body, user.id)
    db.commit()
    return comment_out(db, comment)


@router.patch("/tasks/{task_id}/comments/{comment_id}", dependencies=write)
def edit_comment(
    workspace_id: str,
    task_id: str,
    comment_id: str,
    data: CommentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    task = get_task(db, workspace_id, task_id)
    comment = db.scalar(
        select(TaskComment).where(
            TaskComment.task_id == task.id,
            TaskComment.id == comment_id,
            TaskComment.deleted_at.is_(None),
        )
    )
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.author_id != user.id:
        raise HTTPException(403, "You can edit only your own comments")
    if comment.version != data.version:
        raise HTTPException(409, "This comment changed. Reload it and try again.")
    activity(db, task, user.id, "comment_edited", "comment", comment.body, data.body)
    comment.body, comment.edited_at = data.body, now()
    comment.version += 1
    task.version += 1
    task.updated_at = now()
    event(db, workspace_id, "task.updated", {"comment": comment_out(db, comment)}, task)
    db.commit()
    return comment_out(db, comment)


@router.delete("/tasks/{task_id}/comments/{comment_id}", status_code=204, dependencies=write)
def delete_comment(
    workspace_id: str,
    task_id: str,
    comment_id: str,
    version: int = Query(ge=1),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    member = access(db, workspace_id, user.id, "editor", lock=True)
    task = get_task(db, workspace_id, task_id)
    comment = db.scalar(
        select(TaskComment).where(
            TaskComment.task_id == task.id,
            TaskComment.id == comment_id,
            TaskComment.deleted_at.is_(None),
        )
    )
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.author_id != user.id and member.role not in {"owner", "admin"}:
        raise HTTPException(403, "You can delete only your own comments")
    if comment.version != version:
        raise HTTPException(409, "This comment changed. Reload it and try again.")
    activity(db, task, user.id, "comment_deleted", "comment", comment.body, None)
    comment.body, comment.deleted_at = "", now()
    comment.version += 1
    task.comment_count -= 1
    task.version += 1
    task.updated_at = now()
    event(db, workspace_id, "task.updated", {"comment": comment_out(db, comment)}, task)
    db.commit()


@router.get("/tasks/{task_id}/activity")
def task_activity(
    workspace_id: str,
    task_id: str,
    before: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    task = get_task(db, workspace_id, task_id)
    query = select(TaskActivity).where(TaskActivity.task_id == task.id)
    if before:
        anchor = db.scalar(
            select(TaskActivity).where(TaskActivity.task_id == task.id, TaskActivity.id == before)
        )
        if not anchor or (
            anchor.link_id and not visible_link(db, db.get(Link, anchor.link_id), user.id)
        ):
            raise HTTPException(422, "Invalid activity cursor")
        query = query.where(
            or_(
                TaskActivity.created_at < anchor.created_at,
                and_(TaskActivity.created_at == anchor.created_at, TaskActivity.id < anchor.id),
            )
        )
    # Filter hidden links before pagination, so neither page counts nor cursors reveal them.
    result = []
    for item in db.scalars(query.order_by(TaskActivity.created_at.desc(), TaskActivity.id.desc())):
        if item.link_id:
            link = db.get(Link, item.link_id)
            if not link or not visible_link(db, link, user.id):
                continue
        result.append(
            {
                "id": item.id,
                "kind": item.kind,
                "field": item.field,
                "old_value": item.old_value,
                "new_value": item.new_value,
                "actor": actor_out(db.get(User, item.actor_id)),
                "created_at": iso(item.created_at),
            }
        )
        if len(result) > limit:
            break
    return {
        "activity": result[:limit],
        "next_cursor": result[limit - 1]["id"] if len(result) > limit else None,
    }


@router.post("/links", status_code=201, dependencies=write)
def new_link(
    workspace_id: str,
    data: LinkInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "editor", lock=True)
    link = create_link(db, workspace_id, data, user.id)
    db.commit()
    return visible_link(db, link, user.id)


@router.get("/links")
def list_links(
    workspace_id: str,
    object_type: str = Query(pattern=r"^(message|task)$"),
    object_id: str = Query(max_length=36),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    resolve_item(db, workspace_id, object_type, object_id, user.id)
    links = db.scalars(
        select(Link)
        .where(
            Link.workspace_id == workspace_id,
            or_(
                and_(Link.source_type == object_type, Link.source_id == object_id),
                and_(Link.target_type == object_type, Link.target_id == object_id),
            ),
        )
        .order_by(Link.created_at)
    )
    return [out for link in links if (out := visible_link(db, link, user.id))]


@router.get("/links/{link_id}")
def get_link(
    workspace_id: str,
    link_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id)
    link = db.scalar(select(Link).where(Link.workspace_id == workspace_id, Link.id == link_id))
    result = visible_link(db, link, user.id) if link else None
    if not result:
        raise HTTPException(404, LINK_NOT_FOUND)
    return result
