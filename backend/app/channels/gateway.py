import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import anyio
import jwt
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

from app.channels.fanout import fanout
from app.channels.models import ChannelEvent
from app.channels.schemas import SocketCommand, SocketEvent
from app.channels.service import NOT_FOUND, channel_access, channel_out, visible_channels
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import Session
from app.core.security import ACCESS_COOKIE, now

router = APIRouter(tags=["live"])
MAX_FRAME_BYTES = 8192


class EphemeralState:
    """Process-local presence/typing; no content or sessions stored in this map."""

    def __init__(self):
        self.lock = threading.Lock()
        self.connections = {}
        self.typing = {}

    def add(self, connection):
        with self.lock:
            users = sum(c.user_id == connection.user_id for c in self.connections.values())
            ips = sum(c.ip == connection.ip for c in self.connections.values())
            if users >= settings.ws_connections_per_user or ips >= settings.ws_connections_per_ip:
                return False
            self.connections[id(connection)] = connection
            return True

    def remove(self, connection):
        with self.lock:
            self.connections.pop(id(connection), None)
            for key in list(self.typing):
                if key[0] == id(connection):
                    del self.typing[key]
        fanout.publish()

    def set_typing(self, connection, channel_id, active):
        with self.lock:
            key = (id(connection), channel_id)
            if active:
                self.typing[key] = time.monotonic() + 5
            else:
                self.typing.pop(key, None)
        fanout.publish()

    def snapshot(self, channel_id):
        tick = time.monotonic()
        with self.lock:
            candidates = [
                (c.user_id, c.session_id, c.expires, id(c))
                for c in self.connections.values()
                if channel_id in c.channels
            ]
            typing = {
                cid
                for (cid, channel), expiry in self.typing.items()
                if channel == channel_id and expiry > tick
            }
        return candidates, typing


state = EphemeralState()


def authenticated(db, session_id, user_id, expires):
    session = db.get(Session, session_id)
    return bool(
        session
        and session.user_id == user_id
        and not session.revoked_at
        and session.expires_at > now()
        and expires > time.time()
    )


