from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import new_id


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_document_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"]
        ),
        CheckConstraint(
            "type IN ('spec','meeting_notes','adr','bug_postmortem')", name="ck_document_type"
        ),
        CheckConstraint("revision >= 1", name="ck_document_revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(240))
    type: Mapped[str] = mapped_column(String(24))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[bytes] = mapped_column(LargeBinary, default=b"\x00\x00")
    plain_text: Mapped[str] = mapped_column(Text, default="")
    markdown: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    last_editor: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def scoped():
    return ForeignKeyConstraint(
        ["workspace_id", "document_id"],
        ["documents.workspace_id", "documents.id"],
        ondelete="CASCADE",
    )


class DocumentMember(Base):
    __tablename__ = "document_members"
    __table_args__ = (
        scoped(),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)


class DocumentUpdate(Base):
    __tablename__ = "document_updates"
    __table_args__ = (
        scoped(),
        UniqueConstraint(
            "workspace_id", "document_id", "revision", name="uq_document_update_revision"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    update: Mapped[bytes] = mapped_column(LargeBinary)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (scoped(),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[bytes] = mapped_column(LargeBinary)
    markdown: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(String(24), default="user")
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("proposals.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentSuggestion(Base):
    __tablename__ = "document_suggestions"
    __table_args__ = (
        scoped(),
        ForeignKeyConstraint(
            ["workspace_id", "proposal_id"], ["proposals.workspace_id", "proposals.id"]
        ),
        UniqueConstraint("proposal_id", name="uq_document_suggestion_proposal"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    proposal_id: Mapped[str] = mapped_column(String(36))
    from_anchor: Mapped[str] = mapped_column(Text)
    to_anchor: Mapped[str] = mapped_column(Text)
    expected_text: Mapped[str] = mapped_column(Text)
    replacement: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
