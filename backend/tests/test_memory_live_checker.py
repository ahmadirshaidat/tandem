"""Acceptance guards only; mocked HTTP is not real-model acceptance evidence."""

import json
import runpy
import sys
from pathlib import Path

import httpx
import pytest

from app.ai import providers


def test_semantic_live_check_rejects_full_text_hits_without_vectors(monkeypatch, capsys):
    calls = []

    def response(value):
        return httpx.Response(200, json=value, request=httpx.Request("GET", "http://test.local"))

    class Client:
        def __init__(self, **kwargs):
            self.headers = {}
            self.cookies = {"tandem_csrf": "synthetic-only"}
            self.tasks = 0

        def get(self, path, params=None):
            calls.append(path)
            if path == "/api/auth/csrf":
                return response({"csrf_token": "synthetic-only"})
            if path.endswith("/memory/settings"):
                return response({"degraded": False, "model": "synthetic-only", "version": "1"})
            if path.endswith("/channels"):
                return response([{"id": "channel"}])
            if path.endswith("/search"):
                # Hybrid can succeed entirely from FTS despite an empty vector index.
                return response(
                    {
                        "degraded": False,
                        "items": []
                        if params.get("mode") == "vector"
                        else [{"source_id": "past"}, {"source_id": "target"}],
                    }
                )
            raise AssertionError("Agent admission must follow verified vector retrieval")

        def request(self, method, path, json):
            calls.append(path)
            if path.endswith("/register"):
                return response({})
            if path == "/api/workspaces":
                return response({"id": "workspace"})
            if path.endswith("/projects"):
                return response({"id": "project"})
            if path.endswith("/tasks"):
                self.tasks += 1
                return response({"id": "past" if self.tasks == 1 else "target"})
            raise AssertionError("No generation may be requested with missing task vectors")

        def post(self, path):
            return response({})

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(providers, "provider_key", lambda name: "synthetic-only")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_memory_live.py",
            "--language",
            "en",
            "--tool",
            "analyze_bug",
            "--require-live",
            "--require-embeddings",
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(__file__).resolve().parents[2] / "infra/check_memory_live.py"))
    assert stopped.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["category"] == "vector_index_incomplete"
    assert result["vector_index_verified"] is False
    assert not any(path.endswith(("/messages", "/agent/settings")) for path in calls)
