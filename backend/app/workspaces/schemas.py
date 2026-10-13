from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.auth.schemas import EmailInput

Role = Literal["owner", "admin", "editor", "viewer"]


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Workspace name cannot be blank")
        return value.strip()


class RoleInput(BaseModel):
    role: Role


class InviteInput(EmailInput):
    role: Literal["admin", "editor", "viewer"] = "editor"