@dataclass(eq=False)
class Connection:
    socket: WebSocket
    user_id: str
    session_id: str
    expires: float
    ip: str
    channels: dict[str, tuple[str, int]] = field(default_factory=dict)
    workspaces: dict[str, dict] = field(default_factory=dict)
    ephemeral: dict = field(default_factory=dict)
    frames: deque = field(default_factory=deque)
    active_at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def emit(self, type, data, workspace_id=None, channel_id=None, seq=None):
        event = SocketEvent(
            type=type, data=data, workspace_id=workspace_id, channel_id=channel_id, seq=seq
        )
        await self.socket.send_json(event.model_dump())

    def inspect(self):
        with SessionLocal() as db:
            if not authenticated(db, self.session_id, self.user_id, self.expires):
                return None
            workspace_snapshots, events, revoked, ephemeral = {}, [], [], {}
            for wid in list(self.workspaces):
                try:
                    workspace_snapshots[wid] = {
                        c.id: channel_out(db, c, self.user_id)
                        for c in visible_channels(db, wid, self.user_id)
                    }
                except HTTPException:
                    revoked.append((wid, None))
            for cid, (wid, cursor) in list(self.channels.items()):
                try:
                    channel_access(db, wid, cid, self.user_id)
                except HTTPException:
                    revoked.append((wid, cid))
                    continue
                rows = list(
                    db.scalars(
                        select(ChannelEvent)
                        .where(ChannelEvent.channel_id == cid, ChannelEvent.seq > cursor)
                        .order_by(ChannelEvent.seq)
                        .limit(200)
                    )
                )
                events.extend((wid, cid, row.seq, row.type, row.payload) for row in rows)
                candidates, typing_ids = state.snapshot(cid)
                users, typing = set(), set()
                for uid, sid, expires, connection_id in candidates:
                    if not authenticated(db, sid, uid, expires):
                        continue
                    try:
                        channel_access(db, wid, cid, uid)
                    except HTTPException:
                        continue
                    users.add(uid)
                    if connection_id in typing_ids:
                        typing.add(uid)
                ephemeral[cid] = (wid, sorted(users), sorted(typing))
            return workspace_snapshots, events, revoked, ephemeral

    async def pump(self):
        async with self.lock:
            result = await anyio.to_thread.run_sync(self.inspect)
            if result is None:
                await self.socket.close(code=4001, reason="Session expired")
                raise WebSocketDisconnect(4001)
            snapshots, events, revoked, ephemeral = result
            for wid, cid in revoked:
                if cid:
                    self.channels.pop(cid, None)
                else:
                    self.workspaces.pop(wid, None)
                    for channel in [key for key, value in self.channels.items() if value[0] == wid]:
                        del self.channels[channel]
                await self.emit("error", {"message": NOT_FOUND, "code": "access_revoked"}, wid, cid)
                fanout.publish()
            for wid, snapshot in snapshots.items():
                previous = self.workspaces.get(wid, {})
                for cid, value in snapshot.items():
                    old = previous.get(cid)
                    # Counts update with messages; metadata events update the sidebar too.
                    if value != old:
                        kind = (
                            "channel.created"
                            if old is None
                            else "channel.archived"
                            if value["archived"] and not old["archived"]
                            else "channel.updated"
                        )
                        await self.emit(kind, {"channel": value}, wid, cid)
                for cid in previous.keys() - snapshot.keys():
                    await self.emit(
                        "error", {"message": NOT_FOUND, "code": "access_revoked"}, wid, cid
                    )
                self.workspaces[wid] = snapshot
            for wid, cid, seq, type, payload in events:
                # Recheck immediately before transmitting: revocation may follow journal read.
                def allowed(wid=wid, cid=cid):
                    with SessionLocal() as db:
                        if not authenticated(db, self.session_id, self.user_id, self.expires):
                            return False
                        try:
                            channel_access(db, wid, cid, self.user_id)
                            return True
                        except HTTPException:
                            return False

                if cid in self.channels and await anyio.to_thread.run_sync(allowed):
                    if seq > self.channels[cid][1]:
                        await self.emit(type, payload, wid, cid, seq)
                        self.channels[cid] = (wid, seq)
            for cid, (wid, users, typing) in ephemeral.items():
                previous_users, previous_typing = self.ephemeral.get(cid, (None, []))
                if users != previous_users:
                    await self.emit("presence.update", {"user_ids": users}, wid, cid)
                for uid in set(typing) - set(previous_typing):
                    await self.emit("typing.start", {"user_id": uid}, wid, cid)
                for uid in set(previous_typing) - set(typing):
                    await self.emit("typing.stop", {"user_id": uid}, wid, cid)
                self.ephemeral[cid] = (users, typing)
            if any(sum(event[1] == cid for event in events) == 200 for cid in self.channels):
                fanout.publish()  # Drain the next bounded replay page without waiting.

    async def command(self, data):
        tick = time.monotonic()
        while self.frames and self.frames[0] < tick - 60:
            self.frames.popleft()
        if len(self.frames) >= settings.ws_frames_per_minute:
            await self.socket.close(code=1008, reason="Too many commands")
            raise WebSocketDisconnect(1008)
        self.frames.append(tick)
        self.active_at = tick
        try:
            command = SocketCommand.model_validate(data)
        except ValidationError:
            async with self.lock:
                await self.emit("error", {"message": "Invalid command", "code": "invalid_command"})
            return
        async with self.lock:

            def validate():
                with SessionLocal() as db:
                    if not authenticated(db, self.session_id, self.user_id, self.expires):
                        raise HTTPException(401, "Session expired")
                    if command.type == "ping":
                        return
                    if not command.workspace_id:
                        raise HTTPException(404, NOT_FOUND)
                    if command.channel_id:
                        c, _ = channel_access(
                            db, command.workspace_id, command.channel_id, self.user_id
                        )
                        if command.last_seq > c.last_seq:
                            raise HTTPException(400, "Invalid replay cursor")
                    else:
                        visible_channels(db, command.workspace_id, self.user_id)

            try:
                await anyio.to_thread.run_sync(validate)
            except HTTPException as error:
                if error.status_code == 401:
                    await self.socket.close(code=4001, reason="Session expired")
                    raise WebSocketDisconnect(4001) from None
                await self.emit(
                    "error",
                    {
                        "message": NOT_FOUND if error.status_code == 404 else error.detail,
                        "code": "access_denied",
                    },
                    command.workspace_id,
                    command.channel_id,
                )
                return
            if command.type == "subscribe":
                if (
                    command.channel_id
                    and command.channel_id not in self.channels
                    and len(self.channels) >= 50
                ) or (
                    not command.channel_id
                    and command.workspace_id not in self.workspaces
                    and len(self.workspaces) >= 10
                ):
                    await self.emit(
                        "error", {"message": "Too many subscriptions", "code": "subscription_limit"}
                    )
                    return
                if command.channel_id:
                    self.channels[command.channel_id] = (command.workspace_id, command.last_seq)
                    self.ephemeral.pop(command.channel_id, None)
                else:
                    self.workspaces.setdefault(command.workspace_id, {})
                fanout.publish()
            elif command.type == "unsubscribe":
                if command.channel_id:
                    self.channels.pop(command.channel_id, None)
                    state.set_typing(self, command.channel_id, False)
                else:
                    self.workspaces.pop(command.workspace_id, None)
                    self.channels = {
                        key: value
                        for key, value in self.channels.items()
                        if value[0] != command.workspace_id
                    }
                fanout.publish()
            elif command.type.startswith("typing.") and command.channel_id in self.channels:
                state.set_typing(self, command.channel_id, command.type == "typing.start")
            # Ping only refreshes the idle deadline; no durable event or message.


