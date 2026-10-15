import base64
import io
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from sqlalchemy import func, select
from starlette.websockets import WebSocketDisconnect
from test_workspaces import add_member, workspace

from app.channels.models import ChannelEvent, ChannelMember, Message, MessageMention
from app.channels.service import send_limiter
from app.core.config import settings


def channel(client, wid, private=False, name="discussion"):
    response = client.post(
        f"/api/workspaces/{wid}/channels", json={"name": name, "is_private": private}
    )
    assert response.status_code == 201, response.text
    return response.json()


def path(wid, cid):
    return f"/api/workspaces/{wid}/channels/{cid}"


def send(client, base, body="hello", **extra):
    response = client.post(
        base + "/messages", json={"body": body, "client_message_id": uuid.uuid4().hex, **extra}
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def socket(client):
    return client.websocket_connect("/api/ws", headers={"origin": settings.frontend_url})


def subscribe(ws, wid, cid=None, seq=0):
    ws.send_json({"type": "subscribe", "workspace_id": wid, "channel_id": cid, "last_seq": seq})


def until(ws, kind):
    for _ in range(100):
        event = ws.receive_json()
        if event["type"] == kind:
            return event
    raise AssertionError(f"No {kind} event")


def image(kind="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (3, 2), "blue").save(output, format=kind)
    return output.getvalue()


def test_defaults_roles_unread_mentions_threads_and_pagination(client_factory, db):
    owner, _ = client_factory("owner@example.com", "Owner")
    wid = workspace(owner)["id"]
    general = owner.get(f"/api/workspaces/{wid}/channels").json()[0]
    assert general["name"] == "general" and general["joined"]
    viewer, member = add_member(owner, client_factory, wid, "viewer@example.com", "viewer")
    assert viewer.get(f"/api/workspaces/{wid}/channels").json()[0]["joined"]
    assert viewer.post(f"/api/workspaces/{wid}/channels", json={"name": "nope"}).status_code == 403
    c = channel(owner, wid)
    base = path(wid, c["id"])
    assert viewer.patch(base, json={"topic": "no"}).status_code == 403
    assert viewer.post(base + "/members", json={"user_id": member["user_id"]}).status_code == 403
    root = send(owner, base, "@Teammate and @Agent **hello**")
    assert root["mentions_agent"] and len(root["mentions"]) == 2
    assert db.scalar(select(func.count()).select_from(MessageMention)) == 2
    off_reply = owner.get(base + "/messages").json()["messages"][0]
    assert off_reply["author"]["type"] == "agent"
    assert "agent is off" in off_reply["body"]
    assert owner.get(f"/api/workspaces/{wid}/channels").json()[1]["unread_count"] == 1
    counts = viewer.get(base).json()
    assert counts["mention_count"] == 1 and counts["unread_count"] == 2
    reply = send(viewer, base, "A question", thread_root_id=root["id"])
    assert reply["thread_root_id"] == root["id"]
    assert owner.get(base + f"/threads/{root['id']}").json()["messages"][0]["id"] == reply["id"]
    assert owner.patch(base + f"/messages/{reply['id']}", json={"body": "no"}).status_code == 403
    assert owner.delete(base + f"/messages/{reply['id']}").status_code == 204
    rows = [send(viewer, base, str(n)) for n in range(3)]
    first = viewer.get(base + "/messages?limit=2").json()
    second = viewer.get(base + f"/messages?limit=2&before={first['next_cursor']}").json()
    third = viewer.get(base + f"/messages?limit=2&before={second['next_cursor']}").json()
    assert [m["id"] for m in first["messages"] + second["messages"] + third["messages"]] == [
        m["id"] for m in reversed([root, off_reply, *rows])
    ]
    assert viewer.post(base + "/read", json={"last_read_seq": 1000}).status_code == 200
    assert viewer.get(base).json()["unread_count"] == 0
    assert viewer.post(base + "/leave").json()["joined"] is False
    assert viewer.post(base + "/join").json()["joined"] is True
    assert owner.patch(base, json={"archived": True}).json()["archived"]
    assert (
        viewer.post(
            base + "/messages", json={"body": "no", "client_message_id": "archived"}
        ).status_code
        == 409
    )


def test_concurrent_idempotent_send_and_constraints(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    c = channel(owner, wid)
    base = path(wid, c["id"])
    data = {"body": "One send", "client_message_id": "same-id"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: owner.post(base + "/messages", json=data), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert db.scalar(select(func.count()).select_from(Message)) == 1
    assert owner.post(base + "/messages", json={**data, "body": "x" * 4001}).status_code == 422
    assert (
        owner.post(base + "/messages", json={"body": " ", "client_message_id": "empty"}).status_code
        == 422
    )


def test_private_and_workspace_isolation_on_every_surface(client_factory):
    owner, _ = client_factory("owner@example.com")
    outsider, _ = client_factory("outsider@example.com")
    wid = workspace(owner)["id"]
    other = workspace(outsider)["id"]
    member, _ = add_member(owner, client_factory, wid, "member@example.com", "editor")
    c = channel(owner, wid, private=True, name="hidden-name")
    base = path(wid, c["id"])
    m = send(owner, base, "private body")
    a = owner.post(base + "/attachments", content=image()).json()
    assert all(
        item["id"] != c["id"] for item in member.get(f"/api/workspaces/{wid}/channels").json()
    )
    for client in [member, outsider]:
        for method, endpoint, body in [
            ("GET", "", None),
            ("PATCH", "", {"name": "change"}),
            ("GET", "/members", None),
            ("POST", "/members", {"user_id": "x"}),
            ("POST", "/join", None),
            ("POST", "/leave", None),
            ("GET", "/messages", None),
            ("POST", "/messages", {"body": "x", "client_message_id": "x"}),
            ("GET", f"/messages/{m['id']}", None),
            ("PATCH", f"/messages/{m['id']}", {"body": "x"}),
            ("DELETE", f"/messages/{m['id']}", None),
            ("GET", f"/threads/{m['id']}", None),
            ("POST", "/read", {"last_read_seq": 0}),
            ("GET", f"/attachments/{a['id']}", None),
            ("POST", "/attachments", None),
        ]:
            r = client.request(method, base + endpoint, json=body)
            assert r.status_code == 404, (method, endpoint, r.text)
            assert r.json()["error"]["message"] == "Channel not found or you do not have access"
            assert "hidden-name" not in r.text and "private body" not in r.text
        with socket(client) as ws:
            subscribe(ws, wid, c["id"])
            assert (
                until(ws, "error")["data"]["message"]
                == "Channel not found or you do not have access"
            )
            subscribe(ws, wid, "nonexistent")
            assert (
                until(ws, "error")["data"]["message"]
                == "Channel not found or you do not have access"
            )
    assert owner.get(path(other, c["id"])).status_code == 404
    assert outsider.get(f"/api/workspaces/{wid}/channels").status_code == 404


@pytest.mark.parametrize("kind", ["PNG", "JPEG", "WEBP", "GIF"])
def test_image_magic_dimensions_authenticated_serving_and_deletion(client_factory, kind):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    base = path(wid, channel(owner, wid)["id"])
    r = owner.post(
        base + "/attachments",
        content=image(kind),
        headers={"content-type": "application/x-executable"},
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["width"] == 3 and a["height"] == 2
    assert "storage_key" not in a
    m = send(owner, base, attachment_ids=[a["id"]])
    r = owner.get(a["url"])
    assert r.status_code == 200 and r.headers["x-content-type-options"] == "nosniff"
    owner.delete(base + f"/messages/{m['id']}")
    assert owner.get(a["url"]).status_code == 404
    owner.post("/api/auth/logout")
    assert owner.get(a["url"]).status_code == 401


def test_bad_images_limits_attachment_ownership_and_csrf(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    member, _ = add_member(owner, client_factory, wid, "member@example.com", "viewer")
    base = path(wid, channel(owner, wid)["id"])
    for data in [b"MZ fake.exe", b'<svg onload="alert(1)"></svg>', b"\x89PNG\r\n\x1a\ntruncated"]:
        assert (
            owner.post(
                base + "/attachments", content=data, headers={"Content-Type": "image/png"}
            ).status_code
            == 415
        )
    assert owner.post(base + "/attachments", content=b"x" * (5242880 + 1)).status_code == 413
    corrupt = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aAZkAAAAASUVORK5CYII="
    )
    assert owner.post(base + "/attachments", content=corrupt).status_code == 415
    a = owner.post(base + "/attachments", content=image()).json()
    assert member.get(a["url"]).status_code == 404  # Pending uploads are uploader-only.
    assert (
        member.post(
            base + "/messages",
            json={"body": "x", "client_message_id": "stolen", "attachment_ids": [a["id"]]},
        ).status_code
        == 404
    )
    assert (
        owner.post(
            base + "/messages",
            json={
                "body": "x",
                "client_message_id": "too-many",
                "attachment_ids": [str(n) for n in range(5)],
            },
        ).status_code
        == 422
    )
    assert (
        owner.post(
            base + "/messages",
            json={"body": "x", "client_message_id": "csrf"},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )


def test_realtime_catchup_exact_order_including_edit_and_presence(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    member, _ = add_member(owner, client_factory, wid, "member@example.com", "viewer")
    cid = channel(owner, wid)["id"]
    base = path(wid, cid)
    with socket(owner) as a, socket(member) as b:
        subscribe(a, wid, cid, 1)
        subscribe(b, wid, cid, 1)
        assert len(until(a, "presence.update")["data"]["user_ids"]) >= 1
        b.send_json({"type": "typing.start", "workspace_id": wid, "channel_id": cid})
        assert until(a, "typing.start")["data"]["user_id"]
        b.send_json({"type": "typing.stop", "workspace_id": wid, "channel_id": cid})
        until(a, "typing.stop")
        first = send(member, base, "first")
        initial = until(a, "message.created")
        assert initial["data"]["message"]["id"] == first["id"]
        cursor = initial["seq"]
    missed = [send(member, base, f"missed {n}") for n in range(3)]
    member.patch(base + f"/messages/{missed[0]['id']}", json={"body": "edited while offline"})
    with socket(owner) as a:
        subscribe(a, wid, cid, cursor)
        events = [until(a, "message.created") for _ in range(3)]
        events.append(until(a, "message.updated"))
        assert [e["seq"] for e in events] == list(range(cursor + 1, cursor + 5))
        assert [e["data"]["message"]["id"] for e in events[:3]] == [m["id"] for m in missed]
        assert events[-1]["data"]["message"]["body"] == "edited while offline"
        # Resubscribe at the last cursor, then a new event is the very next message.
        subscribe(a, wid, cid, events[-1]["seq"])
        last = send(member, base, "new after catchup")
        assert until(a, "message.created")["data"]["message"]["id"] == last["id"]
    assert (
        db.scalar(
            select(func.count()).select_from(ChannelEvent).where(ChannelEvent.channel_id == cid)
        )
        == 7
    )


def test_live_private_workspace_removal_and_session_revocation(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    member, record = add_member(owner, client_factory, wid, "member@example.com", "viewer")
    private = channel(owner, wid, private=True)
    base = path(wid, private["id"])
    owner.post(base + "/members", json={"user_id": record["user_id"]})
    with socket(member) as ws:
        subscribe(ws, wid, private["id"], 2)
        until(ws, "presence.update")
        assert owner.delete(base + f"/members/{record['user_id']}").status_code == 204
        event = until(ws, "error")
        assert event["data"]["code"] == "access_revoked"
        send(owner, base, "not delivered")
        subscribe(ws, wid, private["id"])
        assert until(ws, "error")["data"]["code"] == "access_denied"
    public = owner.get(f"/api/workspaces/{wid}/channels").json()[0]
    with socket(member) as ws:
        subscribe(ws, wid, public["id"])
        until(ws, "presence.update")
        owner.delete(f"/api/workspaces/{wid}/members/{record['id']}")
        assert until(ws, "error")["data"]["code"] == "access_revoked"
    with socket(owner) as ws:
        subscribe(ws, wid, public["id"])
        until(ws, "presence.update")
        owner.post("/api/auth/logout")
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4001


def test_origin_session_frame_limits_and_send_limit(client_factory, monkeypatch):
    owner, _ = client_factory("owner@example.com")
    with pytest.raises(WebSocketDisconnect):
        with owner.websocket_connect("/api/ws", headers={"origin": "https://evil.example"}):
            pass
    monkeypatch.setattr(settings, "ws_connections_per_user", 1)
    with socket(owner):
        with pytest.raises(WebSocketDisconnect):
            with socket(owner):
                pass
    with socket(owner) as ws:
        ws.send_text("x" * 8193)
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1009
    with socket(owner) as ws:
        ws.send_bytes(b"binary commands are not supported")
        with pytest.raises(WebSocketDisconnect) as binary:
            ws.receive_json()
        assert binary.value.code == 1003
    wid = workspace(owner)["id"]
    base = path(wid, channel(owner, wid)["id"])
    send_limiter.hits.clear()
    monkeypatch.setattr(settings, "message_requests_per_minute", 1)
    send(owner, base)
    assert (
        owner.post(
            base + "/messages", json={"body": "limited", "client_message_id": "limited"}
        ).status_code
        == 429
    )


def test_migration_backfills_existing_workspace_without_replacing_data(db):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from app.channels.models import Channel
    from app.core.models import Membership, User, Workspace

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    db.commit()
    command.downgrade(config, "5ef693bcfd14")
    try:
        user = User(
            name="Existing member", email="existing@example.com", password_hash="fixture-no-login"
        )
        db.add(user)
        db.flush()
        existing = Workspace(name="Existing workspace")
        db.add(existing)
        db.flush()
        db.add(Membership(workspace_id=existing.id, user_id=user.id, role="owner"))
        db.commit()
        command.upgrade(config, "head")
        channel = db.scalar(select(Channel).where(Channel.workspace_id == existing.id))
        assert channel.name == "general" and not channel.is_private
        assert (
            db.scalar(select(ChannelMember.user_id).where(ChannelMember.channel_id == channel.id))
            == user.id
        )
        assert db.get(Workspace, existing.id).name == "Existing workspace"
        assert db.get(User, user.id).email == "existing@example.com"
    finally:
        db.rollback()
        command.upgrade(config, "head")


def test_workspace_removal_and_reinvite_does_not_restore_private_membership(client_factory, db):
    from test_workspaces import invite

    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    member, record = add_member(owner, client_factory, wid, "member@example.com", "viewer")
    cid = channel(owner, wid, private=True)["id"]
    base = path(wid, cid)
    owner.post(base + "/members", json={"user_id": record["user_id"]})
    assert owner.delete(f"/api/workspaces/{wid}/members/{record['id']}").status_code == 204
    assert not db.scalar(
        select(ChannelMember.id).where(
            ChannelMember.channel_id == cid, ChannelMember.user_id == record["user_id"]
        )
    )
    token, _ = invite(owner, wid, "member@example.com", "viewer")
    assert member.post(f"/api/invitations/{token}/accept").status_code == 200
    assert member.get(base).status_code == 404


def test_socket_commands_limiter_and_expired_typing(client_factory, monkeypatch):
    import time

    from app.channels.gateway import state

    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    member, _ = add_member(owner, client_factory, wid, "member@example.com", "viewer")
    cid = channel(owner, wid)["id"]
    with socket(owner) as a, socket(member) as b:
        subscribe(a, wid, cid, 1)
        subscribe(b, wid, cid, 1)
        until(a, "presence.update")
        b.send_json({"type": "typing.start", "workspace_id": wid, "channel_id": cid})
        until(a, "typing.start")
        with state.lock:
            for key in state.typing:
                state.typing[key] = time.monotonic() - 1
        assert until(a, "typing.stop")["data"]["user_id"]
    monkeypatch.setattr(settings, "ws_frames_per_minute", 10)
    with socket(owner) as ws:
        for _ in range(11):
            ws.send_json({"type": "ping"})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1008
