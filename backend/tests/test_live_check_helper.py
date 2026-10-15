"""Hermetic tests of the live-check harness; these are NOT real-provider evidence."""

import json
import runpy
import sys
from pathlib import Path

import httpx
import pytest

from app.ai import providers

SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "check_approval_live.py"


def run_helper(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *args])
    return runpy.run_path(str(SCRIPT), run_name="__main__")


@pytest.mark.parametrize("strict,code", [(False, 0), (True, 2)])
def test_missing_key_is_skipped_and_strict_mode_cannot_pass(monkeypatch, capsys, strict, code):
    monkeypatch.setattr(providers, "provider_key", lambda name: None)

    def no_network(*args, **kwargs):
        pytest.fail("Missing credentials must not make network requests")

    monkeypatch.setattr(httpx, "Client", no_network)
    with pytest.raises(SystemExit) as error:
        run_helper(monkeypatch, "--language", "ar", *(["--require-live"] if strict else []))
    assert error.value.code == code
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "mode": "live",
        "provider": "groq",
        "language": "ar",
        "status": "live checks skipped",
        "reason": "no_key",
    }


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "fake",
        "failed_run",
        "wrong_provider",
        "english",
        "unapproved_task",
        "tampered_hash",
        "duplicate_execution",
    ],
)
def test_arabic_protocol_approval_and_failure_boundaries(monkeypatch, capsys, scenario):
    original_client = httpx.Client
    monkeypatch.setattr(providers, "provider_key", lambda name: "synthetic-placeholder")
    proofs, questions = [], []
    polls = 0
    title = "JWT backend" if scenario == "english" else "تنفيذ المصادقة JWT"
    item = {"item_id": "backend", "title": title, "description": "وصف تجريبي للمهمة"}
    proposal = {
        "id": "proposal",
        "trigger_message_id": "trigger",
        "kind": "create_tasks",
        "status": "proposed",
        "version": 1,
        "payload_hash": "a" * 64,
        "payload": {"items": [item]},
    }

    def handle(req):
        nonlocal polls
        path = req.url.path
        data = json.loads(req.content) if req.content else {}
        if path.endswith("/auth/csrf"):
            return httpx.Response(
                200,
                json={"csrf_token": "synthetic-csrf"},
                headers={"Set-Cookie": "tandem_csrf=synthetic-csrf; Path=/"},
            )
        if path.endswith(("/auth/register", "/auth/logout")):
            return httpx.Response(200, json={})
        if path == "/api/workspaces":
            return httpx.Response(201, json={"id": "workspace"})
        if path.endswith("/agent/settings"):
            return httpx.Response(
                200,
                json={
                    "providers": {
                        "groq": {"status": "fake_test_mode" if scenario == "fake" else "available"}
                    }
                },
            )
        if path.endswith("/projects"):
            return httpx.Response(201, json={"id": "project"})
        if path.endswith("/channels"):
            return httpx.Response(200, json=[{"id": "channel"}])
        if path.endswith("/messages"):
            questions.append(data["body"])
            return httpx.Response(201, json={"id": "trigger"})
        if path.endswith("/agent/runs"):
            polls += 1
            return httpx.Response(
                200,
                json=[
                    {
                        "trigger_message_id": "trigger",
                        "status": "failed"
                        if scenario == "failed_run"
                        else "running"
                        if polls == 1
                        else "completed",
                        "provider": "gemini" if scenario == "wrong_provider" else "groq",
                        "model": "synthetic-test-model",
                        "error_category": "invalid_response" if scenario == "failed_run" else None,
                    }
                ],
            )
        if path.endswith("/proposals"):
            return httpx.Response(200, json={"proposals": [proposal]})
        if path.endswith("/approve"):
            assert polls >= 2, "Do not approve while the provider is still running"
            assert req.headers["X-CSRF-Token"] == "synthetic-csrf"
            proofs.append(data)
            return httpx.Response(
                200,
                json={
                    **proposal,
                    "payload_hash": "b" * 64
                    if scenario == "tampered_hash"
                    else proposal["payload_hash"],
                    "status": "completed",
                    "execution_result": {"task_ids": ["task"]},
                },
            )
        if path.endswith("/tasks/task"):
            return httpx.Response(200, json={**item, "created_by_agent": True})
        if path.endswith("/tasks"):
            total = (
                (2 if scenario == "duplicate_execution" and len(proofs) == 2 else 1)
                if proofs
                else (1 if scenario == "unapproved_task" else 0)
            )
            return httpx.Response(200, json={"total": total})
        pytest.fail("Unexpected request")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(handle)),
    )
    if scenario != "success":
        with pytest.raises(SystemExit):
            run_helper(monkeypatch, "--language", "ar", "--require-live")
        assert len(proofs) == {"tampered_hash": 1, "duplicate_execution": 2}.get(scenario, 0)
    else:
        run_helper(monkeypatch, "--language", "ar", "--require-live")
        assert len(proofs) == 2 and proofs[0] == proofs[1]
        assert proofs[0]["version"] == proposal["version"]
        assert proofs[0]["payload_hash"] == proposal["payload_hash"]
        assert proofs[0]["idempotency_key"]
        assert "اكتب العناوين والأوصاف بالعربية" in questions[0]
        output = capsys.readouterr().out
        assert title not in output and item["description"] not in output
        assert "synthetic-placeholder" not in output
        assert json.loads(output)["idempotent_retry"] is True
