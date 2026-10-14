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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import new_id


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_channel_name"),
        UniqueConstraint("workspace_id", "id", name="uq_channel_scope"),
        CheckConstraint("last_seq >= 0", name="ck_channel_seq"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(64))
    topic: Mapped[str] = mapped_column(String(240), default="")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def membership_fk():
    return ForeignKeyConstraint(
        ["workspace_id", "user_id"],
        ["memberships.workspace_id", "memberships.user_id"],
        ondelete="CASCADE",
    )


def channel_fk():
    return ForeignKeyConstraint(
        ["workspace_id", "channel_id"], ["channels.workspace_id", "channels.id"], ondelete="CASCADE"
    )


class ChannelMember(Base):
    __tablename__ = "channel_members"
    __table_args__ = (
        channel_fk(),
        membership_fk(),
        UniqueConstraint("channel_id", "user_id", name="uq_channel_member"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        channel_fk(),
        UniqueConstraint("workspace_id", "channel_id", "id", name="uq_message_scope"),
        ForeignKeyConstraint(
            ["workspace_id", "channel_id", "thread_root_id"],
            ["messages.workspace_id", "messages.channel_id", "messages.id"],
        ),
        UniqueConstraint("channel_id", "seq", name="uq_message_seq"),
        UniqueConstraint("channel_id", "author_id", "client_message_id", name="uq_message_client"),
        CheckConstraint("seq > 0 AND char_length(body) <= 4000", name="ck_message_body_seq"),
        Index("ix_message_history", "channel_id", "thread_root_id", "seq"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    thread_root_id: Mapped[str | None] = mapped_column(String(36))
    client_message_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageMention(Base):
    __tablename__ = "message_mentions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "channel_id", "message_id"],
            ["messages.workspace_id", "messages.channel_id", "messages.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(is_agent AND user_id IS NULL) OR (NOT is_agent AND user_id IS NOT NULL)",
            name="ck_mention_target",
        ),
        UniqueConstraint("message_id", "user_id", name="uq_mention_user"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(36))
    message_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    is_agent: Mapped[bool] = mapped_column(Boolean, default=False)


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        channel_fk(),
        ForeignKeyConstraint(
            ["workspace_id", "channel_id", "message_id"],
            ["messages.workspace_id", "messages.channel_id", "messages.id"],
        ),
        CheckConstraint("size > 0 AND size <= 5242880", name="ck_attachment_size"),
        CheckConstraint(
            "content_type IN ('image/png', 'image/jpeg', 'image/webp', 'image/gif')",
            name="ck_attachment_type",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    message_id: Mapped[str | None] = mapped_column(String(36), index=True)
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelReadState(Base):
    __tablename__ = "channel_read_state"
    __table_args__ = (
        channel_fk(),
        membership_fk(),
        UniqueConstraint("channel_id", "user_id", name="uq_channel_read"),
        CheckConstraint("last_read_seq >= 0", name="ck_read_seq"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_read_seq: Mapped[int] = mapped_column(Integer, default=0)


class ChannelEvent(Base):
    __tablename__ = "channel_events"
    __table_args__ = (
        channel_fk(),
        UniqueConstraint("channel_id", "seq", name="uq_channel_event_seq"),
        CheckConstraint("seq > 0", name="ck_event_seq"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(36), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
