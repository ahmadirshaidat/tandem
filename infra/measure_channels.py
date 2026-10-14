"""Measure real HTTP-send -> second WebSocket delivery and newest history loads.

Run with backend/.venv/bin/python infra/measure_channels.py --origin http://localhost:3000.
Creates synthetic accounts/workspace in the configured development database; no LLM calls.
"""

import argparse
import json
import math
import secrets
import threading
import time
import uuid
from queue import Queue

import httpx
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

parser = argparse.ArgumentParser()
parser.add_argument("--origin", default="http://localhost:3000")
parser.add_argument("--samples", type=int, default=30)
parser.add_argument("--history-requests", type=int, default=20)
args = parser.parse_args()
if not 1 <= args.samples <= 50 or not 1 <= args.history_requests <= 100:
    raise SystemExit("Use 1–50 sends and 1–100 history loads")
origin = args.origin.rstrip("/")


def create(name):
    client = httpx.Client(base_url=origin, timeout=10)
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    client.headers.update({"X-CSRF-Token": token, "Origin": origin})
    email = f"latency-{uuid.uuid4().hex}@example.com"
    result = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": secrets.token_urlsafe(24)},
    )
    result.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies.get("tandem_csrf")
    return client, email


def post(client, path, body):
    result = client.post("/api" + path, json=body)
    result.raise_for_status()
    return result.json()


def percentile(values, p):
    return round(sorted(values)[max(0, math.ceil(len(values) * p) - 1)], 2)


a, _ = create("Latency A")
b, email = create("Latency B")
try:
    workspace = post(a, "/workspaces", {"name": "Synthetic latency check"})
    wid = workspace["id"]
    invitation = post(
        a, f"/workspaces/{wid}/invitations", {"email": email, "role": "viewer"}
    )
    from urllib.parse import parse_qs, urlsplit

    token = parse_qs(urlsplit(invitation["invite_url"]).query)["token"][0]
    post(b, f"/invitations/{token}/accept", {})
    channel = a.get(f"/api/workspaces/{wid}/channels").json()[0]
    cid = channel["id"]
    url = origin.replace("http://", "ws://").replace("https://", "wss://") + "/api/ws"
    deliveries = Queue()
    with (
        connect(
            url,
            origin=origin,
            additional_headers={
                "Cookie": "tandem_access=" + a.cookies.get("tandem_access")
            },
        ) as wa,
        connect(
            url,
            origin=origin,
            additional_headers={
                "Cookie": "tandem_access=" + b.cookies.get("tandem_access")
            },
        ) as wb,
    ):
        subscription = {
            "type": "subscribe",
            "workspace_id": wid,
            "channel_id": cid,
            "last_seq": channel["last_seq"],
        }
        wa.send(json.dumps(subscription))
        wb.send(json.dumps(subscription))
        # Presence is an authorization/subscription readiness barrier.
        while json.loads(wb.recv(timeout=10))["type"] != "presence.update":
            pass

        def receive():
            try:
                for frame in wb:
                    event = json.loads(frame)
                    if event["type"] == "message.created":
                        deliveries.put(
                            (
                                event["data"]["message"]["client_message_id"],
                                time.perf_counter(),
                            )
                        )
            except ConnectionClosed:
                deliveries.put(("disconnected", time.perf_counter()))

        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        values = []
        for number in range(args.samples):
            client_id = uuid.uuid4().hex
            started = time.perf_counter()
            post(
                a,
                f"/workspaces/{wid}/channels/{cid}/messages",
                {
                    "body": f"Synthetic measurement {number}",
                    "client_message_id": client_id,
                },
            )
            received_id, received_at = deliveries.get(timeout=10)
            assert received_id == client_id, "Out-of-order delivery"
            values.append((received_at - started) * 1000)
        wb.close()
        reader.join(timeout=5)
    histories = []
    for _ in range(args.history_requests):
        started = time.perf_counter()
        result = b.get(f"/api/workspaces/{wid}/channels/{cid}/messages")
        result.raise_for_status()
        assert len(result.json()["messages"]) == args.samples
        histories.append((time.perf_counter() - started) * 1000)
    print(
        json.dumps(
            {
                "origin": origin,
                "delivery_samples": len(values),
                "delivery_p50_ms": percentile(values, 0.5),
                "delivery_p95_ms": percentile(values, 0.95),
                "delivery_max_ms": round(max(values), 2),
                "history_samples": len(histories),
                "history_message_count": args.samples,
                "history_p50_ms": percentile(histories, 0.5),
                "history_p95_ms": percentile(histories, 0.95),
                "target_delivery_p95_ms": 300,
                "target_met": percentile(values, 0.95) < 300,
            },
            indent=2,
        )
    )
finally:
    for client in (a, b):
        client.post("/api/auth/logout")
        client.close()
