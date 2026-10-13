from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select, text

from app.core.db import engine
from app.core.models import Invitation, Membership
from app.core.security import now


def workspace(client, name="Studio North"):
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def invite(owner, wid, email, role="editor"):
    response = owner.post(f"/api/workspaces/{wid}/invitations", json={"email": email, "role": role})
    assert response.status_code == 201, response.text
    return parse_qs(urlsplit(response.json()["invite_url"]).query)["token"][0], response.json()


def add_member(owner, client_factory, wid, email, role):
    client, user = client_factory(email)
    token, _ = invite(owner, wid, email, role)
    response = client.post(f"/api/invitations/{token}/accept")
    assert response.status_code == 200, response.text
    member = next(
        item
        for item in owner.get(f"/api/workspaces/{wid}/members").json()
        if item["user_id"] == user["id"]
    )
    return client, member


def test_health_and_migration_vector_extension(client):
    assert client.get("/health").json() == {"status": "ok", "database": "connected", "vector": True}
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
            == "vector"
        )


def test_register_create_invite_join_and_switch(client_factory):
    owner, _ = client_factory("owner@example.com", "Owner")
    first = workspace(owner)
    assert first["role"] == "owner"
    second = workspace(owner, "Another team")
    member, record = add_member(owner, client_factory, first["id"], "editor@example.com", "editor")
    assert record["role"] == "editor"
    assert {item["id"] for item in owner.get("/api/workspaces").json()} == {
        first["id"],
        second["id"],
    }
    assert [item["id"] for item in member.get("/api/workspaces").json()] == [first["id"]]
    assert member.get(f"/api/workspaces/{first['id']}").json()["role"] == "editor"


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_viewer_and_editor_cannot_manage_members_or_settings(client_factory, role):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    client, member = add_member(owner, client_factory, wid, "member@example.com", role)
    assert client.get(f"/api/workspaces/{wid}/members").status_code == 200
    assert (
        client.post(
            f"/api/workspaces/{wid}/invitations",
            json={"email": "new@example.com", "role": "editor"},
        ).status_code
        == 403
    )
    assert client.get(f"/api/workspaces/{wid}/invitations").status_code == 403
    assert (
        client.patch(
            f"/api/workspaces/{wid}/members/{member['id']}", json={"role": "admin"}
        ).status_code
        == 403
    )
    assert client.delete(f"/api/workspaces/{wid}/members/{member['id']}").status_code == 403
    assert client.patch(f"/api/workspaces/{wid}", json={"name": "Nope"}).status_code == 403


