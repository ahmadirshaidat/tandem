from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.models import (
    Attachment,
    Channel,
    ChannelMember,
    ChannelReadState,
    Message,
    MessageMention,
)
from app.channels.schemas import (
    ChannelInput,
    ChannelUpdate,
    MemberInput,
    MessageEdit,
    MessageInput,
    ReadInput,
)
from app.channels.service import (
    attachment_out,
    can_manage,
    channel_access,
    channel_out,
    message_out,
    parse_mentions,
    record_event,
    send_limiter,
    visible_channels,
)
from app.channels.storage import MAX_IMAGE_BYTES, inspect_image, storage
from app.core.db import get_db
from app.core.models import Membership, User, Workspace
from app.core.security import csrf_check, current_user, now
from app.workspaces.permissions import membership

router = APIRouter(prefix="/api/workspaces/{workspace_id}/channels", tags=["channels"])
write = [Depends(csrf_check)]


def lock_workspace(db, workspace_id, user_id, minimum="viewer"):
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    member = membership(db, workspace_id, user_id)
    can_manage(member, minimum)
    return member


@router.get("")
def list_channels(
    workspace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return [channel_out(db, c, user.id) for c in visible_channels(db, workspace_id, user.id)]


@router.post("", status_code=201, dependencies=write)
def create_channel(
    workspace_id: str,
    data: ChannelInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lock_workspace(db, workspace_id, user.id, "admin" if data.is_private else "editor")
    c = Channel(workspace_id=workspace_id, **data.model_dump())
    db.add(c)
    try:
        db.flush()
        users = (
            [user.id]
            if c.is_private
            else list(
                db.scalars(
                    select(Membership.user_id).where(Membership.workspace_id == workspace_id)
                )
            )
        )
        db.add_all(
            [
                ChannelMember(workspace_id=workspace_id, channel_id=c.id, user_id=uid)
                for uid in users
            ]
        )
        record_event(db, c, "channel.created", {"channel_id": c.id})
        db.commit()
    except IntegrityError:
        db.rollback()
        # Name uniqueness includes private channels; never confirm a hidden channel.
        raise HTTPException(409, "This channel name is unavailable. Choose another name.") from None
    return channel_out(db, c, user.id)


@router.get("/{channel_id}")
def get_channel(
    workspace_id: str,
    channel_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id)
    return channel_out(db, c, user.id)


@router.patch("/{channel_id}", dependencies=write)
def update_channel(
    workspace_id: str,
    channel_id: str,
    data: ChannelUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, member = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    can_manage(member)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(422, "Channel fields cannot be null")
        setattr(c, key, value)
    record_event(
        db, c, "channel.archived" if data.archived else "channel.updated", {"channel_id": c.id}
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This channel name is unavailable. Choose another name.") from None
    return channel_out(db, c, user.id)


@router.post("/{channel_id}/join", dependencies=write)
def join_channel(
    workspace_id: str,
    channel_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    if c.is_private:
        raise HTTPException(403, "An Admin or Owner manages private channel membership")
    if not db.scalar(
        select(ChannelMember.id).where(
            ChannelMember.channel_id == c.id, ChannelMember.user_id == user.id
        )
    ):
        db.add(ChannelMember(workspace_id=workspace_id, channel_id=c.id, user_id=user.id))
        record_event(db, c, "member.joined", {"user_id": user.id})
        db.commit()
    return channel_out(db, c, user.id)


@router.post("/{channel_id}/leave", dependencies=write)
def leave_channel(
    workspace_id: str,
    channel_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    if c.is_private:
        raise HTTPException(403, "An Admin or Owner manages private channel membership")
    db.execute(
        delete(ChannelMember).where(
            ChannelMember.channel_id == c.id, ChannelMember.user_id == user.id
        )
    )
    record_event(db, c, "member.left", {"user_id": user.id})
    db.commit()
    return channel_out(db, c, user.id)


@router.get("/{channel_id}/members")
def list_channel_members(
    workspace_id: str,
    channel_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id)
    query = (
        select(User.id, User.name, Membership.role)
        .join(Membership)
        .where(Membership.workspace_id == workspace_id)
    )
    if c.is_private:
        query = query.where(
            User.id.in_(select(ChannelMember.user_id).where(ChannelMember.channel_id == c.id))
        )
    return [{"user_id": row.id, "name": row.name, "role": row.role} for row in db.execute(query)]


@router.post("/{channel_id}/members", dependencies=write)
def add_channel_member(
    workspace_id: str,
    channel_id: str,
    data: MemberInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, member = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    can_manage(member, "admin")
    if not c.is_private:
        raise HTTPException(409, "Workspace members already have access to public channels")
    membership(db, workspace_id, data.user_id)
    if not db.scalar(
        select(ChannelMember.id).where(
            ChannelMember.channel_id == c.id, ChannelMember.user_id == data.user_id
        )
    ):
        db.add(ChannelMember(workspace_id=workspace_id, channel_id=c.id, user_id=data.user_id))
        record_event(db, c, "member.joined", {"user_id": data.user_id})
        db.commit()
    return {"user_id": data.user_id}


@router.delete("/{channel_id}/members/{user_id}", status_code=204, dependencies=write)
def remove_channel_member(
    workspace_id: str,
    channel_id: str,
    user_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, member = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    can_manage(member, "admin")
    if not c.is_private:
        raise HTTPException(409, "Members leave public channels themselves")
    admins = db.scalars(
        select(ChannelMember.user_id)
        .join(
            Membership,
            (Membership.user_id == ChannelMember.user_id)
            & (Membership.workspace_id == ChannelMember.workspace_id),
        )
        .where(ChannelMember.channel_id == c.id, Membership.role.in_(["owner", "admin"]))
    ).all()
    if user_id in admins and len(admins) == 1:
        raise HTTPException(409, "Keep an Admin or Owner in this private channel")
    db.execute(
        delete(ChannelMember).where(
            ChannelMember.channel_id == c.id, ChannelMember.user_id == user_id
        )
    )
    record_event(db, c, "member.left", {"user_id": user_id})
    db.commit()


def find_message(db, channel_id, message_id):
    m = db.scalar(select(Message).where(Message.channel_id == channel_id, Message.id == message_id))
    if not m:
        raise HTTPException(404, "Message not found")
    return m


@router.get("/{channel_id}/messages")
def history(
    workspace_id: str,
    channel_id: str,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id)
    # Snapshot cursor before reading rows: concurrent commits can be replayed safely.
    cursor = c.last_seq
    query = select(Message).where(Message.channel_id == c.id, Message.thread_root_id.is_(None))
    if before:
        query = query.where(Message.seq < before)
    rows = list(db.scalars(query.order_by(Message.seq.desc()).limit(limit + 1)))
    return {
        "messages": [message_out(db, m) for m in rows[:limit]],
        "next_cursor": rows[limit - 1].seq if len(rows) > limit else None,
        "last_seq": cursor,
    }


@router.post("/{channel_id}/messages", status_code=201, dependencies=write)
def send_message(
    workspace_id: str,
    channel_id: str,
    data: MessageInput,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    existing = db.scalar(
        select(Message).where(
            Message.channel_id == c.id,
            Message.author_id == user.id,
            Message.client_message_id == data.client_message_id,
        )
    )
    if existing:
        response.status_code = 200
        return message_out(db, existing)
    if c.archived:
        raise HTTPException(409, "This channel is archived")
    send_limiter.check(user.id)
    if not data.body.strip() and not data.attachment_ids:
        raise HTTPException(422, "Write a message or attach an image")
    if data.thread_root_id:
        root = find_message(db, c.id, data.thread_root_id)
        if root.thread_root_id or root.deleted_at:
            raise HTTPException(409, "Reply to an existing top-level message")
    files = []
    for aid in data.attachment_ids:
        item = db.scalar(
            select(Attachment).where(
                Attachment.id == aid,
                Attachment.channel_id == c.id,
                Attachment.workspace_id == workspace_id,
                Attachment.uploader_id == user.id,
                Attachment.message_id.is_(None),
            )
        )
        if not item:
            raise HTTPException(404, "Attachment not found or unavailable")
        files.append(item)
    m = Message(
        workspace_id=workspace_id,
        channel_id=c.id,
        author_id=user.id,
        body=data.body,
        seq=c.last_seq + 1,
        client_message_id=data.client_message_id,
        thread_root_id=data.thread_root_id,
    )
    db.add(m)
    db.flush()
    for item in files:
        item.message_id = m.id
    parse_mentions(db, c, m)
    db.flush()
    out = message_out(db, m)
    record_event(
        db, c, "thread.reply_created" if m.thread_root_id else "message.created", {"message": out}
    )
    db.commit()
    return out


@router.patch("/{channel_id}/messages/{message_id}", dependencies=write)
def edit_message(
    workspace_id: str,
    channel_id: str,
    message_id: str,
    data: MessageEdit,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id, lock=True, write=True)
    m = find_message(db, c.id, message_id)
    if m.author_id != user.id:
        raise HTTPException(403, "You can edit only your own messages")
    if m.deleted_at or not data.body.strip():
        raise HTTPException(409, "This message cannot be edited")
    send_limiter.check(user.id)
    m.body, m.edited_at = data.body, now()
    parse_mentions(db, c, m)
    out = message_out(db, m)
    record_event(db, c, "message.updated", {"message": out})
    db.commit()
    return out


@router.delete("/{channel_id}/messages/{message_id}", status_code=204, dependencies=write)
def delete_message(
    workspace_id: str,
    channel_id: str,
    message_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, member = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    m = find_message(db, c.id, message_id)
    if m.author_id != user.id:
        can_manage(member, "admin")
    if not m.deleted_at:
        m.body, m.deleted_at = "", now()
        db.execute(delete(MessageMention).where(MessageMention.message_id == m.id))
        record_event(db, c, "message.deleted", {"message": message_out(db, m)})
        db.commit()


@router.get("/{channel_id}/threads/{message_id}")
def thread(
    workspace_id: str,
    channel_id: str,
    message_id: str,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id)
    root = find_message(db, c.id, message_id)
    if root.thread_root_id:
        raise HTTPException(404, "Thread not found")
    query = select(Message).where(Message.channel_id == c.id, Message.thread_root_id == root.id)
    if before:
        query = query.where(Message.seq < before)
    rows = list(db.scalars(query.order_by(Message.seq.desc()).limit(limit + 1)))
    return {
        "root": message_out(db, root),
        "messages": [message_out(db, m) for m in rows[:limit]],
        "next_cursor": rows[limit - 1].seq if len(rows) > limit else None,
        "last_seq": c.last_seq,
    }


@router.post("/{channel_id}/read", dependencies=write)
def mark_read(
    workspace_id: str,
    channel_id: str,
    data: ReadInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    c, _ = channel_access(db, workspace_id, channel_id, user.id, lock=True)
    read = db.scalar(
        select(ChannelReadState).where(
            ChannelReadState.channel_id == c.id, ChannelReadState.user_id == user.id
        )
    )
    if not read:
        read = ChannelReadState(
            workspace_id=workspace_id, channel_id=c.id, user_id=user.id, last_read_seq=0
        )
        db.add(read)
    read.last_read_seq = max(read.last_read_seq, min(data.last_read_seq, c.last_seq))
    record_event(db, c, "read.updated", {"user_id": user.id, "last_read_seq": read.last_read_seq})
    db.commit()
    return {"last_read_seq": read.last_read_seq}


@router.post("/{channel_id}/attachments", status_code=201, dependencies=write)
async def upload_image(
    workspace_id: str,
    channel_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    channel_access(db, workspace_id, channel_id, user.id, write=True)
    # Raw binary keeps the parser bounded; never trust Content-Length or MIME.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Images must be between 1 byte and 5 MB")
    kind, width, height = inspect_image(bytes(data))
    # Recheck after a slow upload, holding the same workspace lock as removal.
    channel_access(db, workspace_id, channel_id, user.id, lock=True, write=True)
    key = storage.put(bytes(data))
    item = Attachment(
        workspace_id=workspace_id,
        channel_id=channel_id,
        uploader_id=user.id,
        storage_key=key,
        content_type=kind,
        size=len(data),
        width=width,
        height=height,
    )
    db.add(item)
    try:
        db.commit()
    except Exception:
        storage.delete(key)
        raise
    return attachment_out(item)


@router.get("/{channel_id}/attachments/{attachment_id}")
def download_image(
    workspace_id: str,
    channel_id: str,
    attachment_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    channel_access(db, workspace_id, channel_id, user.id)
    item = db.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.workspace_id == workspace_id,
            Attachment.channel_id == channel_id,
        )
    )
    if not item or (not item.message_id and item.uploader_id != user.id):
        raise HTTPException(404, "Attachment not found or unavailable")
    if item.message_id and db.get(Message, item.message_id).deleted_at:
        raise HTTPException(404, "Attachment not found or unavailable")
    path = storage.path(item.storage_key)
    if not path.is_file():
        raise HTTPException(404, "Attachment not found or unavailable")
    return FileResponse(
        path,
        media_type=item.content_type,
        headers={
            "Content-Disposition": 'inline; filename="image"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
