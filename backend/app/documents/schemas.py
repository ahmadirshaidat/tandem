"""Document-scoped transport metadata; never emitted in workspace broadcasts."""

from typing import Literal

from pydantic import BaseModel, Field


class DocumentSyncEvent(BaseModel):
    type: Literal["state", "ack", "rejected", "awareness"]
    state: str | None = Field(default=None, max_length=1400000)
    revision: int | None = None
    can_edit: bool | None = None
    update_id: str | None = None
    data: str | None = Field(default=None, max_length=12000)
