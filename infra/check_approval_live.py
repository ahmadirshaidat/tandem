"""OPTIONAL synthetic live mention -> proposal -> human-test-owner approval.
Run with the normal backend/frontend running and fresh backend provider keys:
backend/.venv/bin/python infra/check_approval_live.py --provider groq
No secrets, prompts or provider response bodies are printed. All domain work is in a new synthetic workspace.
"""

import argparse
import json
import secrets
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.ai.providers import provider_key

p = argparse.ArgumentParser()
p.add_argument("--origin", default="http://localhost:3000")
p.add_argument("--provider", choices=["groq", "gemini"], default="groq")
a = p.parse_args()
if not provider_key(a.provider):
    print(
        json.dumps(
            {
                "mode": "live",
                "provider": a.provider,
                "status": "live checks skipped",
                "reason": "no_key",
            }
        )
    )
    raise SystemExit(0)
origin = a.origin.rstrip("/")
c = httpx.Client(base_url=origin, timeout=70)
try:
    csrf = c.get("/api/auth/csrf").json()["csrf_token"]
    c.headers.update({"X-CSRF-Token": csrf, "Origin": origin})

    def write(path, data, method="POST"):
        r = c.request(method, "/api" + path, json=data)
        r.raise_for_status()
        return r.json()

    write(
        "/auth/register",
        {
            "name": "Synthetic live approval",
            "email": f"live-{uuid.uuid4().hex}@example.com",
            "password": secrets.token_urlsafe(24),
        },
    )
    c.headers["X-CSRF-Token"] = c.cookies.get("tandem_csrf")
    wid = write("/workspaces", {"name": "Synthetic live proposal check"})["id"]
    config = c.get(f"/api/workspaces/{wid}/agent/settings").json()
    if any(v.get("status") == "fake_test_mode" for v in config["providers"].values()):
        raise SystemExit("Live check requires fake mode OFF in the running backend")
    write(f"/workspaces/{wid}/projects", {"name": "Synthetic project", "key": "SYN"})
    write(
        f"/workspaces/{wid}/agent/settings",
        {
            "enabled": True,
            "provider_chain": [a.provider],
            "monthly_run_limit": 10,
            "pause_at_limit": True,
        },
        "PUT",
    )
    cid = c.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    start = time.perf_counter()
    trigger = write(
        f"/workspaces/{wid}/channels/{cid}/messages",
        {
            "body": "@Agent plan JWT authentication as two tasks in this synthetic project. Only propose; do not execute.",
            "client_message_id": uuid.uuid4().hex,
        },
    )
    deadline = time.monotonic() + 70
    proposal = None
    run = None
    while time.monotonic() < deadline:
        runs = c.get(f"/api/workspaces/{wid}/agent/runs", params={"channel_id": cid}).json()
        run = next((r for r in runs if r["trigger_message_id"] == trigger["id"]), None)
        props = c.get(f"/api/workspaces/{wid}/proposals", params={"channel_id": cid}).json()[
            "proposals"
        ]
        proposal = next((r for r in props if r["trigger_message_id"] == trigger["id"]), None)
        if proposal or run and run["status"] in {"failed", "blocked"}:
            break
        time.sleep(0.3)
    if not proposal:
        print(
            json.dumps(
                {
                    "mode": "live",
                    "provider": a.provider,
                    "model": run.get("model") if run else None,
                    "status": "failed",
                    "category": run.get("error_category") if run else "timeout",
                }
            )
        )
        raise SystemExit(1)
    creation_ms = round((time.perf_counter() - start) * 1000, 2)
    assert c.get(f"/api/workspaces/{wid}/tasks").json()["total"] == 0
    start = time.perf_counter()
    result = write(
        f"/workspaces/{wid}/proposals/{proposal['id']}/approve",
        {
            "version": proposal["version"],
            "payload_hash": proposal["payload_hash"],
            "idempotency_key": uuid.uuid4().hex,
        },
    )
    print(
        json.dumps(
            {
                "mode": "live",
                "provider": a.provider,
                "model": run.get("model") if run else None,
                "status": result["status"],
                "proposal_creation_ms": creation_ms,
                "human_approval_http_ms": round((time.perf_counter() - start) * 1000, 2),
                "task_count": len((result.get("execution_result") or {}).get("task_ids", [])),
            }
        )
    )
    if result["status"] != "completed":
        raise SystemExit(1)
finally:
    try:
        c.post("/api/auth/logout")
    finally:
        c.close()
