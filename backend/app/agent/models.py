"""Workspace-scoped agent metadata. Content lives only in channel messages."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import new_id


class AgentSettings(Base):
    __tablename__ = "agent_settings"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_chain: Mapped[list] = mapped_column(JSON, default=lambda: ["groq", "gemini"])
    create_tasks_approver: Mapped[str] = mapped_column(
        String(8), default="editor", server_default="editor"
    )
    monthly_run_limit: Mapped[int] = mapped_column(Integer, default=1000)
    pause_at_limit: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint("monthly_run_limit >= 1", name="ck_agent_limit"),
        CheckConstraint("create_tasks_approver IN ('editor','admin')", name="ck_approval_rule"),
    )


class AgentChannelAccess(Base):
    __tablename__ = "agent_channel_access"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "channel_id"], ["channels.workspace_id", "channels.id"]
        ),
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    channel_id: Mapped[str] = mapped_column(String(36))
    trigger_message_id: Mapped[str] = mapped_column(String(36), unique=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    provider: Mapped[str | None] = mapped_column(String(24))
    model: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_category: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(36), default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_agent_run_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "channel_id", "trigger_message_id"],
            ["messages.workspace_id", "messages.channel_id", "messages.id"],
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed','blocked')", name="ck_agent_status"
        ),
        Index("ix_agent_queue", "status", "created_at"),
    )


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    tool_name: Mapped[str] = mapped_column(String(64))
    redacted_arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["agent_runs.workspace_id", "agent_runs.id"]
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(12))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[str | None] = mapped_column(String(36))
    redacted_arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result_status: Mapped[str] = mapped_column(String(24))
    approval_id: Mapped[str | None] = mapped_column(String(36))
    approval_status: Mapped[str | None] = mapped_column(String(24))
    request_id: Mapped[str] = mapped_column(String(36), default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("actor_type IN ('user','agent','system')", name="ck_audit_actor"),
        Index("ix_audit_page", "workspace_id", "created_at", "id"),
    )
