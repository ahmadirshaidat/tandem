import base64
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import User
from app.core.security import csrf_check, current_user, now
from app.documents import service as svc
from app.documents.models import DocumentMember, DocumentSuggestion, DocumentVersion
from app.tasks.models import Link
from app.tasks.schemas import StrictInput
from app.tasks.service import access, resolve_item, visible_link

router = APIRouter(prefix="/api/workspaces/{workspace_id}/documents", tags=["documents"])
write = [Depends(csrf_check)]


class Create(StrictInput):
    project_id: str = Field(min_length=36, max_length=36)
    title: str = Field(min_length=1, max_length=240)
    type: Literal["spec", "meeting_notes", "adr", "bug_postmortem"] = "spec"
    is_private: bool = False


class Edit(StrictInput):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    archived: bool | None = None
    is_private: bool | None = None


class Update(StrictInput):
    update: str = Field(max_length=90000)


class VersionInput(StrictInput):
    name: str | None = Field(default=None, max_length=120)


class FromConversation(Create):
    message_ids: list[str] = Field(min_length=1, max_length=30)


class Ask(StrictInput):
    channel_id: str = Field(min_length=36, max_length=36)
    question: str = Field(min_length=1, max_length=1500)


@router.get("")
def listing(
    workspace_id: str,
    project_id: str | None = None,
    type: str | None = None,
    archived: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = svc.visible(db, workspace_id, user.id).where(svc.Document.archived == archived)
    if project_id:
        q = q.where(svc.Document.project_id == project_id)
    if type:
        q = q.where(svc.Document.type == type)
    return {
        "documents": [
            svc.output(d) for d in db.scalars(q.order_by(svc.Document.updated_at.desc()).limit(200))
        ]
    }


@router.post("", dependencies=write, status_code=201)
def create(
    workspace_id: str,
    data: Create,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = svc.create(db, workspace_id, user.id, data)
    db.commit()
    return svc.output(d)


@router.post("/from-conversation", dependencies=write, status_code=201)
def conversation(
    workspace_id: str,
    data: FromConversation,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    messages = [
        resolve_item(db, workspace_id, "message", sid, user.id)["message"]
        for sid in data.message_ids
    ]
    d = svc.create(db, workspace_id, user.id, data)
    if any(m.channel_id and db.get(svc.Channel, m.channel_id).is_private for m in messages):
        d.is_private = True
        if not db.get(DocumentMember, (workspace_id, d.id, user.id)):
            db.add(DocumentMember(workspace_id=workspace_id, document_id=d.id, user_id=user.id))
    projected = svc.transform(action="template", text="\n".join(m.body for m in messages))
    svc.persist(db, d, user.id, base64.b64decode(projected["state"]), snapshot_actor="user")
    for m in messages:
        db.add(
            Link(
                workspace_id=workspace_id,
                source_type="document",
                source_id=d.id,
                target_type="message",
                target_id=m.id,
                relation="related",
                created_by=user.id,
            )
        )
    db.commit()
    return svc.output(d)


@router.get("/{document_id}")
def detail(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = svc.document(db, workspace_id, document_id, user.id)
    return {**svc.output(d), "text": d.plain_text, "markdown": d.markdown}


@router.get("/{document_id}/state")
def state(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return svc.state_out(db, svc.document(db, workspace_id, document_id, user.id), user.id)


@router.post("/{document_id}/sync", dependencies=write)
def sync(
    workspace_id: str,
    document_id: str,
    data: Update,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = svc.document(db, workspace_id, document_id, user.id, "editor", lock=True)
    try:
        update = base64.b64decode(data.update, validate=True)
    except ValueError:
        raise HTTPException(422, "Invalid document update") from None
    svc.persist(db, d, user.id, update)
    db.commit()
    return svc.state_out(db, d, user.id)


@router.patch("/{document_id}", dependencies=write)
def edit(
    workspace_id: str,
    document_id: str,
    data: Edit,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(
        db,
        workspace_id,
        user.id,
        "admin" if data.archived is not None or data.is_private is not None else "editor",
        lock=True,
    )
    d = svc.document(db, workspace_id, document_id, user.id, lock=True)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is None:
            raise HTTPException(422, "A document field cannot be cleared")
        if k == "is_private" and v and not d.is_private:
            db.add(DocumentMember(workspace_id=workspace_id, document_id=d.id, user_id=user.id))
        setattr(d, k, v)
        svc.log(db, d, user.id, k)
    d.updated_at = now()
    db.commit()
    return svc.output(d)


@router.delete("/{document_id}", dependencies=write, status_code=204)
def remove(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    d = svc.document(db, workspace_id, document_id, user.id, lock=True)
    d.deleted_at = now()
    svc.log(db, d, user.id, "deleted")
    db.commit()


@router.get("/{document_id}/members")
def members(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    svc.document(db, workspace_id, document_id, user.id)
    return {
        "user_ids": list(
            db.scalars(
                select(DocumentMember.user_id).where(
                    DocumentMember.workspace_id == workspace_id,
                    DocumentMember.document_id == document_id,
                )
            )
        )
    }


@router.put("/{document_id}/members/{member_id}", dependencies=write)
def add_member(
    workspace_id: str,
    document_id: str,
    member_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    d = svc.document(db, workspace_id, document_id, user.id, lock=True)
    access(db, workspace_id, member_id)
    if not db.get(DocumentMember, (workspace_id, document_id, member_id)):
        db.add(
            DocumentMember(workspace_id=workspace_id, document_id=document_id, user_id=member_id)
        )
    svc.log(db, d, user.id, "member_added", member_id=member_id)
    db.commit()
    return {"status": "included"}


@router.delete("/{document_id}/members/{member_id}", dependencies=write, status_code=204)
def remove_member(
    workspace_id: str,
    document_id: str,
    member_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    access(db, workspace_id, user.id, "admin", lock=True)
    d = svc.document(db, workspace_id, document_id, user.id, lock=True)
    db.execute(
        delete(DocumentMember).where(
            DocumentMember.workspace_id == workspace_id,
            DocumentMember.document_id == document_id,
            DocumentMember.user_id == member_id,
        )
    )
    svc.log(db, d, user.id, "member_removed", member_id=member_id)
    db.commit()


def version_out(v):
    return {
        "id": v.id,
        "revision": v.revision,
        "name": v.name,
        "created_by": v.created_by,
        "actor_type": v.actor_type,
        "proposal_id": v.proposal_id,
        "created_at": v.created_at.isoformat(),
    }


@router.get("/{document_id}/versions")
def versions(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    svc.document(db, workspace_id, document_id, user.id)
    return {
        "versions": [
            version_out(v)
            for v in db.scalars(
                select(DocumentVersion)
                .where(
                    DocumentVersion.workspace_id == workspace_id,
                    DocumentVersion.document_id == document_id,
                )
                .order_by(DocumentVersion.created_at.desc())
                .limit(200)
            )
        ]
    }


@router.post("/{document_id}/versions", dependencies=write)
def save_version(
    workspace_id: str,
    document_id: str,
    data: VersionInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = svc.document(db, workspace_id, document_id, user.id, "editor", lock=True)
    v = svc.snapshot(db, d, user.id, data.name)
    svc.log(db, d, user.id, "version_created", version_id=v.id)
    db.commit()
    return version_out(v)


def get_version(db, wid, did, vid):
    v = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.workspace_id == wid,
            DocumentVersion.document_id == did,
            DocumentVersion.id == vid,
        )
    )
    if not v:
        raise HTTPException(404, "Version unavailable")
    return v


@router.get("/{document_id}/versions/{version_id}")
def preview(
    workspace_id: str,
    document_id: str,
    version_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    svc.document(db, workspace_id, document_id, user.id)
    v = get_version(db, workspace_id, document_id, version_id)
    return {**version_out(v), "markdown": v.markdown}


@router.patch("/{document_id}/versions/{version_id}", dependencies=write)
def name_version(
    workspace_id: str,
    document_id: str,
    version_id: str,
    data: VersionInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    svc.document(db, workspace_id, document_id, user.id, "editor", lock=True)
    v = get_version(db, workspace_id, document_id, version_id)
    v.name = data.name
    db.commit()
    return version_out(v)


@router.post("/{document_id}/versions/{version_id}/restore", dependencies=write)
def restore(
    workspace_id: str,
    document_id: str,
    version_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = svc.document(db, workspace_id, document_id, user.id, "editor", lock=True)
    v = get_version(db, workspace_id, document_id, version_id)
    value = svc.transform(d.state, action="restore", previous=base64.b64encode(v.state).decode())
    svc.persist(db, d, user.id, base64.b64decode(value["state"]), snapshot_actor="user")
    svc.snapshot(db, d, user.id, "Restored version " + version_id)
    svc.log(db, d, user.id, "restored", version_id=version_id)
    db.commit()
    return svc.output(d)


@router.get("/{document_id}/export")
def export(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = svc.document(db, workspace_id, document_id, user.id)
    return Response(
        d.markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="document.md"'},
    )


@router.get("/{document_id}/backlinks")
def backlinks(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    svc.document(db, workspace_id, document_id, user.id)
    links = db.scalars(
        select(Link)
        .where(
            Link.workspace_id == workspace_id,
            or_(
                (Link.target_type == "document") & (Link.target_id == document_id),
                (Link.source_type == "document") & (Link.source_id == document_id),
            ),
        )
        .limit(200)
    )
    return {"links": [v for edge in links if (v := visible_link(db, edge, user.id))]}


@router.get("/{document_id}/suggestions")
def suggestions(
    workspace_id: str,
    document_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.proposals.service import get_proposal, proposal_out

    svc.document(db, workspace_id, document_id, user.id)
    out = []
    for item in db.scalars(
        select(DocumentSuggestion).where(
            DocumentSuggestion.workspace_id == workspace_id,
            DocumentSuggestion.document_id == document_id,
        )
    ):
        try:
            p = get_proposal(db, workspace_id, item.proposal_id, user.id)
        except HTTPException:
            continue
        out.append(proposal_out(db, p))
    return {"suggestions": out}


@router.post("/{document_id}/ask", dependencies=write, status_code=202)
def ask(
    workspace_id: str,
    document_id: str,
    data: Ask,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    import uuid

    from app.channels.router import send_message
    from app.channels.schemas import MessageInput

    svc.shared_access(db, workspace_id, document_id, user.id, data.channel_id)
    channel, _ = svc.channel_access(db, workspace_id, data.channel_id, user.id)
    message = send_message(
        workspace_id,
        channel.id,
        MessageInput(
            body=f"@Agent get_document {document_id} and propose_suggest_edit. {data.question}",
            client_message_id=uuid.uuid4().hex,
        ),
        Response(),
        request,
        user,
        db,
    )
    return {"channel_id": channel.id, "message_id": message["id"]}
