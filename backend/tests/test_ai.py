import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.ai import providers
from app.ai.router import trial_limiter
from app.core.config import settings
from app.core.models import AITrial, Membership


@pytest.fixture(autouse=True)
def private_test_keys(monkeypatch):
    # Never use development or user-supplied credentials in automated tests.
    for name in ("groq_api_key", "gemini_api_key", "deepseek_api_key", "tandem_openai_api_key"):
        monkeypatch.setattr(settings, name, None)
    monkeypatch.setattr(settings, "ai_primary_provider", "groq")
    trial_limiter.hits.clear()


def setup_workspace(client_factory):
    client, user = client_factory("ai-owner@example.com")
    workspace = client.post("/api/workspaces", json={"name": "AI tests"}).json()
    return client, user, workspace["id"]


def test_provider_status_never_returns_keys(client_factory, monkeypatch):
    client, _, wid = setup_workspace(client_factory)
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("synthetic-test-key"))
    response = client.get(f"/api/workspaces/{wid}/ai/providers")
    assert response.status_code == 200
    assert "synthetic-test-key" not in response.text
    assert response.json()["providers"][0]["configured"] is True
    assert response.json()["providers"][-1]["configured"] is False


def test_auto_fallback_and_redacted_history(client_factory, monkeypatch, db):
    client, _, wid = setup_workspace(client_factory)
    for name in ("groq_api_key", "gemini_api_key"):
        monkeypatch.setattr(settings, name, SecretStr("synthetic-test-key"))
    calls = []

    def complete(provider, prompt):
        calls.append(provider)
        if provider == "groq":
            raise providers.ProviderFailure("rate_limited", 429)
        return providers.Completion("A useful test answer", 10, 8)

    monkeypatch.setattr(providers, "complete", complete)
    response = client.post(
        f"/api/workspaces/{wid}/ai/trials",
        json={"provider": "auto", "prompt": "private test question"},
    )
    assert response.status_code == 200
    assert calls == ["groq", "gemini"]
    assert response.json()["provider"] == "gemini"
    assert response.json()["answer"] == "A useful test answer"
    history = client.get(f"/api/workspaces/{wid}/ai/trials")
    assert history.json()[0]["attempts"][0]["category"] == "rate_limited"
    assert "private test question" not in history.text
    assert "A useful test answer" not in history.text
    assert "synthetic-test-key" not in history.text
    record = db.scalar(select(AITrial))
    assert record.input_length == len("private test question")
    assert not hasattr(record, "prompt") and not hasattr(record, "answer")


def test_manual_provider_never_silently_falls_back(client_factory, monkeypatch):
    client, _, wid = setup_workspace(client_factory)
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("synthetic-test-key"))
    calls = []

    def fail(name, prompt):
        calls.append(name)
        raise providers.ProviderFailure("unavailable")

    monkeypatch.setattr(providers, "complete", fail)
    response = client.post(
        f"/api/workspaces/{wid}/ai/trials", json={"provider": "deepseek", "prompt": "test"}
    )
    assert response.status_code == 503
    assert calls == ["deepseek"]
    assert client.get(f"/api/workspaces/{wid}/ai/trials").json()[0]["status"] == "failed"


def test_missing_keys_and_invalid_input_do_not_call_provider(client_factory, monkeypatch):
    client, _, wid = setup_workspace(client_factory)

    def forbidden(*args):
        raise AssertionError("External API must not be called")

    monkeypatch.setattr(providers, "complete", forbidden)
    assert (
        client.post(f"/api/workspaces/{wid}/ai/trials", json={"prompt": "test"}).status_code == 503
    )
    for data in (
        {"prompt": " "},
        {"prompt": "x" * 4001},
        {"prompt": "test", "provider": "http://evil.example"},
    ):
        assert client.post(f"/api/workspaces/{wid}/ai/trials", json=data).status_code == 422


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_trial_admin_permissions(client_factory, db, role):
    owner, _, wid = setup_workspace(client_factory)
    user_client, user = client_factory("teammate@example.com")
    db.add(Membership(workspace_id=wid, user_id=user["id"], role=role))
    db.commit()
    for path in ("providers", "trials"):
        assert user_client.get(f"/api/workspaces/{wid}/ai/{path}").status_code == 403
    assert (
        user_client.post(f"/api/workspaces/{wid}/ai/trials", json={"prompt": "test"}).status_code
        == 403
    )


