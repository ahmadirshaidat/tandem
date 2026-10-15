"""Mocked compatibility regressions, never evidence of a live model passing."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.agent.json_protocol import parse_object
from app.agent.llm import WorkspaceLLM, decode_turn, wire_schema
from app.ai import providers
from app.ai.capabilities import capability
from app.core.config import settings

WIRE = {"calls": [{"name": "list_projects", "arguments_json": "{}"}], "answer": ""}
PRIVATE = "never-log-failed-generation-or-secret"


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("synthetic-test-key"))
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic-test-key"))
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    monkeypatch.setattr(settings, "tandem_openai_api_key", None)


def chat_response(body):
    return httpx.Response(
        200,
        json={
            "id": "synthetic",
            "object": "chat.completion",
            "created": 1,
            "model": settings.groq_model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": body},
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
        },
    )


def mock_groq(monkeypatch, responses, requests):
    original = providers.OpenAI
    iterator = iter(responses)

    def transport(request):
        requests.append(json.loads(request.content))
        return next(iterator)

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"] == settings.agent_provider_timeout_seconds
        return original(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport))
        )

    monkeypatch.setattr(providers, "OpenAI", factory)


@pytest.mark.parametrize("code", ["tool_use_failed", "json_validate_failed"])
def test_one_simplified_retry_uses_strict_supported_format_and_never_echoes_failure(
    monkeypatch, caplog, code
):
    requests = []
    mock_groq(
        monkeypatch,
        [
            httpx.Response(
                400,
                json={"error": {"code": code, "message": PRIVATE, "failed_generation": PRIVATE}},
            ),
            chat_response("```json\n" + json.dumps(WIRE) + "\n```"),
        ],
        requests,
    )
    turn, completion = WorkspaceLLM().turn(
        "groq", {"question": "Synthetic plan", "tools": [], "results": []}
    )
    assert turn.calls[0].name == "list_projects"
    assert len(requests) == completion.attempts == 2
    assert completion.repaired and completion.safe_errors == [code]
    assert (completion.input_tokens, completion.output_tokens) == (7, 5)
    for req in requests:
        assert req["tool_choice"] == "none" and "tools" not in req
        assert req["response_format"]["type"] == "json_schema"
        assert req["response_format"]["json_schema"]["strict"] is True
        assert req["max_tokens"] == settings.agent_max_output_tokens
        assert req["reasoning_effort"] == "low"
    assert requests[0]["messages"][0] != requests[1]["messages"][0]
    assert PRIVATE not in json.dumps(requests) and PRIVATE not in caplog.text


@pytest.mark.parametrize("valid", [True, False])
def test_final_failed_generation_is_ephemeral_and_still_requires_pydantic(
    monkeypatch, caplog, valid
):
    requests = []
    generation = json.dumps(WIRE if valid else {**WIRE, "execute": PRIVATE})
    mock_groq(
        monkeypatch,
        [
            httpx.Response(
                400, json={"error": {"code": "json_validate_failed", "failed_generation": PRIVATE}}
            ),
            httpx.Response(
                400,
                json={"error": {"code": "json_validate_failed", "failed_generation": generation}},
            ),
        ],
        requests,
    )
    if valid:
        turn, completion = WorkspaceLLM().turn("groq", {"question": "Synthetic", "results": []})
        assert turn.calls[0].arguments == {}
        assert completion.repaired and completion.attempts == 2
        assert completion.input_tokens is None and completion.output_tokens is None
    else:
        with pytest.raises(providers.ProviderFailure) as error:
            WorkspaceLLM().turn("groq", {"question": "Synthetic", "results": []})
        assert error.value.category == "invalid_response" and PRIVATE not in str(error.value)
    assert len(requests) == 2
    assert PRIVATE not in json.dumps(requests) and PRIVATE not in caplog.text


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_non_recoverable_requests_are_not_retried(monkeypatch, status):
    requests = []
    mock_groq(monkeypatch, [httpx.Response(status, json={"error": {"message": PRIVATE}})], requests)
    with pytest.raises(providers.ProviderFailure) as error:
        WorkspaceLLM().turn("groq", {"question": "Synthetic", "results": []})
    assert len(requests) == 1 and error.value.status == status
    assert PRIVATE not in str(error.value)


@pytest.mark.parametrize("statuses", [[504, 503, 200], [504, 504, 504], [400], [401], [429]])
def test_gemini_uses_bounded_exponential_backoff_only_for_5xx(monkeypatch, statuses):
    original = providers.genai.Client
    requests, sleeps = [], []
    monkeypatch.setattr(providers.time, "sleep", sleeps.append)
    iterator = iter(statuses)

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "tools" not in body
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False
        status = next(iterator)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": PRIVATE}})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": json.dumps(WIRE)}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 5},
            },
        )

    def factory(**kwargs):
        opts = kwargs["http_options"]
        assert opts.retry_options.attempts == 1
        assert opts.timeout == int(settings.agent_provider_timeout_seconds * 1000)
        opts.client_args = {"transport": httpx.MockTransport(transport)}
        return original(**kwargs)

    monkeypatch.setattr(providers.genai, "Client", factory)
    if statuses[-1] == 200:
        turn, completion = WorkspaceLLM().turn("gemini", {"question": "Synthetic", "results": []})
        assert turn.calls[0].arguments == {} and completion.attempts == 3
        assert completion.safe_errors == ["upstream_timeout", "upstream_5xx"]
        assert (completion.input_tokens, completion.output_tokens) == (7, 5)
    else:
        with pytest.raises(providers.ProviderFailure) as error:
            WorkspaceLLM().turn("gemini", {"question": "Synthetic", "results": []})
        assert error.value.attempts == len(statuses)
        assert PRIVATE not in str(error.value)
    assert len(requests) == len(statuses)
    assert sleeps == ([0.5, 1.0] if statuses[0] >= 500 else [])


def test_capabilities_do_not_assume_schema_support_and_wire_objects_are_sealed():
    assert capability("groq", "openai/gpt-oss-120b").format == "json_schema"
    assert capability("groq", "qwen/qwen3.8-27b").format == "json_object"
    assert capability("groq", "unrecognized").native_tools is None
    schema = wire_schema()
    assert schema["additionalProperties"] is False
    for item in schema["$defs"].values():
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(item["properties"])


def test_unsupported_gemini_25_never_calls_transport(monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")
    monkeypatch.setattr(
        providers, "gemini_client", lambda **kwargs: pytest.fail("No retired model calls")
    )
    with pytest.raises(providers.ProviderFailure, match="unsupported_model"):
        WorkspaceLLM().turn("gemini", {"question": "Synthetic", "results": []})


def test_repair_is_syntax_only_and_preserves_values():
    raw = '```json\n{"calls":[{"name":"list_tasks","arguments_json":"{\\"query\\":\\"literal,}\\"}",},],"answer":"",}\n```'
    turn, repaired = decode_turn(raw)
    assert repaired and turn.calls[0].arguments == {"query": "literal,}"}


@pytest.mark.parametrize(
    "body",
    [
        '{"calls":[],"answer":"safe","answer":"duplicate"}',
        '{"calls":[],"answer":"safe","execute":"not allowed"}',
        '{"calls":[],"answer":NaN}',
        '{"calls":[],"answer":"truncated',
        '{"calls":[],"answer":"one"}{"calls":[],"answer":"two"}',
        "__import__('os').system('false')",
    ],
)
def test_repair_never_invents_missing_content_or_drops_forbidden_fields(body):
    with pytest.raises(ValueError):
        decode_turn(body)


def test_duplicate_keys_inside_encoded_arguments_are_rejected():
    with pytest.raises(ValueError):
        decode_turn(
            json.dumps(
                {
                    "calls": [{"name": "list_tasks", "arguments_json": '{"limit":1,"limit":2}'}],
                    "answer": "",
                }
            )
        )
    with pytest.raises(ValueError):
        parse_object("{" + "x" * 20001)


def test_proposal_descriptions_are_deferred_until_authorized_id_reads(monkeypatch):
    from app.agent import llm
    from app.agent.tools import descriptors

    captured = []

    def response(provider, instructions, payload, schema):
        captured.append((json.loads(payload), schema))
        return providers.Completion(json.dumps(WIRE))

    monkeypatch.setattr(llm, "structured", response)
    for results in [
        [],
        [{"tool": "list_projects", "status": "ok", "data": []}],
        [{"tool": "get_task", "status": "ok", "data": {}}],
    ]:
        WorkspaceLLM().turn(
            "groq", {"question": "Synthetic", "tools": descriptors(), "results": results}
        )
    names = [{t["name"] for t in p["allowed_calls"]} for p, _ in captured]
    assert all(not n.startswith("propose_") for n in names[0])
    assert "propose_create_tasks" in names[1] and "propose_delete_task" not in names[1]
    assert "propose_delete_task" in names[2] and "propose_create_tasks" not in names[2]
    for (_payload, schema), offered in zip(captured, names, strict=True):
        assert set(schema["$defs"]["WireCall"]["properties"]["name"]["enum"]) == offered


def test_first_turn_schema_and_local_validator_require_reading_before_an_answer(monkeypatch):
    from app.agent import llm
    from app.agent.tools import descriptors

    def prose(provider, instructions, payload, schema):
        assert schema["properties"]["calls"]["minItems"] == 1
        assert schema["properties"]["answer"]["enum"] == [""]
        return providers.Completion('{"calls":[],"answer":"A plan without source IDs"}')

    monkeypatch.setattr(llm, "structured", prose)
    with pytest.raises(providers.ProviderFailure, match="invalid_response"):
        WorkspaceLLM().turn(
            "groq", {"question": "Synthetic plan", "tools": descriptors(), "results": []}
        )


def test_unoffered_calls_are_not_accepted_by_the_repair_path(monkeypatch):
    from app.agent import llm
    from app.agent.tools import descriptors

    monkeypatch.setattr(
        llm,
        "structured",
        lambda *args: providers.Completion(
            json.dumps(
                {
                    "calls": [{"name": "propose_create_tasks", "arguments_json": "{}"}],
                    "answer": "",
                }
            )
        ),
    )
    with pytest.raises(providers.ProviderFailure, match="invalid_response"):
        WorkspaceLLM().turn(
            "groq", {"question": "Synthetic", "tools": descriptors(), "results": []}
        )
