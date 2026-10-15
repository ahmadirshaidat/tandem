import re
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.channels.models import (
    Attachment,
    Channel,
    ChannelEvent,
    ChannelMember,
    ChannelReadState,
    Message,
    MessageMention,
)
from app.core.config import settings
from app.core.models import Membership, User
from app.workspaces.permissions import LEVEL

NOT_FOUND = "Channel not found or you do not have access"


def channel_access(
    db: Session, workspace_id: str, channel_id: str, user_id: str, *, lock=False, write=False
):
    # Acquire workspace first for all writes, matching membership mutations.
    if lock:
        from app.core.models import Workspace

        db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    member = db.scalar(
        select(Membership)
        .where(Membership.workspace_id == workspace_id, Membership.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    channel = db.scalar(
        select(Channel)
        .where(Channel.workspace_id == workspace_id, Channel.id == channel_id)
        .execution_options(populate_existing=True)
    )
    joined = (
        db.scalar(
            select(ChannelMember.id).where(
                ChannelMember.channel_id == channel_id, ChannelMember.user_id == user_id
            )
        )
        if channel
        else None
    )
    if not member or not channel or (channel.is_private and not joined):
        raise HTTPException(404, NOT_FOUND)
    if lock:
        channel = db.scalar(
            select(Channel)
            .where(Channel.id == channel_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if write and channel.archived:
        raise HTTPException(409, "This channel is archived")
    return channel, member


def can_manage(member, minimum="editor"):
    if LEVEL[member.role] < LEVEL[minimum]:
        raise HTTPException(403, "Your role cannot perform this action")


def visible_channels(db, workspace_id, user_id):
    if not db.scalar(
        select(Membership.id).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user_id
        )
    ):
        raise HTTPException(404, "Workspace not found or you do not have access")
    private = select(ChannelMember.channel_id).where(ChannelMember.user_id == user_id)
    return list(
        db.scalars(
            select(Channel)
            .where(
                Channel.workspace_id == workspace_id,
                (~Channel.is_private) | Channel.id.in_(private),
            )
            .order_by(Channel.created_at, Channel.id)
        )
    )


def join_public(db, workspace_id, user_id):
    for channel in db.scalars(
        select(Channel).where(Channel.workspace_id == workspace_id, Channel.is_private.is_(False))
    ):
        db.add(ChannelMember(workspace_id=workspace_id, channel_id=channel.id, user_id=user_id))


def default_channel(db, workspace_id, user_id):
    channel = Channel(
        workspace_id=workspace_id, name="general", topic="A place for the whole team."
    )
    db.add(channel)
    db.flush()
    db.add(ChannelMember(workspace_id=workspace_id, channel_id=channel.id, user_id=user_id))


def attachment_out(item):
    return {
        "id": item.id,
        "content_type": item.content_type,
        "size": item.size,
        "width": item.width,
        "height": item.height,
        "url": f"/api/workspaces/{item.workspace_id}/channels/{item.channel_id}/attachments/{item.id}",
    }


def message_out(db, message):
    user = db.get(User, message.author_id) if message.author_id else None
    mentions = (
        list(db.scalars(select(MessageMention).where(MessageMention.message_id == message.id)))
        if not message.deleted_at
        else []
    )
    attachments = (
        list(db.scalars(select(Attachment).where(Attachment.message_id == message.id)))
        if not message.deleted_at
        else []
    )
    replies = db.scalar(
        select(func.count()).select_from(Message).where(Message.thread_root_id == message.id)
    )
    from app.agent.models import AgentRun
    from app.agent.service import run_out

    run = db.get(AgentRun, message.client_message_id) if message.actor_type == "agent" else None
    return {
        "agent_run": run_out(db, run) if run else None,
        "id": message.id,
        "workspace_id": message.workspace_id,
        "channel_id": message.channel_id,
        "author": {
            "id": user.id if user else message.workspace_id,
            "name": user.name if user else "Agent",
            "type": message.actor_type,
        },
        "body": "" if message.deleted_at else message.body,
        "seq": message.seq,
        "client_message_id": message.client_message_id,
        "thread_root_id": message.thread_root_id,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
        "created_at": message.created_at.isoformat(),
        "mentions": [{"user_id": m.user_id, "is_agent": m.is_agent} for m in mentions],
        "mentions_agent": any(m.is_agent for m in mentions),
        "attachments": [attachment_out(a) for a in attachments],
        "reply_count": replies,
    }


def channel_out(db, channel, user_id):
    read = (
        db.scalar(
            select(ChannelReadState.last_read_seq).where(
                ChannelReadState.channel_id == channel.id, ChannelReadState.user_id == user_id
            )
        )
        or 0
    )
    unread_query = select(Message.id).where(
        Message.channel_id == channel.id,
        Message.seq > read,
        or_(Message.author_id != user_id, Message.actor_type == "agent"),
        Message.deleted_at.is_(None),
    )
    unread = db.scalar(select(func.count()).select_from(unread_query.subquery()))
    mentions = db.scalar(
        select(func.count())
        .select_from(MessageMention)
        .where(MessageMention.message_id.in_(unread_query), MessageMention.user_id == user_id)
    )
    joined = bool(
        db.scalar(
            select(ChannelMember.id).where(
                ChannelMember.channel_id == channel.id, ChannelMember.user_id == user_id
            )
        )
    )
    return {
        "id": channel.id,
        "workspace_id": channel.workspace_id,
        "project_id": channel.project_id,
        "name": channel.name,
        "topic": channel.topic,
        "is_private": channel.is_private,
        "archived": channel.archived,
        "last_seq": channel.last_seq,
        "unread_count": unread,
        "mention_count": mentions,
        "joined": joined,
        "last_read_seq": read,
    }


def record_event(db, channel, type, data):
    channel.last_seq += 1
    db.add(
        ChannelEvent(
            workspace_id=channel.workspace_id,
            channel_id=channel.id,
            seq=channel.last_seq,
            type=type,
            payload=data,
        )
    )
    return channel.last_seq


def parse_mentions(db, channel, message):
    db.execute(delete(MessageMention).where(MessageMention.message_id == message.id))
    members = db.execute(
        select(User).join(Membership).where(Membership.workspace_id == channel.workspace_id)
    ).scalars()
    names = {user.name.casefold(): user.id for user in members}
    # Longest names first; full display names and the composer use the same spelling.
    targets = {"agent": None, **names}
    targets["agent"] = None  # Agent is reserved, even if a member chooses that name.
    pattern = (
        r"(?<![\w@])@("
        + "|".join(re.escape(n) for n in sorted(targets, key=len, reverse=True))
        + r")(?![\w-])"
    )
    found = {
        match.group(1).casefold() for match in re.finditer(pattern, message.body, re.IGNORECASE)
    }
    visible_users = (
        set(db.scalars(select(ChannelMember.user_id).where(ChannelMember.channel_id == channel.id)))
        if channel.is_private
        else None
    )
    for name in found:
        target = targets[name]
        if target is not None and visible_users is not None and target not in visible_users:
            continue
        db.add(
            MessageMention(
                workspace_id=channel.workspace_id,
                channel_id=channel.id,
                message_id=message.id,
                user_id=target,
                is_agent=target is None,
            )
        )
    db.flush()


class SendLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.hits = defaultdict(deque)

    def check(self, user_id):
        tick = time.monotonic()
        with self.lock:
            for key in list(self.hits):
                q = self.hits[key]
                while q and q[0] < tick - 60:
                    q.popleft()
                if not q:
                    del self.hits[key]
            if len(self.hits[user_id]) >= settings.message_requests_per_minute:
                raise HTTPException(
                    429, "Too many messages. Try again shortly.", headers={"Retry-After": "60"}
                )
            self.hits[user_id].append(tick)


send_limiter = SendLimiter()