@router.websocket("/api/ws")
async def gateway(socket: WebSocket):
    if socket.headers.get("origin") != settings.frontend_url:
        await socket.close(code=1008)
        return
    try:
        payload = jwt.decode(
            socket.cookies.get(ACCESS_COOKIE, ""),
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="tandem",
            audience="tandem-web",
        )
        connection = Connection(
            socket,
            payload["sub"],
            payload["sid"],
            payload["exp"],
            socket.client.host if socket.client else "unknown",
        )

        def valid():
            with SessionLocal() as db:
                return authenticated(
                    db, connection.session_id, connection.user_id, connection.expires
                )

        if not await anyio.to_thread.run_sync(valid):
            raise ValueError("Invalid session")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        await socket.close(code=1008)
        return
    if not state.add(connection):
        await socket.close(code=1008)
        return
    await socket.accept()
    wake, remove = fanout.wake_event()
    wake.set()

    async def receive():
        while True:
            raw = await socket.receive_text()
            if len(raw.encode()) > MAX_FRAME_BYTES:
                await socket.close(code=1009)
                return
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                data = None
            await connection.command(data)

    async def deliver():
        while True:
            try:
                await asyncio.wait_for(wake.wait(), timeout=0.5)
            except TimeoutError:
                pass
            wake.clear()
            if time.monotonic() - connection.active_at > settings.ws_idle_seconds:
                await socket.close(code=1001, reason="Idle connection")
                return
            await connection.pump()

    tasks = [asyncio.create_task(receive()), asyncio.create_task(deliver())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            try:
                task.result()
            except (WebSocketDisconnect, RuntimeError):
                pass
    except asyncio.CancelledError:
        pass  # ASGI shutdown/disconnect cancels the connection task.
    finally:
        remove()
        state.remove(connection)
        for task in tasks:
            task.cancel()
