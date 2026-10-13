import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.db import get_db
from app.core.models import Session, User, new_id

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
ACCESS_COOKIE = "tandem_access"
REFRESH_COOKIE = "tandem_refresh"
CSRF_COOKIE = "tandem_csrf"


def now():
    return datetime.now(UTC)


def digest(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(encoded: str, password: str):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def csrf_check(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != settings.frontend_url:
        raise HTTPException(403, "Untrusted request origin")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(403, "Missing or invalid CSRF token")


def set_session(db: DBSession, user: User, response: Response, family_id: str | None = None):
    raw_token = secrets.token_urlsafe(48)
    session = Session(
        id=new_id(),
        user_id=user.id,
        family_id=family_id or new_id(),
        token_hash=digest(raw_token),
        expires_at=now() + timedelta(days=settings.refresh_days),
    )
    db.add(session)
    db.flush()
    access = jwt.encode(
        {
            "sub": user.id,
            "sid": session.id,
            "exp": now() + timedelta(minutes=settings.access_minutes),
            "iat": now(),
            "iss": "tandem",
            "aud": "tandem-web",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    options = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(
        ACCESS_COOKIE, access, max_age=settings.access_minutes * 60, path="/", **options
    )
    response.set_cookie(
        REFRESH_COOKIE,
        raw_token,
        max_age=settings.refresh_days * 86400,
        path="/api/auth",
        **options,
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=settings.refresh_days * 86400,
        path="/",
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_session(response: Response):
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(
            request.cookies.get(ACCESS_COOKIE, ""),
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="tandem",
            audience="tandem-web",
        )
        session = db.get(Session, payload["sid"])
        if (
            not session
            or session.revoked_at
            or session.expires_at <= now()
            or session.user_id != payload["sub"]
        ):
            raise ValueError("Invalid session")
        user = db.get(User, payload["sub"])
        if user is None:
            raise ValueError("Missing user")
        return user
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Please log in to continue") from None
