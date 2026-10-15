"""Synthetic two-user mention -> step and answer latency. No message content printed.
Run: backend/.venv/bin/python infra/measure_agent.py --origin http://localhost:3000
Requires explicit fake provider mode; --live permits real Groq/Gemini calls if configured.
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
p.add_argument("--live", action="store_true")
a = p.parse_args()
if not 1 <= a.samples <= 5:
    raise SystemExit("Use 1–5 samples to respect the default per-user rate limit")
origin = a.origin.rstrip("/")


def account(name):
    c = httpx.Client(base_url=origin, timeout=70)
    token = c.get("/api/auth/csrf").json()["csrf_token"]
    c.headers.update({"X-CSRF-Token": token, "Origin": origin})
    email = f"agent-perf-{uuid.uuid4().hex}@example.com"
    r = c.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": secrets.token_urlsafe(24)},
    )
    r.raise_for_status()
    c.headers["X-CSRF-Token"] = c.cookies.get("tandem_csrf")
    return c, email


def write(c, path, data, method="POST"):
    r = c.request(method, "/api" + path, json=data)
    r.raise_for_status()
    return r.json()


def percentile(values, quantile):
    return round(sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)], 2)


owner, _ = account("Agent performance owner")
viewer, email = account("Agent performance viewer")
try:
    wid = write(owner, "/workspaces", {"name": "Synthetic agent performance"})["id"]
    config = owner.get(f"/api/workspaces/{wid}/agent/settings").json()
    fake = config["providers"].get("groq", {}).get("status") == "fake_test_mode"
    if not fake and not a.live:
        raise SystemExit(
            "Enable AGENT_FAKE_PROVIDER explicitly, or use --live for synthetic real-provider measurements"
        )
    if not fake and not any(
        config["providers"].get(p, {}).get("status") == "available"
        for p in ["groq", "gemini"]
    ):
        print(json.dumps({"mode": "live", "status": "skipped_no_available_provider"}))
        raise SystemExit(0)
    write(
        owner,
        f"/workspaces/{wid}/agent/settings",
        {
            "enabled": True,
            "provider_chain": ["groq", "gemini"],
            "monthly_run_limit": 1000,
            "pause_at_limit": True,
        },
        "PUT",
    )
    invitation = write(
        owner, f"/workspaces/{wid}/invitations", {"email": email, "role": "viewer"}
    )
    token = parse_qs(urlsplit(invitation["invite_url"]).query)["token"][0]
    write(viewer, f"/invitations/{token}/accept", {})
    channel = owner.get(f"/api/workspaces/{wid}/channels").json()[0]
    cid = channel["id"]
    url = origin.replace("http://", "ws://").replace("https://", "wss://") + "/api/ws"
    first, final = [], []
    with connect(
        url,
        origin=origin,
        additional_headers={
            "Cookie": "tandem_access=" + owner.cookies.get("tandem_access")
        },
    ) as ws:
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
            m = write(
                viewer,
                f"/workspaces/{wid}/channels/{cid}/messages",
                {
                    "body": "@Agent summarize this synthetic channel",
                    "client_message_id": uuid.uuid4().hex,
                },
            )
            saw_step = False
            while True:
                e = json.loads(ws.recv(timeout=70))
                run = e.get("data", {}).get("run")
                if not run or run["trigger_message_id"] != m["id"]:
                    continue
                latency = (time.perf_counter() - start) * 1000
                if e["type"] == "agent.step" and not saw_step:
                    first.append(latency)
                    saw_step = True
                if e["type"] == "agent.run_failed":
                    raise SystemExit("Agent failed: " + str(run["error_category"]))
                if e["type"] == "agent.message_created":
                    if not saw_step:
                        raise SystemExit("No agent.step executed; measurement invalid")
                    final.append(latency)
                    break
    print(
        json.dumps(
            {
                "mode": "deterministic_fake_orchestration" if fake else "live_provider",
                "samples": a.samples,
                "first_step_ms": {
                    "median": percentile(first, 0.5),
                    "p95": percentile(first, 0.95),
                },
                "final_message_ms": {
                    "median": percentile(final, 0.5),
                    "p95": percentile(final, 0.95),
                },
            },
            indent=2,
        )
    )
finally:
    owner.post("/api/auth/logout")
    viewer.post("/api/auth/logout")
    owner.close()
    viewer.close()
