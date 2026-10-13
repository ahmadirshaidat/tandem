import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.auth.schemas import EmailInput, Login, Register, ResetPassword, UserOut
from app.core.config import settings
from app.core.db import get_db
from app.core.mail import send_reset
from app.core.models import PasswordReset, Session, User
from app.core.rate_limit import limiter
from app.core.security import (
    DUMMY_HASH,
    REFRESH_COOKIE,
    clear_session,
    csrf_check,
    current_user,
    digest,
    hasher,
    now,
    set_session,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(limiter), Depends(csrf_check)],
)
def register(data: Register, response: Response, db: DBSession = Depends(get_db)):
    user = User(email=data.email, name=data.name, password_hash=hasher.hash(data.password))
    db.add(user)
    try:
        db.flush()
        set_session(db, user, response)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists") from None
    return user


@router.post("/login", response_model=UserOut, dependencies=[Depends(limiter), Depends(csrf_check)])
def login(data: Login, response: Response, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    valid = verify_password(user.password_hash if user else DUMMY_HASH, data.password)
    if not user or not valid:
        raise HTTPException(401, "Email or password is incorrect")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(data.password)
    set_session(db, user, response)
    db.commit()
    return user


@router.get("/csrf")
def csrf(response: Response):
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        "tandem_csrf", token, path="/", secure=settings.cookie_secure, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": token}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/refresh", dependencies=[Depends(limiter), Depends(csrf_check)])
def refresh(request: Request, response: Response, db: DBSession = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    session = db.scalar(
        select(Session).where(Session.token_hash == digest(token or "")).with_for_update()
    )
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Session expired. Please log in again.")
    if session.revoked_at:
        db.execute(
            update(Session).where(Session.family_id == session.family_id).values(revoked_at=now())
        )
        db.commit()
        raise HTTPException(401, "Session expired. Please log in again.")
    user = db.get(User, session.user_id)
    session.revoked_at = now()
    set_session(db, user, response, session.family_id)
    db.commit()
    return {"message": "Session refreshed"}


@router.post("/logout", dependencies=[Depends(csrf_check)])
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    session = db.scalar(
        select(Session).where(Session.token_hash == digest(request.cookies.get(REFRESH_COOKIE, "")))
    )
    if session:
        db.execute(
            update(Session).where(Session.family_id == session.family_id).values(revoked_at=now())
        )
        db.commit()
    clear_session(response)
    return {"message": "Logged out"}


@router.post("/forgot-password", dependencies=[Depends(limiter), Depends(csrf_check)])
def forgot(data: EmailInput, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    if user:
        token = secrets.token_urlsafe(48)
        db.add(
            PasswordReset(
                user_id=user.id, token_hash=digest(token), expires_at=now() + timedelta(minutes=30)
            )
        )
        send_reset(user.email, f"{settings.frontend_url}/reset-password?token={token}")
        db.commit()
    return {"message": "If an account exists, a password reset link has been sent."}


@router.post("/reset-password", dependencies=[Depends(limiter), Depends(csrf_check)])
def reset(data: ResetPassword, db: DBSession = Depends(get_db)):
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest(data.token)))
    if not reset or reset.used_at or reset.expires_at <= now():
        raise HTTPException(400, "This reset link has expired or has already been used")
    # Lock the user so simultaneous distinct reset links cannot overwrite passwords.
    user = db.scalar(select(User).where(User.id == reset.user_id).with_for_update())
    db.refresh(reset)
    if reset.used_at or reset.expires_at <= now():
        raise HTTPException(400, "This reset link has expired or has already been used")
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id).values(used_at=now()))
    user.password_hash = hasher.hash(data.password)
    db.execute(update(Session).where(Session.user_id == user.id).values(revoked_at=now()))
    db.commit()
    return {"message": "Password updated. Please log in."}
