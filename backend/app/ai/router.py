import threading
import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import providers
from app.core.config import settings
from app.core.db import get_db
from app.core.models import AITrial, Membership
from app.core.security import csrf_check
from app.workspaces.permissions import membership, require_role

router = APIRouter(prefix="/api/workspaces/{workspace_id}/ai", tags=["AI trial"])


class TrialInput(BaseModel):
    provider: Literal["auto", "groq", "gemini", "deepseek", "openai"] = "auto"
    prompt: str = Field(min_length=1, max_length=4000)

    @field_validator("prompt")
    @classmethod
    def nonempty_prompt(cls, value):
        if not value.strip():
            raise ValueError("Enter a question to try")
        return value.strip()


class TrialLimiter:
    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()
        self.concurrent = threading.BoundedSemaphore(4)

    def check(self, workspace_id, user_id):
        tick = time.monotonic()
        with self.lock:
            for key in list(self.hits):
                queue = self.hits[key]
                while queue and queue[0] <= tick - 60:
                    queue.popleft()
                if not queue:
                    del self.hits[key]
            # A user cannot reset the trial budget by creating/switching workspaces.
            keys = [("user", user_id), ("workspace", workspace_id)]
            if any(len(self.hits[key]) >= settings.ai_requests_per_minute for key in keys):
                raise HTTPException(
                    429, "Trial limit reached. Please wait a minute.", headers={"Retry-After": "60"}
                )
            for key in keys:
                self.hits[key].append(tick)


trial_limiter = TrialLimiter()


@router.get("/providers")
def provider_status(workspace_id: str, member: Membership = Depends(require_role("admin"))):
    return {
        "primary": settings.ai_primary_provider,
        "providers": [
            {
                "id": name,
                "configured": bool(providers.provider_key(name)),
                "model": providers.provider_model(name),
            }
            for name in providers.PROVIDERS
        ],
        "max_prompt_characters": 4000,
        "max_output_tokens": settings.ai_max_output_tokens,
        "requests_per_minute": settings.ai_requests_per_minute,
    }


@router.get("/trials")
def trial_history(
    workspace_id: str,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    trials = db.scalars(
        select(AITrial)
        .where(AITrial.workspace_id == workspace_id)
        .order_by(AITrial.created_at.desc())
        .limit(20)
    )
    return [
        {
            "id": trial.id,
            "status": trial.status,
            "provider": trial.provider_used,
            "attempts": trial.attempts,
            "created_at": trial.created_at,
            "input_tokens": trial.input_tokens,
            "output_tokens": trial.output_tokens,
        }
        for trial in trials
    ]


@router.post("/trials", dependencies=[Depends(csrf_check)])
def run_trial(
    workspace_id: str,
    data: TrialInput,
    member: Membership = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    trial_limiter.check(workspace_id, member.user_id)
    if not trial_limiter.concurrent.acquire(blocking=False):
        raise HTTPException(503, "AI is busy. Please try again shortly.")
    try:
        names = (
            [data.provider]
            if data.provider != "auto"
            else [
                settings.ai_primary_provider,
                *[name for name in providers.PROVIDERS if name != settings.ai_primary_provider],
            ]
        )
        attempts = []
        result = None
        used = None
        for name in names:
            if not providers.provider_key(name):
                attempts.append(
                    {"provider": name, "status": "skipped", "category": "not_configured"}
                )
                continue
            start = time.monotonic()
            try:
                result = providers.complete(name, data.prompt)
                used = name
                attempts.append(
                    {
                        "provider": name,
                        "status": "completed",
                        "elapsed_ms": round((time.monotonic() - start) * 1000),
                    }
                )
                break
            except providers.ProviderFailure as error:
                attempts.append(
                    {
                        "provider": name,
                        "status": "failed",
                        "category": error.category,
                        "http_status": error.status,
                        "elapsed_ms": round((time.monotonic() - start) * 1000),
                    }
                )
                if error.category == "invalid_request":
                    break  # Do not rebill the same invalid prompt against other providers.
        membership(db, workspace_id, member.user_id, "admin")
        record = AITrial(
            workspace_id=workspace_id,
            actor_id=member.user_id,
            requested_provider=data.provider,
            provider_used=used,
            status="completed" if result else "failed",
            input_length=len(data.prompt),
            attempts=attempts,
            input_tokens=result.input_tokens if result else None,
            output_tokens=result.output_tokens if result else None,
        )
        db.add(record)
        db.commit()
        if not result:
            raise HTTPException(
                503,
                "No configured provider answered. Check the trial history and server configuration.",
            )
        return {
            "id": record.id,
            "provider": used,
            "model": providers.provider_model(used),
            "answer": result.text,
            "attempts": attempts,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
    finally:
        trial_limiter.concurrent.release()
