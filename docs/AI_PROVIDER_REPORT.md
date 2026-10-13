# AI provider setup and trial report

Date: 2026-10-13. Branch: `v1`.

## Outcome

The app now has a workspace-protected **Try AI** screen that uses real backend provider calls. **Groq works:** a real answer passed through the Docker backend and Next.js frontend and was displayed in desktop and 390px mobile browsers. DeepSeek and Gemini are configured but their current generation requests fail for the reasons below. Optional future OpenAI support is implemented and tested against SDK contracts; no real OpenAI key was supplied or validated.

Codex is the development tool used to build and run the app. It does not replace the runtime providers or supply their API keys. Mobile support here means responsive web. No native iOS/Android app, public hosting deployment, or App Store release was created.

## Live provider results

| Provider | Configuration | Actual checks | Current result |
| --- | --- | --- | --- |
| Groq | Temporary key configured privately; model `openai/gpt-oss-20b` | Real generation from the host, Docker backend and authenticated browser; real reply rendered on desktop and mobile | **Working.** Kept as the default primary provider. |
| DeepSeek | Temporary key configured privately; model `deepseek-flash` selected from its model listing | Model listing succeeds. Real generation returns upstream HTTP 402; the app records `billing_required` and returns a safe dependency error | **Needs account balance/billing.** Fund the account through DeepSeek if you want to use it; no financial action was taken. |
| Gemini | Temporary key configured privately; model `gemini-3.8-flash` | Model listing succeeds. Google rejects 2.5 Flash as retired for new users and recommends 3.8 Flash. Real 3.8 generation returned upstream 500/503 service errors; the app records `unavailable` | **Generation unavailable in these checks.** Model listing alone does not prove generation works. The errors do not establish that the key is invalid. |
| OpenAI | No real key configured; optional model `gpt-5.5` | Responses API adapter, request limits, `store=false`, authentication headers and result parsing validated with a mocked HTTP transport | **Prepared, not live-validated.** Add your own main key securely when ready. |

Only small synthetic questions were used for live checks. Automatic fallback behavior was tested with controlled provider failures; this is separate from a successful live generation at every provider. Initial network access was blocked; later allowed requests established the results above. The environment draft includes the required provider destinations, but a saved draft does not by itself prove publication or restoration in a new task.

## Credentials and privacy

