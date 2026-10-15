from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import new_id


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_project_key"),
        UniqueConstraint("workspace_id", "id", name="uq_project_scope"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(10))
    color: Mapped[str] = mapped_column(String(12), default="brand")
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceTaskState(Base):
    __tablename__ = "workspace_task_state"
    __table_args__ = (
        CheckConstraint("last_number >= 0 AND last_seq >= 0", name="ck_workspace_task_state"),
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer, default=0)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number", name="uq_task_number"),
        UniqueConstraint("workspace_id", "key", name="uq_task_key"),
        UniqueConstraint("workspace_id", "id", name="uq_task_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"]
        ),
        CheckConstraint("type IN ('bug','task')", name="ck_task_type"),
        CheckConstraint("status IN ('todo','in_progress','done')", name="ck_task_status"),
        CheckConstraint("priority IN ('P1','P2','P3')", name="ck_task_priority"),
        CheckConstraint(
            "version > 0 AND number > 0 AND comment_count >= 0", name="ck_task_counters"
        ),
        Index("ix_task_board", "workspace_id", "project_id", "status", "rank", "id"),
        Index("ix_task_updated", "workspace_id", "updated_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    number: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(8), default="task")
    status: Mapped[str] = mapped_column(String(16), default="todo")
    priority: Mapped[str] = mapped_column(String(2), default="P2")
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    rank: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def task_fk():
    return ForeignKeyConstraint(
        ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="CASCADE"
    )


class TaskComment(Base):
    __tablename__ = "task_comments"
    __table_args__ = (
        task_fk(),
        CheckConstraint("version > 0 AND char_length(body) <= 4000", name="ck_task_comment_body"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskActivity(Base):
    __tablename__ = "task_activity"
    __table_args__ = (task_fk(), Index("ix_task_activity_order", "task_id", "created_at", "id"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(32))
    old_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    link_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation",
            name="uq_link_edge",
        ),
        CheckConstraint(
            "source_type IN ('message','task','document') AND target_type IN ('message','task','document')",
            name="ck_link_types",
        ),
        CheckConstraint(
            "relation IN ('related','depends_on') AND (relation != 'depends_on' OR (source_type = 'task' AND target_type = 'task'))",
            name="ck_link_relation",
        ),
        CheckConstraint(
            "source_type != target_type OR source_id != target_id", name="ck_link_self"
        ),
        Index("ix_link_source", "workspace_id", "source_type", "source_id"),
        Index("ix_link_target", "workspace_id", "target_type", "target_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(12))
    source_id: Mapped[str] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(String(12))
    target_id: Mapped[str] = mapped_column(String(36))
    relation: Mapped[str] = mapped_column(String(16), default="related", server_default="related")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceEvent(Base):
    __tablename__ = "workspace_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "seq", name="uq_workspace_event_seq"),
        CheckConstraint("seq > 0", name="ck_workspace_event_seq"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
