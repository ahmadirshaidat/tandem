from typing import Literal

from pydantic import BaseModel, Field, field_validator

EventType = Literal[
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


class SocketEvent(BaseModel):
    type: EventType
    workspace_id: str | None = None
    channel_id: str | None = None
    seq: int | None = None
    data: dict
