import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.channels.service import default_channel, join_public
from app.core.config import settings
from app.core.db import get_db
from app.core.models import Invitation, Membership, User, Workspace, new_id
from app.core.security import csrf_check, current_user, digest, now
from app.tasks.service import unassign_removed_member
from app.workspaces.permissions import lock_workspace, require_role
from app.workspaces.schemas import InviteInput, RoleInput, WorkspaceInput

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])
invites = APIRouter(prefix="/api/invitations", tags=["invitations"])
write = [Depends(csrf_check)]


def workspace_out(workspace: Workspace, role: str):
    return {
        "id": workspace.id,
        "name": workspace.name,
        "role": role,
        "created_at": workspace.created_at,
    }


def invitation_out(invitation: Invitation):
    status = "pending"
    if invitation.accepted_at:
        status = "accepted"
    elif invitation.revoked_at:
        status = "revoked"
    elif invitation.expires_at <= now():
        status = "expired"
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "expires_at": invitation.expires_at,
        "status": status,
    }


@router.get("")
def list_workspaces(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    return [workspace_out(workspace, role) for workspace, role in rows]


@router.post("", status_code=201, dependencies=write)
def create_workspace(
    data: WorkspaceInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    workspace = Workspace(id=new_id(), name=data.name)
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    default_channel(db, workspace.id, user.id)
    db.commit()
    return workspace_out(workspace, "owner")


@router.get("/{workspace_id}")
def get_workspace(
    workspace_id: str, member: Membership = Depends(require_role()), db: Session = Depends(get_db)
):
    return workspace_out(db.get(Workspace, workspace_id), member.role)


@router.patch("/{workspace_id}", dependencies=write)
def update_workspace(
    workspace_id: str,
    data: WorkspaceInput,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    member = lock_workspace(db, workspace_id, member.user_id)
    workspace = db.get(Workspace, workspace_id)
    workspace.name = data.name
    db.commit()
    return workspace_out(workspace, member.role)


@router.get("/{workspace_id}/members")
def list_members(
    workspace_id: str, member: Membership = Depends(require_role()), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(Membership, User)
        .join(User)
        .where(Membership.workspace_id == workspace_id)
        .order_by(Membership.created_at)
    )
    return [
        {
            "id": item.id,
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "role": item.role,
        }
        for item, user in rows
    ]


def target_member(db: Session, workspace_id: str, member_id: str, actor: Membership):
    target = db.scalar(
        select(Membership)
        .where(Membership.id == member_id, Membership.workspace_id == workspace_id)
        .execution_options(populate_existing=True)
    )
    if not target:
        raise HTTPException(404, "Member not found")
    if target.role == "owner" and actor.role != "owner":
        raise HTTPException(403, "Only an Owner can change another Owner")
    return target


def protect_last_owner(db: Session, workspace_id: str, target: Membership):
    if target.role == "owner":
        owners = db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id, Membership.role == "owner")
        )
        if owners <= 1:
            raise HTTPException(409, "The last Owner cannot be removed or demoted")


@router.patch("/{workspace_id}/members/{member_id}", dependencies=write)
def change_role(
    workspace_id: str,
    member_id: str,
    data: RoleInput,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    actor = lock_workspace(db, workspace_id, member.user_id)
    target = target_member(db, workspace_id, member_id, actor)
    if data.role == "owner" and actor.role != "owner":
        raise HTTPException(403, "Only an Owner can grant the Owner role")
    if data.role != "owner":
        protect_last_owner(db, workspace_id, target)
    target.role = data.role
    db.commit()
    return {"id": target.id, "role": target.role}


@router.delete("/{workspace_id}/members/{member_id}", status_code=204, dependencies=write)
def remove_member(
    workspace_id: str,
    member_id: str,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    actor = lock_workspace(db, workspace_id, member.user_id)
    target = target_member(db, workspace_id, member_id, actor)
    protect_last_owner(db, workspace_id, target)
    unassign_removed_member(db, workspace_id, target.user_id, actor.user_id)
    db.delete(target)
    db.commit()


@router.get("/{workspace_id}/invitations")
def list_invitations(
    workspace_id: str,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return [
        invitation_out(item)
        for item in db.scalars(
            select(Invitation)
            .where(Invitation.workspace_id == workspace_id)
            .order_by(Invitation.expires_at.desc())
        )
    ]


@router.post("/{workspace_id}/invitations", status_code=201, dependencies=write)
def create_invitation(
    workspace_id: str,
    data: InviteInput,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    actor = lock_workspace(db, workspace_id, member.user_id)
    existing = db.scalar(
        select(Membership)
        .join(User)
        .where(Membership.workspace_id == workspace_id, User.email == data.email)
    )
    if existing:
        raise HTTPException(409, "This person is already a member")
    # Reissuing a link revokes any earlier pending link for the same address.
    for old in db.scalars(
        select(Invitation).where(
            Invitation.workspace_id == workspace_id,
            Invitation.email == data.email,
            Invitation.accepted_at.is_(None),
        )
    ):
        old.revoked_at = now()
    token = secrets.token_urlsafe(48)
    invitation = Invitation(
        workspace_id=workspace_id,
        created_by=actor.user_id,
        email=data.email,
        role=data.role,
        token_hash=digest(token),
        expires_at=now() + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    return {
        **invitation_out(invitation),
        "invite_url": f"{settings.frontend_url}/accept-invitation?token={token}",
    }


@router.delete("/{workspace_id}/invitations/{invitation_id}", status_code=204, dependencies=write)
def revoke_invitation(
    workspace_id: str,
    invitation_id: str,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    lock_workspace(db, workspace_id, member.user_id)
    item = db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.workspace_id == workspace_id
        )
    )
    if not item:
        raise HTTPException(404, "Invitation not found")
    if item.accepted_at:
        raise HTTPException(409, "This invitation has already been accepted")
    item.revoked_at = now()
    db.commit()


def valid_invitation(db: Session, token: str):
    invitation = db.scalar(
        select(Invitation)
        .where(Invitation.token_hash == digest(token))
        .execution_options(populate_existing=True)
    )
    if (
        not invitation
        or invitation.revoked_at
        or invitation.accepted_at
        or invitation.expires_at <= now()
    ):
        raise HTTPException(410, "This invitation has expired or is no longer available")
    return invitation


@invites.get("/{token}")
def preview_invitation(token: str, db: Session = Depends(get_db)):
    item = valid_invitation(db, token)
    workspace = db.get(Workspace, item.workspace_id)
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "email": item.email,
        "role": item.role,
        "expires_at": item.expires_at,
    }


@invites.post("/{token}/accept", dependencies=write)
def accept_invitation(
    token: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    item = valid_invitation(db, token)
    # All membership and invitation mutations use the same workspace lock first.
    db.scalar(select(Workspace).where(Workspace.id == item.workspace_id).with_for_update())
    item = valid_invitation(db, token)
    if item.email != user.email:
        raise HTTPException(403, "Log in with the email address this invitation was sent to")
    existing = db.scalar(
        select(Membership).where(
            Membership.workspace_id == item.workspace_id, Membership.user_id == user.id
        )
    )
    if existing:
        raise HTTPException(409, "You are already a member of this workspace")
    db.add(Membership(workspace_id=item.workspace_id, user_id=user.id, role=item.role))
    db.flush()
    join_public(db, item.workspace_id, user.id)
    item.accepted_at = now()
    workspace = db.get(Workspace, item.workspace_id)
    db.commit()
    return workspace_out(workspace, item.role)
