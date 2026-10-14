from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["todo", "in_progress", "done"]
Priority = Literal["P1", "P2", "P3"]
TaskType = Literal["bug", "task"]
ProjectColor = Literal["brand", "agent", "success", "warning", "danger"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    key: str = Field(min_length=1, max_length=10, pattern=r"^[A-Z][A-Z0-9]*$")
    color: ProjectColor = "brand"
    description: str = Field(default="", max_length=4000)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a project name")
        return value.strip()


class ProjectUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    key: str | None = Field(default=None, min_length=1, max_length=10, pattern=r"^[A-Z][A-Z0-9]*$")
    color: ProjectColor | None = None
    description: str | None = Field(default=None, max_length=4000)
    archived: bool | None = None


class TaskInput(StrictInput):
    project_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=12000)
    type: TaskType = "task"
    status: Status = "todo"
    priority: Priority = "P2"
    assignee_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a task title")
        return value.strip()


class TaskUpdate(StrictInput):
    version: int = Field(ge=1)
    project_id: str | None = Field(default=None, min_length=1, max_length=36)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=12000)
    type: TaskType | None = None
    status: Status | None = None
    priority: Priority | None = None
    assignee_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None


class TaskMove(StrictInput):
    version: int = Field(ge=1)
    status: Status
    before_id: str | None = Field(default=None, max_length=36)
    after_id: str | None = Field(default=None, max_length=36)


class TaskDelete(StrictInput):
    version: int = Field(ge=1)


class CommentInput(StrictInput):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Write a comment")
        return value


class CommentUpdate(CommentInput):
    version: int = Field(ge=1)


class FromMessageInput(TaskInput):
    message_id: str = Field(min_length=1, max_length=36)


class LinkInput(StrictInput):
    source_type: Literal["task", "message"]
    source_id: str = Field(min_length=1, max_length=36)
    target_type: Literal["task", "message"]
    target_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class ChannelProjectInput(StrictInput):
    project_id: str | None = Field(default=None, max_length=36)


class TaskDeleteRef(StrictInput):
    id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class BulkTaskInput(StrictInput):
    tasks: list[TaskDeleteRef] = Field(min_length=1, max_length=100)
    status: Status | None = None
    assignee_id: str | None = Field(default=None, max_length=36)


class ActorOut(BaseModel):
    id: str
    name: str


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    key: str
    color: str
    description: str
    archived: bool
    deleted_at: str | None
    created_at: str
    updated_at: str


class TaskOut(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    key: str
    number: int
    title: str
    description: str
    type: TaskType
    status: Status
    priority: Priority
    assignee_id: str | None
    assignee: ActorOut | None
    reporter: ActorOut
    due_date: str | None
    created_by_agent: bool
    version: int
    rank: str
    comment_count: int
    last_event_seq: int
    created_at: str
    updated_at: str
    deleted_at: str | None


class TaskCommentOut(BaseModel):
    id: str
    task_id: str
    author: ActorOut
    body: str
    version: int
    created_at: str
    edited_at: str | None
    deleted_at: str | None
