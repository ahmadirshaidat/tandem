"""Bounded synthetic real Suggestion approval; safe metadata only, never bodies or keys."""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai.providers import provider_key  # noqa: E402
from app.documents.service import transform  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--language", choices=["en", "ar"], required=True)
parser.add_argument("--origin", default="http://localhost:3000")
parser.add_argument("--require-live", action="store_true")
a = parser.parse_args()
meta = {"mode": "live", "provider": "groq", "language": a.language, "status": "failed"}
if not provider_key("groq"):
    print(json.dumps({**meta, "status": "skipped", "category": "no_key"}))
    raise SystemExit(2 if a.require_live else 0)
code = 1
with httpx.Client(base_url=a.origin, timeout=80, headers={"Origin": a.origin}) as c:
    try:

        def write(path, data, method="POST"):
            token = c.get("/api/auth/csrf")
            token.raise_for_status()
            r = c.request(
                method,
                "/api" + path,
                json=data,
                headers={"X-CSRF-Token": token.json()["csrf_token"]},
            )
            r.raise_for_status()
            return r.json()

        write(
            "/auth/register",
            {
                "name": "Synthetic document live owner",
                "email": f"doc-live-{uuid.uuid4().hex}@example.com",
                "password": uuid.uuid4().hex + "!",
            },
        )
        w = write("/workspaces", {"name": "Synthetic document live acceptance"})
        base = "/workspaces/" + w["id"]
        p = write(base + "/projects", {"name": "Synthetic docs", "key": "LIVE"})
        d = write(
            base + "/documents",
            {
                "project_id": p["id"],
                "title": "Synthetic live specification",
                "type": "spec",
            },
        )
        path = base + "/documents/" + d["id"]
        old = "Describe the problem." if a.language == "en" else "يجب توضيح المشكلة."
        replacement = (
            "Describe the problem and acceptance criteria clearly."
            if a.language == "en"
            else "يجب توضيح المشكلة ومعايير القبول بوضوح."
        )
        if a.language == "ar":
            value = transform(action="template", text="# مواصفات الاختبار\n" + old)
            write(path + "/sync", {"update": value["state"]})
        cid = c.get("/api" + base + "/channels").json()[0]["id"]
        config = c.get("/api" + base + "/agent/settings").json()
        if config["providers"]["groq"]["status"] == "fake_test_mode":
            raise ValueError("fake_mode_rejected")
        write(
            base + "/agent/settings",
            {
                "enabled": True,
                "provider_chain": ["groq"],
                "monthly_run_limit": 10,
                "pause_at_limit": True,
            },
            "PUT",
        )
        question = (
            f"اقرأ المستند بالأداة get_document ثم اقترح suggest_edit واحدا فقط. استبدل النص الدقيق «{old}» بالنص الدقيق «{replacement}». السبب: توضيح المتطلبات. لا تطبق أي تعديل."
            if a.language == "ar"
            else f'Read using get_document, then propose exactly one suggest_edit replacing the exact text "{old}" with exactly "{replacement}". Reason: clarify requirements. Do not apply edits.'
        )
        before = c.get("/api" + path).json()["text"]
        start = time.perf_counter()
        trigger = write(path + "/ask", {"channel_id": cid, "question": question})
        run = None
        for _ in range(160):
            runs = c.get(
                "/api" + base + "/agent/runs", params={"channel_id": cid}
            ).json()
            run = next(
                (r for r in runs if r["trigger_message_id"] == trigger["message_id"]),
                None,
            )
            if run and run["status"] in {"completed", "failed", "blocked"}:
                break
            time.sleep(0.5)
        meta.update(
            model=(run or {}).get("model"),
            agent_status=(run or {}).get("status"),
            agent_latency_ms=(run or {}).get("latency_ms"),
            wall_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        if not run or run["status"] != "completed":
            raise ValueError((run or {}).get("error_category") or "run_not_completed")
        proposals = c.get("/api" + path + "/suggestions").json()["suggestions"]
        proposal = next(
            (
                p
                for p in proposals
                if p["kind"] == "suggest_edit" and p["status"] == "proposed"
            ),
            None,
        )
        unchanged = c.get("/api" + path).json()["text"] == before
        meta["unchanged_before_approval"] = unchanged
        if not proposal or not unchanged:
            raise ValueError("proposal_preconditions_failed")
        if (
            proposal["payload"]["expected_text"] != old
            or proposal["payload"]["replacement"] != replacement
        ):
            raise ValueError("reviewed_payload_mismatch")
        decision = {
            "version": proposal["version"],
            "payload_hash": proposal["payload_hash"],
            "idempotency_key": uuid.uuid4().hex,
        }
        approved = write(base + "/proposals/" + proposal["id"] + "/approve", decision)
        after = c.get("/api" + path).json()["text"]
        repeat = write(base + "/proposals/" + proposal["id"] + "/approve", decision)
        versions = c.get("/api" + path + "/versions").json()["versions"]
        good = (
            approved["status"] == "completed"
            and replacement in after
            and c.get("/api" + path).json()["text"] == after
            and repeat["id"] == approved["id"]
            and any(
                v["proposal_id"] == proposal["id"]
                and v["actor_type"] == "agent_approved"
                for v in versions
            )
        )
        meta.update(
            status="passed" if good else "failed",
            proposal_status=approved["status"],
            double_accept_applied_once=True,
            agent_approved_version=any(
                v["proposal_id"] == proposal["id"] for v in versions
            ),
        )
        if good:
            code = 0
    except httpx.HTTPStatusError as e:
        meta.update(category="http_error", http_status=e.response.status_code)
    except ValueError as e:
        meta["category"] = (
            str(e)
            if str(e)
            in {
                "fake_mode_rejected",
                "rate_limited",
                "run_not_completed",
                "proposal_preconditions_failed",
                "reviewed_payload_mismatch",
                "invalid_response",
                "tool_use_failed",
                "json_validate_failed",
                "unavailable",
            }
            else "check_failed"
        )
    except Exception:
        meta["category"] = "check_failed"
    finally:
        try:
            write("/auth/logout", {})
        except Exception:
            pass
print(json.dumps(meta))
raise SystemExit(code)
