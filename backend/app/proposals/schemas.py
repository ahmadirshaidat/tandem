from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from app.tasks.schemas import CommentInput, Priority, Status, StrictInput, TaskInput

Kind = Literal[
    "create_tasks", "update_task", "reassign_task", "change_priority", "delete_task", "add_comment"
]


class NewItem(TaskInput):
    item_id: str = Field(min_length=1, max_length=36, pattern=r"^[a-zA-Z0-9_-]+$")
    depends_on: list[str] = Field(default_factory=list, max_length=9)
    description: str = Field(default="", max_length=4000)


class CreateTasks(StrictInput):
    items: list[NewItem] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def dag(self):
        graph = {i.item_id: i.depends_on for i in self.items}
        if len(graph) != len(self.items):
            raise ValueError("Each item needs a unique ID")

        def visit(key, path):
            if key not in graph or key in path:
                raise ValueError("Dependencies must reference other items without cycles")
            for dep in graph[key]:
                visit(dep, path | {key})

        for key in graph:
            visit(key, set())
        return self


class Target(StrictInput):
    task_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class Changes(StrictInput):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    status: Status | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("Choose a task field to change")
        if any(getattr(self, k) is None for k in self.model_fields_set - {"due_date"}):
            raise ValueError("Only due date can be cleared")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("Enter a title")
        return self


class UpdateTask(Target):
    changes: Changes


class ReassignTask(Target):
    assignee_id: str | None = Field(default=None, max_length=36)


class ChangePriority(Target):
    priority: Priority


class AddComment(Target, CommentInput):
    pass


PAYLOADS = {
    "create_tasks": CreateTasks,
    "update_task": UpdateTask,
    "reassign_task": ReassignTask,
    "change_priority": ChangePriority,
    "delete_task": Target,
    "add_comment": AddComment,
}


class Source(StrictInput):
    type: Literal["message", "task"]
    id: str = Field(min_length=1, max_length=36)


class Decision(StrictInput):
    version: int = Field(ge=1)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    reason: str | None = Field(default=None, max_length=500)


class EditApproval(Decision):
    payload: dict


class Rules(StrictInput):
    create_tasks_approver: Literal["editor", "admin"]
