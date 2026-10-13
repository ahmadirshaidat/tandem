from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Membership, User, Workspace
from app.core.security import current_user

LEVEL = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}


def membership(db: Session, workspace_id: str, user_id: str, minimum: str = "viewer"):
    member = db.scalar(
        select(Membership)
        .where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    )
    if not member:
        raise HTTPException(404, "Workspace not found or you do not have access")
    if LEVEL[member.role] < LEVEL[minimum]:
        raise HTTPException(403, "An Admin or Owner is required for this action")
    return member


def require_role(minimum: str = "viewer"):
    def dependency(
        workspace_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
    ):
        return membership(db, workspace_id, user.id, minimum)

    return dependency


def lock_workspace(db: Session, workspace_id: str, user_id: str, minimum: str = "admin"):
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    # Check again after the lock so concurrent membership changes cannot authorize stale roles.
    return membership(db, workspace_id, user_id, minimum)
