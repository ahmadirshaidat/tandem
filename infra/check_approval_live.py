"""OPTIONAL synthetic live mention -> proposal -> human-test-owner approval.
Run with the normal backend/frontend running and fresh backend provider keys:
backend/.venv/bin/python infra/check_approval_live.py --provider groq --language ar --require-live
No secrets, prompts or provider response bodies are printed. All domain work is in a new synthetic workspace.
This checks the synthetic HTTP workflow, not the product owner's manual UI acceptance.
"""

import argparse
import json
import re
import secrets
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.ai.providers import provider_key


def checked(condition, message):
    if not condition:
        raise SystemExit(message)


p = argparse.ArgumentParser()
p.add_argument("--origin", default="http://localhost:3000")
p.add_argument("--provider", choices=["groq", "gemini"], default="groq")
p.add_argument("--language", choices=["en", "ar"], default="en")
p.add_argument("--require-live", action="store_true", help="Missing credentials exit 2, not 0")
a = p.parse_args()
if not provider_key(a.provider):
    print(
        json.dumps(
            {
                "mode": "live",
                "provider": a.provider,
                "language": a.language,
                "status": "live checks skipped",
                "reason": "no_key",
            }
        )
    )
    raise SystemExit(2 if a.require_live else 0)
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
            "body": (
                "@Agent خطط لتنفيذ المصادقة باستخدام JWT باقتراح مهمتين في هذا المشروع التجريبي. اكتب العناوين والأوصاف بالعربية. اقترح فقط ولا تنفذ أي تغيير؛ يجب أن يوافق إنسان أولاً."
                if a.language == "ar"
                else "@Agent plan JWT authentication as two tasks in this synthetic project. Only propose; do not execute. Use English titles and descriptions."
            ),
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
        if run and run["status"] in {"completed", "failed", "blocked"}:
            break
        time.sleep(0.3)
    if not proposal or not run or run["status"] != "completed":
        print(
            json.dumps(
                {
                    "mode": "live",
                    "provider": a.provider,
                    "language": a.language,
                    "model": run.get("model") if run else None,
                    "status": "failed",
                    "category": run.get("error_category") if run else "timeout",
                }
            )
        )
        raise SystemExit(1)
    if run["provider"] != a.provider or not run.get("model"):
        raise SystemExit("Live check did not use the selected provider")
    if proposal["kind"] != "create_tasks" or proposal["status"] != "proposed":
        raise SystemExit("Live check did not return an undecided task proposal")
    if a.language == "ar":
        if not all(
            re.search(r"[\u0621-\u064a]", item.get(field, ""))
            for item in proposal["payload"]["items"]
            for field in ["title", "description"]
        ):
            raise SystemExit("Arabic titles/descriptions were not returned")
    creation_ms = round((time.perf_counter() - start) * 1000, 2)
    checked(
        c.get(f"/api/workspaces/{wid}/tasks").json()["total"] == 0,
        "Unexpected task mutation before human test-owner approval",
    )
    start = time.perf_counter()
    proof = {
        "version": proposal["version"],
        "payload_hash": proposal["payload_hash"],
        "idempotency_key": uuid.uuid4().hex,
    }
    result = write(
        f"/workspaces/{wid}/proposals/{proposal['id']}/approve",
        proof,
    )
    approval_ms = round((time.perf_counter() - start) * 1000, 2)
    if result["status"] != "completed":
        raise SystemExit("Human test-owner approval did not complete")
    checked(result["payload_hash"] == proposal["payload_hash"], "Executed payload hash changed")
    ids = result["execution_result"]["task_ids"]
    checked(
        len(set(ids)) == len(proposal["payload"]["items"]) and ids,
        "Unexpected executed task count",
    )
    for tid, item in zip(ids, proposal["payload"]["items"], strict=True):
        task = c.get(f"/api/workspaces/{wid}/tasks/{tid}").json()
        checked(
            task["title"] == item["title"] and task["description"] == item["description"],
            "Executed task fields differ from the displayed proposal",
        )
        checked(task["created_by_agent"], "Agent task attribution missing")
    retry = write(f"/workspaces/{wid}/proposals/{proposal['id']}/approve", proof)
    checked(
        retry["execution_result"] == result["execution_result"], "Approval retry changed result"
    )
    checked(
        c.get(f"/api/workspaces/{wid}/tasks").json()["total"] == len(ids),
        "Approval retry duplicated task execution",
    )
    print(
        json.dumps(
            {
                "mode": "live",
                "provider": a.provider,
                "language": a.language,
                "model": run.get("model") if run else None,
                "status": result["status"],
                "proposal_creation_ms": creation_ms,
                "human_test_owner_approval_http_ms": approval_ms,
                "idempotent_retry": True,
                "task_count": len((result.get("execution_result") or {}).get("task_ids", [])),
            }
        )
    )
finally:
    try:
        c.post("/api/auth/logout")
    finally:
        c.close()
