"""Synthetic fake-provider proposal/approval timing across two users and real WS.
backend/.venv/bin/python infra/measure_proposals.py --origin http://localhost:3000
All created workspaces/accounts/tasks are synthetic. Created tasks are soft-deleted after each sample.
"""

import argparse
import json
import math
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
from websockets.sync.client import connect

p = argparse.ArgumentParser()
p.add_argument("--origin", default="http://localhost:3000")
p.add_argument("--samples", type=int, default=5)
a = p.parse_args()
if not 1 <= a.samples <= 5:
    raise SystemExit("Use 1–5 samples")
origin = a.origin.rstrip("/")


def write(c, path, data, method="POST"):
    r = c.request(method, "/api" + path, json=data)
    r.raise_for_status()
    return None if r.status_code == 204 else r.json()


def account(name):
    c = httpx.Client(base_url=origin, timeout=70)
    c.headers["X-CSRF-Token"] = c.get("/api/auth/csrf").json()["csrf_token"]
    email = f"proposal-perf-{uuid.uuid4().hex}@example.com"
    write(
        c,
        "/auth/register",
        {"name": name, "email": email, "password": secrets.token_urlsafe(24)},
    )
    c.headers["X-CSRF-Token"] = c.cookies.get("tandem_csrf")
    return c, email


def stats(values):
    return {
        "median": round(sorted(values)[max(0, math.ceil(len(values) * 0.5) - 1)], 2),
        "p95": round(sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)], 2),
    }


owner, _ = account("Synthetic approver")
viewer, email = account("Synthetic requester")
try:
    wid = write(owner, "/workspaces", {"name": "Synthetic proposal performance"})["id"]
    config = owner.get(f"/api/workspaces/{wid}/agent/settings").json()
    if config["providers"].get("groq", {}).get("status") != "fake_test_mode":
        raise SystemExit("This measurement requires explicit fake-provider mode")
    write(
        owner,
        f"/workspaces/{wid}/projects",
        {"name": "Synthetic project", "key": "SYN"},
    )
    invitation = write(owner, f"/workspaces/{wid}/invitations", {"email": email, "role": "viewer"})
    token = parse_qs(urlsplit(invitation["invite_url"]).query)["token"][0]
    write(viewer, f"/invitations/{token}/accept", {})
    write(
        owner,
        f"/workspaces/{wid}/agent/settings",
        {
            "enabled": True,
            "provider_chain": ["groq", "gemini"],
            "monthly_run_limit": 100,
            "pause_at_limit": True,
        },
        "PUT",
    )
    channel = owner.get(f"/api/workspaces/{wid}/channels").json()[0]
    cid = channel["id"]
    url = origin.replace("http://", "ws://").replace("https://", "wss://") + "/api/ws"
    creations, approvals = [], []
    with connect(
        url,
        origin=origin,
        additional_headers={"Cookie": "tandem_access=" + viewer.cookies.get("tandem_access")},
    ) as ws:
        ws.send(json.dumps({"type": "subscribe", "workspace_id": wid, "workspace_seq": 0}))
        ws.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "workspace_id": wid,
                    "channel_id": cid,
                    "last_seq": channel["last_seq"],
                }
            )
        )
        while json.loads(ws.recv(timeout=10))["type"] != "presence.update":
            pass
        for _ in range(a.samples):
            start = time.perf_counter()
            trigger = write(
                viewer,
                f"/workspaces/{wid}/channels/{cid}/messages",
                {
                    "body": "@Agent create a task for review",
                    "client_message_id": uuid.uuid4().hex,
                },
            )
            while True:
                e = json.loads(ws.recv(timeout=70))
                proposal = e.get("data", {}).get("proposal")
                if (
                    e["type"] == "proposal.created"
                    and proposal
                    and proposal["trigger_message_id"] == trigger["id"]
                ):
                    break
                if e["type"] == "agent.run_failed":
                    raise SystemExit("Synthetic run failed")
            creations.append((time.perf_counter() - start) * 1000)
            assert owner.get(f"/api/workspaces/{wid}/tasks").json()["total"] == 0
            start = time.perf_counter()
            result = write(
                owner,
                f"/workspaces/{wid}/proposals/{proposal['id']}/approve",
                {
                    "version": proposal["version"],
                    "payload_hash": proposal["payload_hash"],
                    "idempotency_key": uuid.uuid4().hex,
                },
            )
            assert result["status"] == "completed"
            ids = result["execution_result"]["task_ids"]
            while True:
                e = json.loads(ws.recv(timeout=10))
                if e["type"] == "task.created" and e["data"]["task"]["id"] in ids:
                    break
            approvals.append((time.perf_counter() - start) * 1000)
            for tid in ids:
                task = owner.get(f"/api/workspaces/{wid}/tasks/{tid}").json()
                write(
                    owner,
                    f"/workspaces/{wid}/tasks/{tid}",
                    {"version": task["version"]},
                    "DELETE",
                )
    print(
        json.dumps(
            {
                "mode": "deterministic_fake_provider",
                "samples": a.samples,
                "mention_to_proposal_ms": stats(creations),
                "approval_to_second_user_task_event_ms": stats(approvals),
            },
            indent=2,
        )
    )
finally:
    owner.post("/api/auth/logout")
    viewer.post("/api/auth/logout")
    owner.close()
    viewer.close()