def test_all_ai_endpoints_enforce_workspace_isolation(client_factory):
    owner, _, wid = setup_workspace(client_factory)
    outsider, _ = client_factory("outside@example.com")
    for path in ("providers", "trials"):
        assert outsider.get(f"/api/workspaces/{wid}/ai/{path}").status_code == 404
    assert (
        outsider.post(f"/api/workspaces/{wid}/ai/trials", json={"prompt": "test"}).status_code
        == 404
    )


def test_trial_request_limit_and_csrf(client_factory, monkeypatch):
    client, _, wid = setup_workspace(client_factory)
    monkeypatch.setattr(settings, "ai_requests_per_minute", 1)
    assert (
        client.post(f"/api/workspaces/{wid}/ai/trials", json={"prompt": "test"}).status_code == 503
    )
    assert (
        client.post(f"/api/workspaces/{wid}/ai/trials", json={"prompt": "test"}).status_code == 429
    )
    assert (
        client.post(
            f"/api/workspaces/{wid}/ai/trials",
            json={"prompt": "test"},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )


def test_invalid_upstream_request_does_not_rebill_fallback(client_factory, monkeypatch):
    client, _, wid = setup_workspace(client_factory)
    for name in ("groq_api_key", "gemini_api_key"):
        monkeypatch.setattr(settings, name, SecretStr("synthetic-test-key"))
    calls = []

    def fail(name, prompt):
        calls.append(name)
        raise providers.ProviderFailure("invalid_request", 400)

    monkeypatch.setattr(providers, "complete", fail)
    assert (
        client.post(f"/api/workspaces/{wid}/ai/trials", json={"prompt": "test"}).status_code == 503
    )
    assert calls == ["groq"]


@pytest.mark.parametrize("provider", ["groq", "deepseek", "openai"])
def test_openai_sdk_adapters_with_verified_contracts(provider, monkeypatch):
    key_name = "tandem_openai_api_key" if provider == "openai" else f"{provider}_api_key"
    monkeypatch.setattr(settings, key_name, SecretStr("synthetic-test-key"))
    original = providers.OpenAI

    def transport(request):
        assert request.headers["authorization"] == "Bearer synthetic-test-key"
        body = json.loads(request.content)
        assert body["model"] == providers.provider_model(provider)
        if provider == "openai":
            assert request.url.host == "api.openai.com"
            assert (
                body["store"] is False
                and body["max_output_tokens"] == settings.ai_max_output_tokens
            )
            return httpx.Response(
                200,
                json={
                    "id": "resp_test",
                    "object": "response",
                    "status": "completed",
                    "created_at": 1,
                    "model": body["model"],
                    "output": [
                        {
                            "id": "msg_test",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {"type": "output_text", "text": "Test answer", "annotations": []}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                },
            )
        assert request.url.host == ("api.groq.com" if provider == "groq" else "api.deepseek.com")
        assert body["max_tokens"] == settings.ai_max_output_tokens
        return httpx.Response(
            200,
            json={
                "id": "chat_test",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Test answer"},
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            },
        )

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        return original(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport))
        )

    monkeypatch.setattr(providers, "OpenAI", factory)
    result = providers.complete(provider, "Test question")
    assert (result.text, result.input_tokens, result.output_tokens) == ("Test answer", 5, 3)


def test_gemini_sdk_adapter_and_no_automatic_tools(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic-test-key"))
    original = providers.genai.Client

    def transport(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "synthetic-test-key"
        assert "key=" not in str(request.url)
        body = json.loads(request.content)
        assert body["generationConfig"]["maxOutputTokens"] == settings.ai_max_output_tokens
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "Gemini answer"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
            },
        )

    def factory(**kwargs):
        assert kwargs["http_options"].retry_options.attempts == 1
        kwargs["http_options"].client_args = {"transport": httpx.MockTransport(transport)}
        return original(**kwargs)

    monkeypatch.setattr(providers.genai, "Client", factory)
    result = providers.complete("gemini", "Test question")
    assert result.text == "Gemini answer"
    assert result.input_tokens == 5


@pytest.mark.parametrize(
    "status,category", [(401, "authentication_or_access"), (402, "billing_required")]
)
def test_provider_errors_do_not_echo_credentials(monkeypatch, status, category):
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("synthetic-test-key"))
    original = providers.OpenAI

    def transport(request):
        return httpx.Response(
            status,
            json={
                "error": {
                    "message": "Upstream echoed synthetic-test-key",
                    "type": "authentication_error",
                }
            },
        )

    monkeypatch.setattr(
        providers,
        "OpenAI",
        lambda **kwargs: original(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport))
        ),
    )
    with pytest.raises(providers.ProviderFailure) as error:
        providers.complete("groq", "Test")
    assert error.value.category == category
    assert "synthetic-test-key" not in str(error.value)
