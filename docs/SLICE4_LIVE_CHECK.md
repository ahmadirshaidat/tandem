# Live agent and approval acceptance before Slice 6

**Gate: BLOCKED, not passed.** Checked on 2026-10-15 (Asia/Amman).

Slice 5 is merged into GitHub's default branch `v1` at `8cf8f14580082f7458919e7c6a8b0db4a6c84652`. Its [v1 CI run](https://github.com/ahmadirshaidat/tandem/actions/runs/38758946503) passed. That uses the deterministic fake provider and does not establish real-model readiness.

Secure bindings are now saved for Groq, Gemini and DeepSeek, and the backend can see them. The backend was recreated with fake mode off, current proxy/CA configuration and the default auth budget. Backend health and frontend login both returned HTTP 200. Credentials are no longer the missing prerequisite; real agent/proposal integration checks now fail. The product owner's manual Slice 5 acceptance is still not verified. DeepSeek workspace flows are outside this prerequisite check.

## Actual live attempts

The earlier attempts skipped with `no_key`/exit 2. After secure bindings became available, all four strict commands actually ran against the normal backend, each in a separate synthetic workspace:

| Provider | Configured model | Language | Actual result | Exit code |
|---|---|---|---|---:|
| Groq | `openai/gpt-oss-20b` | English | failed — unavailable | 1 |
| Groq | `openai/gpt-oss-20b` | Arabic | failed — unavailable | 1 |
| Gemini | `gemini-3.8-flash` | English | failed — unavailable | 1 |
| Gemini | `gemini-3.8-flash` | Arabic | failed — unavailable | 1 |

[Machine-readable evidence](live-provider-results.json) preserves the earlier skipped attempts separately. The four agent runs failed before executing any tool. Database checks confirmed zero task changes in all four synthetic workspaces. No real proposal approval or successful end-to-end inference latency is claimed. Exit 2 means a required credential is absent; exit 1 means a check failed; exit 0 means the selected flow completed, or an optional run skipped when `--require-live` was omitted. Always use strict mode for the Slice 6 gate.

Additional bounded diagnostics distinguish connection/protocol behavior from the complete workflow:

- The isolated structured-tool checker obtained a valid Groq `get_channel_context` request (3,709 input tokens, 154 output tokens). Groq model discovery reported `invalid_request`; this metadata failure did not prevent that one successful structured request.
- Gemini model discovery succeeded, but its structured generation check failed with `unavailable`. A direct generation diagnostic returned HTTP **504** (`ServerError`). This does not establish a successful Gemini tool call.
- From inside the running backend container, a basic Groq completion and Gemini model lookup both received responses. A Groq planning request using the app's JSON protocol returned HTTP **400**. Raising only the diagnostic's output budget to 2,048 tokens also failed, with safe error code **`tool_use_failed`**. The application's configured output budget was not changed.
- These are observed failures, not a proven root-cause fix. Resolve real planning/tool protocol compatibility and Gemini generation availability, then repeat all four flows. Native smoke checks, mocked tests and green CI do not replace a real proposal/approval pass.

## Secure setup and repeatable commands

Supply **fresh** keys through environment settings or the application's ignored local `.env`. Never send key values in chat, commit them, or put them in frontend variables. Secure bindings are present in the latest check; follow these steps again only when credentials/configuration change. Recheck runtime readiness and actual operations after any update.

Restart the backend with `AGENT_FAKE_PROVIDER=false`; leave TLS verification enabled. In this cloud workspace use `AGENT_FAKE_PROVIDER=false AUTH_RATE_LIMIT=10 python3 infra/cloud_start.py`, then start the frontend as documented in README. For desktop use the existing `node infra/dev.mjs` launcher after editing that project's private `.env`. Changing `.env` without recreating the backend container does not update its running configuration. Do not use production data; every helper invocation creates a separate synthetic test account/workspace/project.

From the repository root, with backend dependencies installed and normal backend/frontend services running:

```bash
backend/.venv/bin/python infra/check_agent_providers.py
backend/.venv/bin/python infra/check_approval_live.py --provider groq --language en --require-live
backend/.venv/bin/python infra/check_approval_live.py --provider groq --language ar --require-live
backend/.venv/bin/python infra/check_approval_live.py --provider gemini --language en --require-live
backend/.venv/bin/python infra/check_approval_live.py --provider gemini --language ar --require-live
```