- The three supplied trial values are in the existing, Git-ignored `.env` with mode `0600`. Existing database/session settings were preserved. No credential values are included in this report, example files, install/start instructions or commits.
- Cloud requirements were saved for `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, and `GEMINI_API_KEY`. The corresponding allowed HTTPS hosts are `api.groq.com`, `api.deepseek.com`, and `generativelanguage.googleapis.com`.
- Optional personal binding `TANDEM_OPENAI_API_KEY` and destination `api.openai.com` were added for a future key. The `TANDEM_` name avoids the cloud's reserved `OPENAI_` namespace; the backend explicitly passes it to the SDK.
- All keys stay server-side. The frontend receives provider/model names and key-presence flags, never API key values. A configured flag is not an online/validity claim.
- Only the submitted question is sent to the chosen provider. Workspace history, member data, files, credentials and tools are not included. Questions and answers are not stored in trial history.
- Upstream error bodies are discarded. The persisted history includes workspace/actor attribution, provider attempts, safe categories/status codes, elapsed time and token usage when available.
- The keys were supplied in chat, so treat them as exposed test credentials and rotate them before real use. Enter future real keys yourself through secure environment settings rather than chat. The private `.env` is local development configuration, not a production vault.

## Implemented behavior

- `GET /api/workspaces/{workspace_id}/ai/providers`: safe provider/model status and request limits.
- `POST /api/workspaces/{workspace_id}/ai/trials`: authenticated, CSRF-protected Owner/Admin trials.
- `GET /api/workspaces/{workspace_id}/ai/trials`: the latest 20 redacted records, restricted to the same workspace and Owner/Admin roles.
- Manual provider selection runs only that provider. Automatic selection starts with `AI_PRIMARY_PROVIDER` (Groq by default), then configured alternatives. Access, rate-limit, billing and service failures can fall back; invalid requests stop to avoid rebilling the same invalid request. SDK retries are disabled.
- Limits: 4,000 input characters, 512 output tokens by default, five requests per user and per workspace per minute, and four concurrent requests per backend process. Switching workspaces does not reset a user's limit. These in-memory limits assume one backend process; a shared limiter is needed before scaling.
- Provider URLs are fixed in server code. Requests cannot choose arbitrary endpoints or submit API keys. Membership is checked again before delivering the result.
- The UI supports light/dark themes, labelled controls, mobile navigation, real answers as plain text, clear pending/error states, provider selection and redacted history. Tests verify model output cannot execute as HTML.
- The cloud runtime now receives the existing proxy, its resolved host mapping and the public trusted CA. A discovered permission issue was fixed: the public CA is mode `0644` for the non-root container, while `.env` stays `0600`. Private-key material is rejected as a public CA bundle. TLS verification remains enabled.

## Files changed or added

| Area | Files |
| --- | --- |
| Provider configuration | `.env.example`, `backend/app/core/config.py`, `backend/pyproject.toml`, `backend/uv.lock`, `compose.yaml` |
| Provider API | `backend/app/ai/providers.py`, `backend/app/ai/router.py`, `backend/app/ai/__init__.py`, `backend/app/main.py` |
| Persistence | `backend/app/core/models.py`, migration `5ef693bcfd14_record_redacted_ai_provider_trial_.py` |
| Web/mobile UI | `frontend/src/app/ai/page.tsx`, `frontend/src/components/ai-trial.tsx`, `frontend/src/components/workspace-app.tsx`, `frontend/src/app/globals.css` |
| Verification | `backend/tests/test_ai.py`, `backend/tests/test_ai_limits.py`, `frontend/tests/ai-trial.test.tsx`, `frontend/e2e/workspaces.spec.ts` |
| Cloud runtime | `infra/cloud_environment.py`, `infra/cloud_build.py`, `infra/cloud_start.py`, `infra/compose.cloud.yaml` |
| Documentation | `README.md`, this report, `docs/adr/0003-provider-trials.md` |

## Validation

- **39 backend tests pass.** Includes the original authentication/workspace checks plus provider status redaction, scoped permissions/isolation, fallback/manual behavior, CSRF, missing keys, rate limits, workspace-switch budget protection, SDK request/response contracts, billing classification and safe errors. Automated tests use synthetic credentials and mocked provider transports; they do not spend the supplied keys.
- **17 frontend tests pass.** Includes existing auth/API tests plus trial permissions, scoped submission, safe plain-text answers, honest failure states and disabled sending without keys.
- **2 browser tests pass.** Covers independent users, roles, invitation acceptance, workspace switching, mobile layouts, AI trial access and provider settings. CI browser tests make no paid provider calls.
- Lint, TypeScript checks, production build and Alembic schema-drift check pass. The backend tests migrate a fresh disposable PostgreSQL database, including the new trial table.
- Separate live browser validation confirmed a real Groq reply, mobile layout without overflow, and persisted redacted DeepSeek/Gemini failures. This is a real provider check rather than a mocked UI demonstration.
- Credential scans cover staged source and generated frontend output. Git ignores `.env`, `.local/`, runtime mail, screenshots and generated build files.
- These are current-instance checks. They do not assert a successful remote GitHub Actions run, public deployment, environment publication or fresh-task restoration.

## How to use it

1. Start the app using the README. In this cloud, build with `python3 infra/cloud_build.py` when needed, then start backend/database with `python3 infra/cloud_start.py`. Start Next.js from `frontend/` with `npm run dev` (or `npm run start` after a build).
2. Create/log into your account, select a workspace you own/administer, and choose **Try AI**.
3. Choose **Groq** or **Automatic**, enter a small synthetic question and send it. Inspect the labelled answer and recent-trial history.
4. Review/save the environment draft and publish when you want to retain the prepared environment. Supply secure binding values through environment settings for future tasks; snapshot publication does not keep live processes running.

For a future OpenAI main key, set `TANDEM_OPENAI_API_KEY` securely, set `AI_PRIMARY_PROVIDER=openai` or select OpenAI manually, and restart the backend. Override `OPENAI_MODEL` if your account uses a different supported model. Changing these settings does not require frontend code changes. For another main provider, replace that provider's secure key and primary/model settings instead.

## Remaining work

- DeepSeek needs external billing/balance to generate answers. Gemini generation needs a successful upstream service response before it can be called working. Optional OpenAI needs your future key and a real connectivity/generation check.
- A public HTTPS deployment and native mobile packaging were not requested/configured. Physical-phone keyboard/landscape testing is not covered by Chromium viewport checks.
- This is an isolated provider trial requested after Slice 1. Channels, full shared-agent tool execution, proposals, approvals, memory/RAG and collaborative documents remain later work from the PRD.
- Email ownership verification and production mail configuration remain earlier documented gaps. The code should not be described as a production launch.
