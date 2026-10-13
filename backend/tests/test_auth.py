import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.models import PasswordReset, Session, User
from app.core.security import digest, now, verify_password
from app.main import app


def test_register_login_logout_and_secure_storage(client, db, caplog):
    password = "my-private-long-password"
    response = client.post(
        "/api/auth/register",
        json={"email": "Alex@Example.com", "name": " Alex ", "password": password},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "alex@example.com"
    assert response.json()["name"] == "Alex"
    assert "password" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(user.password_hash, password)
    token = client.cookies.get("tandem_refresh")
    assert db.scalar(select(Session)).token_hash == digest(token)
    assert client.get("/api/auth/me").status_code == 200
    access = client.cookies.get("tandem_access")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("tandem_access", access)
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": "alex@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "alex@example.com", "password": password}
        ).status_code
        == 200
    )
    assert password not in caplog.text


def test_invalid_inputs_do_not_echo_passwords(client):
    response = client.post(
        "/api/auth/register", json={"email": "invalid", "name": " ", "password": "secret"}
    )
    assert response.status_code == 422
    assert "secret" not in response.text
    assert {item["field"] for item in response.json()["error"]["details"]} == {
        "email",
        "name",
        "password",
    }


def test_duplicate_email_is_case_insensitive(client_factory, client):
    client_factory("alex@example.com")
    response = client.post(
        "/api/auth/register",
        json={"email": "Alex@Example.com", "name": "A", "password": "another-long-password"},
    )
    assert response.status_code == 409


def test_refresh_rotation_and_reuse_revoke_family(client_factory, db):
    client, _ = client_factory("alex@example.com")
    old = client.cookies.get("tandem_refresh")
    assert client.post("/api/auth/refresh").status_code == 200
    fresh = client.cookies.get("tandem_refresh")
    assert old != fresh
    assert client.get("/api/auth/me").status_code == 200
    client.cookies.clear()
    client.cookies.set("tandem_refresh", old, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.clear()
    client.cookies.set("tandem_refresh", fresh, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    db.expire_all()
    assert all(item.revoked_at for item in db.scalars(select(Session)))


def test_expired_sessions_are_rejected(client_factory, db):
    client, _ = client_factory("alex@example.com")
    session = db.scalar(select(Session))
    session.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/refresh").status_code == 401


def test_csrf_and_untrusted_origin_are_rejected():
    with TestClient(app) as client:
        data = {"email": "alex@example.com", "name": "A", "password": "a-long-test-password"}
        assert client.post("/api/auth/register", json=data).status_code == 403
        token = client.get("/api/auth/csrf").json()["csrf_token"]
        assert (
            client.post(
                "/api/auth/register",
                json=data,
                headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
            ).status_code
            == 403
        )


def test_auth_rate_limit_returns_retry_after(client):
    for _ in range(settings.auth_rate_limit):
        response = client.post(
            "/api/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
        )
        assert response.status_code == 401
    response = client.post(
        "/api/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
    )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_forgot_password_does_not_disclose_accounts(client_factory, client):
    client_factory("alex@example.com")
    known = client.post("/api/auth/forgot-password", json={"email": "alex@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(list(settings.mail_outbox.glob("*.eml"))) == 1


def test_reset_password_is_single_use_and_revokes_sessions(client_factory, db):
    client, _ = client_factory("alex@example.com")
    assert (
        client.post("/api/auth/forgot-password", json={"email": "alex@example.com"}).status_code
        == 200
    )
    mail = next(settings.mail_outbox.glob("*.eml")).read_text()
    # Parse the plain-text email with the email package to handle MIME wrapping.
    from email import policy
    from email.parser import Parser

    body = Parser(policy=policy.default).parsestr(mail).get_content()
    token = re.search(r"token=([A-Za-z0-9_-]+)", body).group(1)
    assert db.scalar(select(PasswordReset)).token_hash == digest(token)
    response = client.post(
        "/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "alex@example.com", "password": "a-long-test-password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "alex@example.com", "password": "a-brand-new-password"},
        ).status_code
        == 200
    )


def test_expired_reset_is_rejected(client_factory, db):
    client, user = client_factory("alex@example.com")
    token = "x" * 48
    db.add(
        PasswordReset(
            user_id=user["id"], token_hash=digest(token), expires_at=now() - timedelta(seconds=1)
        )
    )
    db.commit()
    assert (
        client.post(
            "/api/auth/reset-password", json={"token": token, "password": "a-new-long-password"}
        ).status_code
        == 400
    )


def test_concurrent_reset_links_can_only_change_password_once(client_factory, db):
    client, user = client_factory("alex@example.com")
    tokens = ["a" * 48, "b" * 48]
    for token in tokens:
        db.add(
            PasswordReset(
                user_id=user["id"],
                token_hash=digest(token),
                expires_at=now() + timedelta(minutes=30),
            )
        )
    db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda token: (
                    client.post(
                        "/api/auth/reset-password",
                        json={"token": token, "password": "new-long-password"},
                    ).status_code
                ),
                tokens,
            )
        )
    assert sorted(statuses) == [200, 400]