The commands above use the cloud/native port 3000. For the desktop launcher append `--origin http://localhost:3001` to all four approval commands. On Windows replace the Python executable with `backend\.venv\Scripts\python.exe`; Python/uv and native backend dependencies are needed to run helpers outside Docker. The launcher itself only requires Node/Docker. Run `uv sync --project backend --frozen` to prepare the native helper dependencies when needed.

For each case, the helper restricts the provider chain to the selected provider, refuses fake mode, waits for a completed run rather than approving a partial/failed run's proposal, checks the selected provider, and reads the exact stored proposal. It verifies zero tasks before approval, submits its displayed version/hash and a generated operation key, verifies created task titles/descriptions and Agent attribution, retries with the same key, and checks that the task count did not grow. Arabic mode requires Arabic letters in each title/description; this verifies script presence, not semantic quality. Approval is performed by the synthetic human test owner's authenticated HTTP session. It is not approval by the product owner or a manual UI test.

Only provider/model/language/status/count/timing metadata is printed on success. Preserve safe output and exit codes; do not paste keys, prompts, retrieved bodies or provider exception bodies into reports. If model discovery or structured output fails, record the actual safe category and configured model rather than silently replacing it with a fake or another provider. Replace the failure evidence above only after real flows pass.

## Product-owner manual UI acceptance — pending

Use a synthetic workspace, with the real provider selected and fake mode off. Complete the checklist and record who tested it, the date and the actual outcome:

- [ ] Mention `@Agent` with an English task request; inspect the proposed stored fields and sources. Confirm no task exists before approval.
- [ ] Edit/remove a proposed item, approve, and verify exactly the reviewed changes appear in Tasks and for a second user. Inspect the human attribution and Audit log.
- [ ] Request an Arabic proposal and check that the Arabic content is meaningful, direction is correct, and the review/approval flow works.
- [ ] Reject a proposal and confirm no task change. Verify a Viewer cannot approve and an Editor cannot approve a high-risk proposal.
- [ ] Confirm offline approval controls are disabled. Review the mobile sheet if available; distinguish emulation from a physical device.
- [ ] Confirm Groq and Gemini both passed the real checks above, including proposal approval; record configured model names and failures/latencies honestly.

Only after the real checks and this manual acceptance pass should Slice 6 implementation begin. No Slice 6 branch or memory/RAG code is created by this prerequisite work.

## Harness validation

`backend/tests/test_live_check_helper.py` tests strict missing-key exits with no network, Arabic request/response checks, waiting for run completion, fake-mode rejection, failed/mismatched-provider rejection, unapproved mutation detection, displayed hash enforcement and idempotent retry/task count. Its HTTP responses are mocked explicitly. These tests check the acceptance harness and **do not satisfy the live-provider gate**.

Run from `backend`: `.venv/bin/pytest -q tests/test_live_check_helper.py`. The focused run passed **10 tests**. The full backend suite passed **105 tests in 34.92 seconds**, with one existing Starlette/httpx deprecation warning. Backend/helper lint and format passed, and `alembic check` found no new upgrade operations. Full CI also runs these tests, and lints/formats the helper. Existing Slice 5 validation remains in [SLICE5_REPORT.md](SLICE5_REPORT.md).

The latest focused recheck, `.venv/bin/pytest -q tests/test_proposals.py tests/test_live_check_helper.py`, passed **26 tests in 11.06 seconds** with the same existing deprecation warning. These validate proposal boundaries and the harness; they do not use real models.

## Slice 5 and Slice 6 status review

- **Slice 5:** implementation is merged in `v1` and hosted CI is green. Proposal and acceptance-helper tests pass. Real-provider integration remains **not passed**, for the failures above. The stricter checker/report is in draft [PR #1](https://github.com/ahmadirshaidat/tandem/pull/1), not merged into `v1`.
- **Slice 6:** no `slice-6-memory` branch, memory/RAG implementation or Slice 6 completion report exists in the checked GitHub repository. It remains gated on the successful real-provider and product-owner acceptance checks; this review does not implement Slice 6.
