from pydantic import SecretStr

from app.ai import providers
from app.ai.router import trial_limiter
from app.core.config import settings


def test_workspace_switch_cannot_reset_user_trial_budget(client_factory, monkeypatch):
    client, _ = client_factory("limit-owner@example.com")
    first = client.post("/api/workspaces", json={"name": "First"}).json()["id"]
    second = client.post("/api/workspaces", json={"name": "Second"}).json()["id"]
    trial_limiter.hits.clear()
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("synthetic-test-key"))
    monkeypatch.setattr(settings, "ai_requests_per_minute", 1)
    monkeypatch.setattr(
        providers, "complete", lambda name, prompt: providers.Completion("Test answer")
    )
    assert (
        client.post(
            f"/api/workspaces/{first}/ai/trials", json={"provider": "groq", "prompt": "Test"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/workspaces/{second}/ai/trials", json={"provider": "groq", "prompt": "Test"}
        ).status_code
        == 429
    )
    trial_limiter.hits.clear()
