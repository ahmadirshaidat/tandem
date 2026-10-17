from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agent.audit import audit
from app.agent.service import configuration
from app.channels.service import channel_access, visible_channels
from app.core.db import get_db
from app.core.models import User
from app.core.security import csrf_check, current_user
from app.proposals.models import Proposal
from app.proposals.schemas import Decision, EditApproval, Rules
from app.proposals.service import decide, get_proposal, proposal_out
from app.tasks.service import access
from app.workspaces.permissions import LEVEL

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["proposals"])


@router.get("/proposals")
def list_proposals(
    workspace_id: str,
    channel_id: str | None = None,
    pending: bool = False,
    actionable: bool = False,
    before: str | None = Query(None, max_length=36),
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    member = access(db, workspace_id, user.id)
    if channel_id:
        channel_access(db, workspace_id, channel_id, user.id)
        ids = [channel_id]
    else:
        ids = [c.id for c in visible_channels(db, workspace_id, user.id)]
    query = select(Proposal).where(
        Proposal.workspace_id == workspace_id, Proposal.channel_id.in_(ids)
    )
    from app.documents.models import Document
    from app.documents.service import visible

    query = query.where(
        or_(
            Proposal.kind != "suggest_edit",
            Proposal.payload["document_id"]
            .as_string()
            .in_(visible(db, workspace_id, user.id).with_only_columns(Document.id)),
        )
    )
    if pending or actionable:
        from app.core.security import now

        query = query.where(Proposal.status == "proposed", Proposal.expires_at > now())
    if actionable:
        allowed_kinds = [
            k
            for k in [
                "create_tasks",
                "update_task",
                "add_comment",
                "suggest_edit",
                "reassign_task",
                "change_priority",
                "delete_task",
            ]
            if LEVEL[member.role]
            >= LEVEL[
                "admin"
                if k in {"reassign_task", "change_priority", "delete_task"}
                else configuration(db, workspace_id).create_tasks_approver
                if k == "create_tasks"
                else "editor"
            ]
        ]
        query = query.where(Proposal.kind.in_(allowed_kinds))
    if before:
        from fastapi import HTTPException
        from sqlalchemy import and_

        anchor = db.scalar(query.where(Proposal.id == before))
        if not anchor:
            raise HTTPException(422, "Invalid proposal cursor")
        query = query.where(
            or_(
                Proposal.created_at < anchor.created_at,
                and_(Proposal.created_at == anchor.created_at, Proposal.id < anchor.id),
            )
        )
    rows = list(
        db.scalars(query.order_by(Proposal.created_at.desc(), Proposal.id.desc()).limit(limit + 1))
    )
    return {
        "proposals": [proposal_out(db, p) for p in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.get("/proposals/{proposal_id}")
def read_proposal(
    workspace_id: str,
    proposal_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return proposal_out(db, get_proposal(db, workspace_id, proposal_id, user.id))


def human_decision(workspace_id, proposal_id, data, request, user, db, action):
    p = get_proposal(db, workspace_id, proposal_id, user.id, lock=True)
    decide(db, p, user.id, data, action, request.state.request_id)
    db.commit()
    return proposal_out(db, p)


@router.post("/proposals/{proposal_id}/approve", dependencies=[Depends(csrf_check)])
def approve(
    workspace_id: str,
    proposal_id: str,
    data: Decision,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return human_decision(workspace_id, proposal_id, data, request, user, db, "approve")


@router.post("/proposals/{proposal_id}/edit-approve", dependencies=[Depends(csrf_check)])
def edit_approve(
    workspace_id: str,
    proposal_id: str,
    data: EditApproval,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return human_decision(workspace_id, proposal_id, data, request, user, db, "edit-approve")


@router.post("/proposals/{proposal_id}/reject", dependencies=[Depends(csrf_check)])
def reject(
    workspace_id: str,
    proposal_id: str,
    data: Decision,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return human_decision(workspace_id, proposal_id, data, request, user, db, "reject")


@router.post("/proposals/{proposal_id}/cancel", dependencies=[Depends(csrf_check)])
def cancel(
    workspace_id: str,
    proposal_id: str,
    data: Decision,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return human_decision(workspace_id, proposal_id, data, request, user, db, "cancel")


@router.get("/agent/approval-rules")
def read_rules(
    workspace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    access(db, workspace_id, user.id)
    return {"create_tasks_approver": configuration(db, workspace_id).create_tasks_approver}


@router.put("/agent/approval-rules", dependencies=[Depends(csrf_check)])
def update_rules(
    workspace_id: str,
    data: Rules,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    c = configuration(db, workspace_id)
    old = c.create_tasks_approver
    c.create_tasks_approver = data.create_tasks_approver
    audit(
        db,
        workspace_id,
        "user",
        user.id,
        "proposal.rule_changed",
        "workspace",
        workspace_id,
        arguments={"previous": old, "create_tasks_approver": data.create_tasks_approver},
        request_id=request.state.request_id,
    )
    db.commit()
    return {"create_tasks_approver": c.create_tasks_approver}
