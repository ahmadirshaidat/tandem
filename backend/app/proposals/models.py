"""Validated proposal records; only the human decision service can execute them."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import new_id


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    trigger_message_id: Mapped[str] = mapped_column(String(36))
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    risk: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    tool_key: Mapped[str] = mapped_column(String(64))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    target_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_result: Mapped[dict | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    decision_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_proposal_scope"),
        UniqueConstraint("run_id", "tool_key", name="uq_proposal_tool_key"),
        ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["agent_runs.workspace_id", "agent_runs.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "channel_id", "trigger_message_id"],
            ["messages.workspace_id", "messages.channel_id", "messages.id"],
        ),
        CheckConstraint(
            "kind IN ('create_tasks','update_task','reassign_task','change_priority','delete_task','add_comment')",
            name="ck_proposal_kind",
        ),
        CheckConstraint(
            "(kind IN ('reassign_task','change_priority','delete_task') AND risk = 'high') OR (kind IN ('create_tasks','update_task','add_comment') AND risk = 'low')",
            name="ck_proposal_risk",
        ),
        CheckConstraint(
            "status IN ('proposed','approved','completed','rejected','failed','expired','stale') AND version > 0",
            name="ck_proposal_state",
        ),
        Index("ix_proposal_pending", "workspace_id", "channel_id", "status", "expires_at"),
    )


class ProposalItem(Base):
    __tablename__ = "proposal_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    proposal_id: Mapped[str] = mapped_column(String(36), index=True)
    item_key: Mapped[str] = mapped_column(String(36))
    position: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "proposal_id"],
            ["proposals.workspace_id", "proposals.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("proposal_id", "item_key", name="uq_proposal_item"),
        CheckConstraint("position >= 0 AND position < 10", name="ck_proposal_item_position"),
    )
