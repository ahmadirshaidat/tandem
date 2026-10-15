# Live agent and approval acceptance

**Gate: BLOCKED, not passed.** Checked on 2026-10-15 (Asia/Amman). This work fixes real-provider compatibility only; no Slice 6 work is included.

Slice 5 is merged in GitHub's default branch `v1` at `8cf8f14580082f7458919e7c6a8b0db4a6c84652`. Compatibility changes and this evidence are on `fix-agent-provider-compatibility`, [PR #2](https://github.com/ahmadirshaidat/tandem/pull/2). The tested code revision is `de7f9e6a2bc51aac20d66dc99d99c0bd9a04d0f6`; its [hosted CI passed](https://github.com/ahmadirshaidat/tandem/actions/runs/38807994296). CI uses a fake provider and is separate from the real checks below.

Secure bindings were available and actual SDK requests authenticated. The normal backend was rebuilt/recreated with fake mode off, Groq `openai/gpt-oss-120b`, Gemini `gemini-3.5-flash`, a 15-second agent transport timeout and a 2,048-token agent output cap. Auth rate limiting remained at its normal budget of 10. Backend health and frontend login returned HTTP 200. No keys, prompts, retrieved content or provider response bodies are included in this evidence. DeepSeek workspace calls are outside this task.

## Final strict acceptance commands

Each command ran against the rebuilt defaults in a separate synthetic workspace. These are the final matrix results, including failures; earlier successes do not replace a failed final check.

| Provider / model | Language | Actual result / exit | Agent duration | Proposal wall time | Approval HTTP | Input / output tokens |
|---|---|---|---:|---:|---:|---:|
| Groq `openai/gpt-oss-120b` | English | Completed approval / 0 | 1,938 ms | 2,132.74 ms | 65.94 ms | 4,447 / 404 |
| Groq `openai/gpt-oss-120b` | Arabic | Completed approval / 0 | 2,145 ms | 2,389.60 ms | 59.43 ms | 6,803 / 375 |
| Gemini `gemini-3.5-flash` | English | Failed: `rate_limited` / 1 | 226 ms | — | — | 0 / 0 recorded* |
| Gemini `gemini-3.5-flash` | Arabic | Failed: `rate_limited` / 1 | 3,045 ms | — | — | 0 / 0 recorded* |

Both Groq successes verified zero tasks before approval, exact stored/displayed task fields after approval, Agent attribution, two created tasks and no duplicates when retrying approval with the same idempotency key. Approval used the authenticated synthetic human test owner's HTTP session, not an agent tool or the product owner's manual UI session. Arabic assertions verify Arabic script in titles/descriptions, not semantic quality.

The final isolated checker exited **1**:

| Provider / model | Discovery | Structured request | Generation wall time | Attempts | Input / output tokens |
|---|---|---|---:|---:|---:|
| Groq `openai/gpt-oss-120b` | Available | Valid `get_channel_context` request | 619.41 ms | 1 | 1,821 / 78 |
| Gemini `gemini-3.5-flash` | Available | Failed: HTTP 429 `rate_limited` | 178.96 ms | 1 | Unreported |

429 is terminal for an invocation: no automatic retry, account switching or model hopping to evade quota. A later acceptance run needs sufficient provider quota. No complete live gate is claimed.

\* Token totals cover provider-reported successful generations. Failed HTTP attempt usage is unknown. A run audit total of zero means no successful-generation tokens were recorded, not zero billed tokens. Proposal wall time includes polling and audit lookup; agent duration includes real generation and tools. These measurements are not the earlier fake-provider 255 ms queue/transport measurement.

## Model selection and bounded diagnostics

The original baseline failed all four strict flows before any tool execution: Groq 20B planning returned HTTP 400 `tool_use_failed`; Gemini 3.8 generation returned HTTP 504. Those failures, the original zero-task checks and earlier missing-key skips remain in [machine-readable evidence](live-provider-results.json).

