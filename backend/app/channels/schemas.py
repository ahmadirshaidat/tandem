from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.tasks.schemas import ProjectOut, TaskCommentOut, TaskOut

EventType = Literal[
    "task.created",
    "task.updated",
    "task.moved",
    "task.deleted",
    "task.comment_created",
    "project.updated",
    "message.created",
    "message.updated",
    "message.deleted",
    "thread.reply_created",
    "channel.created",
    "channel.updated",
    "channel.archived",
    "member.joined",
    "member.left",
    "presence.update",
    "typing.start",
    "typing.stop",
    "read.updated",
    "error",
]


class ChannelInput(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    topic: str = Field(default="", max_length=240)
    is_private: bool = False


class ChannelUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )
    topic: str | None = Field(default=None, max_length=240)
    archived: bool | None = None


class MessageInput(BaseModel):
    body: str = Field(default="", max_length=4000)
    client_message_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    thread_root_id: str | None = Field(default=None, max_length=36)
    attachment_ids: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("attachment_ids")
    @classmethod
    def unique_attachments(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Each attachment can appear only once")
        return value


class MessageEdit(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReadInput(BaseModel):
    last_read_seq: int = Field(ge=0)


class MemberInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)


class SocketCommand(BaseModel):
    type: Literal["subscribe", "unsubscribe", "ping", "typing.start", "typing.stop"]
    workspace_id: str | None = Field(default=None, max_length=36)
    channel_id: str | None = Field(default=None, max_length=36)
    last_seq: int = Field(default=0, ge=0)
    workspace_seq: int | None = Field(default=None, ge=0)


class AuthorOut(BaseModel):
    id: str
    name: str


class AttachmentOut(BaseModel):
    id: str
    content_type: str
    size: int
    width: int
    height: int
    url: str


class MentionOut(BaseModel):
    user_id: str | None
    is_agent: bool


class MessageOut(BaseModel):
    id: str
    workspace_id: str
    channel_id: str
    author: AuthorOut
    body: str
    seq: int
    client_message_id: str
    thread_root_id: str | None
    created_at: str
    edited_at: str | None
    deleted_at: str | None
    mentions: list[MentionOut]
    mentions_agent: bool
    attachments: list[AttachmentOut]
    reply_count: int


class ChannelOut(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    name: str
    topic: str
    is_private: bool
    archived: bool
    last_seq: int
    unread_count: int
    mention_count: int
    joined: bool
    last_read_seq: int


class EventData(BaseModel):
    task: TaskOut | None = None
    project: ProjectOut | None = None
    comment: TaskCommentOut | None = None
    message: MessageOut | str | None = None
    thread_root: MessageOut | None = None
    channel: ChannelOut | None = None
    channel_id: str | None = None
    user_id: str | None = None
    user_ids: list[str] | None = None
    last_read_seq: int | None = None
    code: str | None = None


class SocketEvent(BaseModel):
    type: EventType
    workspace_id: str | None
    channel_id: str | None
    seq: int | None
    data: EventData
