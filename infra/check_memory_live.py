"""Bounded real Slice 6 agent checks in isolated synthetic workspaces.

Prints metadata only: never prompts, answers, provider bodies or credentials.
backend/.venv/bin/python infra/check_memory_live.py --language en --tool analyze_bug --require-live
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.ai.providers import provider_key

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--language", choices=["en", "ar"], required=True)
parser.add_argument("--tool", choices=["analyze_bug", "find_similar_bugs"], required=True)
parser.add_argument("--origin", default="http://localhost:3000")
parser.add_argument("--require-live", action="store_true")
parser.add_argument(
    "--require-embeddings",
    action="store_true",
    help="Reject degraded retrieval before any paid generation",
)
parser.add_argument("--embedding-model", help="Require this exact local embedding model ID")
args = parser.parse_args()
metadata = {
    "mode": "live",
    "provider": "groq",
    "language": args.language,
    "requested_tool": args.tool,
}
if not provider_key("groq"):
    print(json.dumps({**metadata, "status": "live checks skipped", "category": "no_key"}))
    raise SystemExit(2 if args.require_live else 0)
origin = args.origin.rstrip("/")
client = httpx.Client(base_url=origin, timeout=75)
code = 1
try:
    response = client.get("/api/auth/csrf")
    response.raise_for_status()
    client.headers.update({"X-CSRF-Token": response.json()["csrf_token"], "Origin": origin})

    def write(path, data, method="POST"):
        response = client.request(method, "/api" + path, json=data)
        response.raise_for_status()
        return response.json()

    write(
        "/auth/register",
        {
            "name": "Synthetic live memory owner",
            "email": f"memory-{uuid.uuid4().hex}@example.com",
            "password": uuid.uuid4().hex + "!Synthetic",
        },
    )
    client.headers["X-CSRF-Token"] = client.cookies.get("tandem_csrf", "")
    wid = write("/workspaces", {"name": "Synthetic live memory check"})["id"]
    embedding = client.get(f"/api/workspaces/{wid}/memory/settings")
    embedding.raise_for_status()
    embedding = embedding.json()
    metadata.update(
        embedding_model=embedding.get("model"),
        embedding_version=embedding.get("version"),
        embeddings_required=bool(args.require_embeddings or args.embedding_model),
    )
    if metadata["embeddings_required"] and embedding["degraded"]:
        raise ValueError("embedding_unavailable")
    if args.embedding_model and embedding.get("model") != args.embedding_model:
        raise ValueError("embedding_model_mismatch")
    project = write(f"/workspaces/{wid}/projects", {"name": "Synthetic retrieval", "key": "LIVE"})
    title = (
        "فشل تجديد JWT بعد إلغاء الجلسة"
        if args.language == "ar"
        else "JWT refresh retry loop after token revocation"
    )
    description = (
        "يدور تجديد JWT في حلقة بعد إلغاء رمز الجلسة. نحتاج تحليل الأدلة فقط."
        if args.language == "ar"
        else "JWT refresh keeps retrying after the session token is revoked. Investigate evidence only."
    )
    past = write(
        f"/workspaces/{wid}/tasks",
        {
            "project_id": project["id"],
            "title": (
                "حل سابق لمشكلة JWT"
                if args.language == "ar"
                else "Previous JWT revoked-token retry fix"
            ),
            "description": (
                "تم حل تكرار JWT بإيقاف المحاولات بعد رفض الرمز وطلب تسجيل دخول جديد."
                if args.language == "ar"
                else "The earlier JWT incident stopped retrying revoked tokens and requested a new sign-in."
            ),
            "type": "bug",
            "status": "done",
        },
    )
    target = write(
        f"/workspaces/{wid}/tasks",
        {"project_id": project["id"], "title": title, "description": description, "type": "bug"},
    )
    cid = client.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    await_index = time.monotonic() + 40
    while True:
        indexed = client.get(
            f"/api/workspaces/{wid}/search", params={"query": "JWT", "mode": "full_text"}
        )
        indexed.raise_for_status()
        result = indexed.json()
        if {target["id"], past["id"]}.issubset({i["source_id"] for i in result["items"]}):
            break
        if time.monotonic() > await_index:
            raise ValueError("index_timeout")
        time.sleep(0.5)
    if metadata["embeddings_required"] and result["degraded"]:
        raise ValueError("embedding_unavailable")
    config = client.get(f"/api/workspaces/{wid}/agent/settings").json()
    if config["providers"]["groq"]["status"] == "fake_test_mode":
        raise ValueError("fake_mode_rejected")
    write(
        f"/workspaces/{wid}/agent/settings",
        {
            "enabled": True,
            "provider_chain": ["groq"],
            "monthly_run_limit": 10,
            "pause_at_limit": True,
        },
        "PUT",
    )
    question = (
        (
            f"@Agent استخدم الأداة {args.tool} "
            + (
                f"لتحليل العطل ذي task_id {target['id']}."
                if args.tool == "analyze_bug"
                else "للبحث عن أعطال مشابهة لمشكلة JWT وتجديد الرمز بعد الإلغاء."
            )
            + " اكتب تحليلا بالعربية وسم الأسباب المحتملة كفرضيات مع المصادر. لا تقترح ولا تنفذ أي تغييرات."
        )
        if args.language == "ar"
        else (
            f"@Agent use the {args.tool} tool "
            + (
                f"for task_id {target['id']}."
                if args.tool == "analyze_bug"
                else "to find similar JWT revoked-token refresh failures."
            )
            + " Explain evidence and label inferred causes as hypotheses with sources. Do not propose or execute changes."
        )
    )
    start = time.perf_counter()
    trigger = write(
        f"/workspaces/{wid}/channels/{cid}/messages",
        {"body": question, "client_message_id": uuid.uuid4().hex},
    )
    deadline = time.monotonic() + 75
    run = None
    while time.monotonic() < deadline:
        runs = client.get(f"/api/workspaces/{wid}/agent/runs", params={"channel_id": cid}).json()
        run = next((r for r in runs if r["trigger_message_id"] == trigger["id"]), None)
        if run and run["status"] in {"completed", "failed", "blocked"}:
            break
        time.sleep(0.4)
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    tools = [s["name"] for s in (run or {}).get("steps", []) if s["status"] == "ok"]
    sources = (
        client.get(f"/api/workspaces/{wid}/agent/runs/{run['id']}/memory-sources")
        .json()
        .get("sources", [])
        if run
        else []
    )
    audit = (
        client.get(
            f"/api/workspaces/{wid}/audit", params={"action": "agent.run_" + run["status"]}
        ).json()
        if run
        else {}
    )
    event = (
        next((e for e in audit.get("events", []) if e["target_id"] == run["id"]), None)
        if run
        else None
    )
    usage = event["redacted_arguments"] if event else {}
    tasks = client.get(f"/api/workspaces/{wid}/tasks").json()
    proposals = client.get(f"/api/workspaces/{wid}/proposals").json()["proposals"]
    passed = bool(
        run
        and run["status"] == "completed"
        and args.tool in tools
        and sources
        and tasks["total"] == 2
        and not proposals
    )
    category = (
        None if passed else (run or {}).get("error_category") or "required_tool_or_sources_missing"
    )
    print(
        json.dumps(
            {
                **metadata,
                "status": "passed" if passed else "failed",
                "category": category,
                "model": (run or {}).get("model"),
                "agent_latency_ms": (run or {}).get("latency_ms"),
                "wall_ms": elapsed,
                "successful_tools": tools,
                "authorized_source_chips": len(sources),
                "task_count_unchanged": tasks["total"] == 2,
                "proposals_created": len(proposals),
                "embedding_degraded": result["degraded"],
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "token_usage_scope": "successful generations; failed HTTP attempt usage not reported",
            }
        )
    )
    code = 0 if passed else 1
except httpx.HTTPStatusError as error:
    print(
        json.dumps(
            {
                **metadata,
                "status": "failed",
                "category": "http_error",
                "http_status": error.response.status_code,
            }
        )
    )
except Exception as error:
    category = (
        str(error)
        if isinstance(error, ValueError)
        and str(error)
        in {
            "index_timeout",
            "fake_mode_rejected",
            "embedding_unavailable",
            "embedding_model_mismatch",
        }
        else "check_failed"
    )
    print(json.dumps({**metadata, "status": "failed", "category": category}))
finally:
    try:
        client.post("/api/auth/logout")
    except httpx.HTTPError:
        pass
    client.close()
raise SystemExit(code)