Groq's [official SDK parameter documentation](https://github.com/groq/groq-python/blob/main/src/groq/types/chat/completion_create_params.py) documents `json_schema`, JSON mode, `tool_choice=none` and reasoning settings. The authenticated models endpoint returned 11 entries and advertised tools/JSON/schema output for GPT-OSS 20B and 120B. Qwen 3.8 27B advertised tools/JSON mode, without schema-constrained output. Llama 3.3 70B and Qwen 3 32B were absent and were not called. Google's [official SDK JSON-schema documentation](https://github.com/googleapis/python-genai/blob/main/README.md#json-response-schema) documents JSON MIME plus response schema. Direct Groq/Google documentation websites were blocked by cloud egress, so official owned GitHub sources were used. Public source URLs/checksums and selected model-catalog metadata are preserved in the evidence file; documentation-host additions are saved in the environment draft and have not been applied to this running instance.

Each candidate below was actually tested against the app's planning protocol; these probes execute no tools and do not establish full approval compatibility. Probe wall time includes model lookup/client setup and generation/retries.

| Provider / model | Format used | Actual planning outcome | Wall time | Attempts | Input / output tokens |
|---|---|---|---:|---:|---:|
| Groq `openai/gpt-oss-20b` | Strict JSON schema | Valid project/task reads | 1,254.76 ms | 1 | 3,790 / 80 |
| Groq `openai/gpt-oss-120b` | Strict JSON schema | Valid project read | 934.18 ms | 1 | 3,790 / 61 |
| Groq `qwen/qwen3.8-27b` | JSON object | Valid project/task reads | 958.84 ms | 1 | 3,670 / 36 |
| Gemini `gemini-3.8-flash` | JSON MIME + schema | Failed: final HTTP 503 | 16,912.18 ms | 3 | Unreported |
| Gemini `gemini-3.5-flash` | JSON MIME + schema | Valid reads after one 5xx retry | 6,096.90 ms | 2 | 3,717 / 45 |

A further bounded Gemini 3.8 probe recorded **504, 504, 503**, then failed after **30,367.63 ms**; token usage was unreported. Lookup availability did not establish generation availability. No Gemini 2.5 live call was made; the agent rejects that family before transport.

Use **GPT-OSS 120B and Gemini 3.5 Flash** as defaults, with the decision and tradeoffs in [ADR 0021](adr/0021-agent-provider-compatibility.md). Existing explicit deployment overrides require an update and backend restart. The 120B choice has real English/Arabic approval evidence. 20B passed isolated planning but full attempts encountered denied invented IDs, premature prose before first-read enforcement, and quota errors; it is not declared incapable of structured output. Qwen was tested only for planning. Gemini 3.5 recovered and completed earlier approvals, whereas 3.8 remained unavailable under bounded retries.

The capability table chooses documented output formats per provider/model. Sealed wire objects carry JSON-encoded arguments, which the server decodes and validates with Pydantic and the existing authorized registry. The first turn must read context; proposal schemas become available after ID reads. A committed proposal finishes with the existing human-review explanation, avoiding an unnecessary final generation that previously failed after proposal creation.

Protocol errors `tool_use_failed`/`json_validate_failed` receive one retry with a shorter fixed instruction. Bounded server-side repair accepts only fences/trailing commas followed by strict validation; it never logs failed generation text. Gemini 5xx/504 receives at most two retries with 0.5/1 second backoff and a 15-second attempt timeout. Other 4xx/429 are not retried. Existing worker deadline and authorization/approval checks remain enforced.

## Earlier outcomes retained

The evidence file preserves intermediate failures and successes, including results before first-read enforcement and before removing the redundant final model request:

- Gemini 3.5 English completed proposal/approval in **7,785.55 ms**, approval **100.52 ms**, **5,723 / 291** input/output tokens.
- Gemini 3.5 Arabic completed proposal/approval in **14,698.56 ms**, approval **82.70 ms**, **7,328 / 430** tokens. An earlier Arabic attempt failed `invalid_response` after **14,076 ms** with **7,326 / 1,073** reported tokens. Failed generation text was not retained; its exact cause is unknown. The later success does not erase this failure or establish reliability.
- An earlier Groq 120B English approval passed in **2,152.55 ms**, approval **106.46 ms**, **4,446 / 389** tokens.
- Intermediate full flows also returned `rate_limited`, `access_changed` or completed without a proposal. These are retained rather than silently counted as passing proposals.
- An earlier isolated Gemini 3.5 check succeeded after one 5xx retry in **4,669.17 ms**, **1,628 / 23** tokens. The final isolated 429 remains a failure.

## Repeatable commands

Use the existing secure environment bindings or an ignored local `.env`; never put secrets in frontend variables or source control. Restart the backend after configuration changes, with `AGENT_FAKE_PROVIDER=false`. In this cloud workspace the tested startup is `AGENT_FAKE_PROVIDER=false AUTH_RATE_LIMIT=10 python3 infra/cloud_start.py`; run the frontend as documented in README. Desktop uses `node infra/dev.mjs`. Run only against synthetic data.

From the repository root, with normal backend/frontend services running:

```bash
backend/.venv/bin/python infra/check_approval_live.py --provider groq --language en --require-live
backend/.venv/bin/python infra/check_approval_live.py --provider groq --language ar --require-live
backend/.venv/bin/python infra/check_approval_live.py --provider gemini --language en --require-live
backend/.venv/bin/python infra/check_approval_live.py --provider gemini --language ar --require-live
backend/.venv/bin/python infra/check_agent_providers.py
```

The four commands use port 3000; desktop users append `--origin http://localhost:3001`. On Windows use `backend\.venv\Scripts\python.exe`. Prepare native helper dependencies with `uv sync --project backend --frozen` if needed. Model-only bounded probes can be reproduced with `backend/.venv/bin/python infra/check_agent_models.py --output /tmp/agent-models.json` or one `--model` selector; they are not approval tests. Avoid repeated quota probes.

Strict missing-key checks exit 2. Failed live checks exit 1. Completed strict approval flows exit 0. Optional checks without `--require-live` may skip; a skip never passes acceptance. Helpers refuse fake mode and provider mismatch, wait for a completed agent run, verify the displayed version/hash, and check authorization-sensitive mutation boundaries and idempotence. Output contains only safe metadata.

## Regression and CI validation

The full backend suite passed **133 tests in 33.24 seconds**, with one existing Starlette/httpx deprecation warning. Regression cases mock protocol errors, simplified retry, Gemini exponential backoff/exhaustion, no retries for other 4xx, syntax-only repair, duplicate/non-finite/forbidden field rejection, Pydantic validation, safe error redaction, capability selection, first-read enforcement and finishing a stored proposal without a redundant provider request. Ordinary tests clear injected real keys. These are not live-provider evidence.

Backend/helper lint and format passed; Alembic found no schema drift; generated event-contract checks passed. [CI for the tested code](https://github.com/ahmadirshaidat/tandem/actions/runs/38807994296) also passed frontend lint, typecheck, unit tests, production build and Playwright integration tests. CI's fake-provider results do not clear the live gate. Existing Slice 5 validation remains in [SLICE5_REPORT.md](SLICE5_REPORT.md).

## Product-owner manual UI acceptance — pending

Manual acceptance is separate from the synthetic HTTP checks. Record who tested, when and the actual outcome in a synthetic workspace with a real provider:

- [ ] Inspect an English `@Agent` proposal and confirm no task exists before approval.
- [ ] Edit/remove an item, approve, verify exactly the reviewed changes for a second user, and inspect human attribution/Audit.
- [ ] Check meaningful Arabic content, direction and the complete review/approval flow.
- [ ] Reject a proposal; verify Viewer approval denial and Editor denial for high-risk proposals.
- [ ] Confirm offline approval is disabled and review mobile behavior, distinguishing emulation from a physical device.
- [ ] Confirm both real providers pass all four strict commands and the isolated checker with sufficient quota.

The final Gemini quota failures, persistent Gemini 3.8 generation failures and unverified manual acceptance remain open. No Slice 6 implementation or readiness claim is made.