def test_admin_can_manage_members_but_not_ownership(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    admin, _ = add_member(owner, client_factory, wid, "admin@example.com", "admin")
    _, member = add_member(owner, client_factory, wid, "editor@example.com", "editor")
    assert (
        admin.patch(
            f"/api/workspaces/{wid}/members/{member['id']}", json={"role": "viewer"}
        ).status_code
        == 200
    )
    assert (
        admin.patch(
            f"/api/workspaces/{wid}/members/{member['id']}", json={"role": "owner"}
        ).status_code
        == 403
    )
    own = next(
        item
        for item in owner.get(f"/api/workspaces/{wid}/members").json()
        if item["role"] == "owner"
    )
    assert (
        admin.patch(
            f"/api/workspaces/{wid}/members/{own['id']}", json={"role": "admin"}
        ).status_code
        == 403
    )
    token, invitation = invite(admin, wid, "new@example.com")
    assert token
    assert admin.delete(f"/api/workspaces/{wid}/invitations/{invitation['id']}").status_code == 204
    assert admin.patch(f"/api/workspaces/{wid}", json={"name": "Updated"}).status_code == 200
    assert admin.delete(f"/api/workspaces/{wid}/members/{member['id']}").status_code == 204


def test_last_owner_cannot_be_removed_or_demoted_and_transfer_works(client_factory):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    own = owner.get(f"/api/workspaces/{wid}/members").json()[0]
    assert owner.delete(f"/api/workspaces/{wid}/members/{own['id']}").status_code == 409
    assert (
        owner.patch(
            f"/api/workspaces/{wid}/members/{own['id']}", json={"role": "editor"}
        ).status_code
        == 409
    )
    _, member = add_member(owner, client_factory, wid, "newowner@example.com", "admin")
    assert (
        owner.patch(
            f"/api/workspaces/{wid}/members/{member['id']}", json={"role": "owner"}
        ).status_code
        == 200
    )
    assert (
        owner.patch(
            f"/api/workspaces/{wid}/members/{own['id']}", json={"role": "viewer"}
        ).status_code
        == 200
    )
    assert owner.get(f"/api/workspaces/{wid}").json()["role"] == "viewer"


def test_workspace_isolation_covers_every_scoped_endpoint(client_factory):
    alice, _ = client_factory("alice@example.com")
    bob, _ = client_factory("bob@example.com")
    aid, bid = workspace(alice)["id"], workspace(bob)["id"]
    member_id = bob.get(f"/api/workspaces/{bid}/members").json()[0]["id"]
    _, invitation = invite(bob, bid, "invitee@example.com")
    checks = [
        ("GET", f"/{bid}", None),
        ("PATCH", f"/{bid}", {"name": "Leaked"}),
        ("GET", f"/{bid}/members", None),
        ("PATCH", f"/{bid}/members/{member_id}", {"role": "viewer"}),
        ("DELETE", f"/{bid}/members/{member_id}", None),
        ("GET", f"/{bid}/invitations", None),
        ("POST", f"/{bid}/invitations", {"email": "leak@example.com", "role": "editor"}),
        ("DELETE", f"/{bid}/invitations/{invitation['id']}", None),
    ]
    for method, path, body in checks:
        response = alice.request(method, f"/api/workspaces{path}", json=body)
        assert response.status_code == 404, (method, path, response.text)
    # Guessed IDs are also protected when nested under a workspace the user owns.
    assert (
        alice.patch(
            f"/api/workspaces/{aid}/members/{member_id}", json={"role": "viewer"}
        ).status_code
        == 404
    )
    assert alice.delete(f"/api/workspaces/{aid}/invitations/{invitation['id']}").status_code == 404
    assert {item["id"] for item in alice.get("/api/workspaces").json()} == {aid}


def test_invitation_is_single_use_email_bound_and_expiring(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    invited, _ = client_factory("invited@example.com")
    other, _ = client_factory("other@example.com")
    wid = workspace(owner)["id"]
    token, _ = invite(owner, wid, "invited@example.com", "viewer")
    assert invited.get(f"/api/invitations/{token}").json()["workspace_name"] == "Studio North"
    assert other.post(f"/api/invitations/{token}/accept").status_code == 403
    assert invited.post(f"/api/invitations/{token}/accept").json()["role"] == "viewer"
    assert invited.post(f"/api/invitations/{token}/accept").status_code == 410
    token, invitation = invite(owner, wid, "other@example.com")
    item = db.get(Invitation, invitation["id"])
    item.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert other.post(f"/api/invitations/{token}/accept").status_code == 410


def test_reissue_revocation_and_removed_member_access(client_factory):
    owner, _ = client_factory("owner@example.com")
    target, _ = client_factory("target@example.com")
    wid = workspace(owner)["id"]
    old, _ = invite(owner, wid, "target@example.com")
    new, invitation = invite(owner, wid, "target@example.com")
    assert target.get(f"/api/invitations/{old}").status_code == 410
    assert owner.delete(f"/api/workspaces/{wid}/invitations/{invitation['id']}").status_code == 204
    assert target.post(f"/api/invitations/{new}/accept").status_code == 410
    new, _ = invite(owner, wid, "target@example.com")
    assert target.post(f"/api/invitations/{new}/accept").status_code == 200
    member = next(
        item
        for item in owner.get(f"/api/workspaces/{wid}/members").json()
        if item["email"] == "target@example.com"
    )
    assert owner.delete(f"/api/workspaces/{wid}/members/{member['id']}").status_code == 204
    assert target.get(f"/api/workspaces/{wid}/members").status_code == 404


def test_two_concurrent_accepts_create_one_membership(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    target, user = client_factory("target@example.com")
    wid = workspace(owner)["id"]
    token, _ = invite(owner, wid, "target@example.com")
    # The cookie state is stable: acceptance does not rotate the session.
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda _: target.post(f"/api/invitations/{token}/accept").status_code, range(2)
            )
        )
    assert sorted(statuses) == [200, 410]
    assert (
        len(
            list(
                db.scalars(
                    select(Membership).where(
                        Membership.workspace_id == wid, Membership.user_id == user["id"]
                    )
                )
            )
        )
        == 1
    )


def test_invalid_workspace_and_role_inputs(client_factory):
    owner, _ = client_factory("owner@example.com")
    assert owner.post("/api/workspaces", json={"name": " "}).status_code == 422
    wid = workspace(owner)["id"]
    assert (
        owner.post(
            f"/api/workspaces/{wid}/invitations", json={"email": "not-email", "role": "root"}
        ).status_code
        == 422
    )


def test_concurrent_owner_demotions_preserve_one_owner(client_factory, db):
    owner, _ = client_factory("owner@example.com")
    wid = workspace(owner)["id"]
    second, member = add_member(owner, client_factory, wid, "second@example.com", "admin")
    own = next(
        item
        for item in owner.get(f"/api/workspaces/{wid}/members").json()
        if item["role"] == "owner"
    )
    assert (
        owner.patch(
            f"/api/workspaces/{wid}/members/{member['id']}", json={"role": "owner"}
        ).status_code
        == 200
    )

    def demote(item):
        client, member_id = item
        return client.patch(
            f"/api/workspaces/{wid}/members/{member_id}", json={"role": "editor"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(demote, [(owner, own["id"]), (second, member["id"])]))
    assert sorted(statuses) == [200, 409]
    db.expire_all()
    assert (
        len(
            list(
                db.scalars(
                    select(Membership).where(
                        Membership.workspace_id == wid, Membership.role == "owner"
                    )
                )
            )
        )
        == 1
    )
