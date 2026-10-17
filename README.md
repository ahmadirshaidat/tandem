# Tandem

An AI-native collaborative workspace for software teams. Slices 0–5 and the real-provider compatibility fixes are merged into `v1`. **Slice 6 (workspace memory and permission-filtered retrieval)** is implemented on `slice-6-memory`; see [the Slice 6 report](docs/SLICE6_REPORT.md) for actual checks and open acceptance gates. Documents remain a later slice.

## Requirements

Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 24, Docker with Compose v2. PostgreSQL runs in Docker; no LLM credentials are required. The test database user needs CREATE DATABASE permission (the local Compose user has it).

## Run locally

### Codex desktop / Windows

This is the new **AI workspace** project at `ahmadirshaidat/tandem`, branch `v1`. An older local project named Tandem is a different project. Clone this repository into a **new folder** and open that folder in Codex desktop:

```powershell
git clone --branch v1 --single-branch https://github.com/ahmadirshaidat/tandem.git tandem-workspace-v1
cd tandem-workspace-v1
```

If you already cloned the new project into `$env:USERPROFILE\tandem-workspace-v1`, update that folder without cloning again:

```powershell
cd "$env:USERPROFILE\tandem-workspace-v1"
git fetch origin refs/heads/v1:refs/remotes/origin/v1
git switch v1
git pull --ff-only origin v1
node infra/dev.mjs
```

A refused branch switch preserves your local changes; do not reset or overwrite them. This explicit fetch also works for the earlier single-branch Slice 2 clone.

Ensure **Node.js 24** and **Docker Desktop** are installed with Docker running. From this new repository folder:

```bash
node infra/dev.mjs
```

The launcher creates development configuration only if `.env` is missing, installs locked frontend dependencies, starts PostgreSQL and the backend with migrations, and starts the frontend. It opens **`http://localhost:3001/login`** only after checking this project's identity and its API. The new desktop project uses separate `tandem-workspace-v1` Docker containers/volumes, API port **8001**, and database port **5433**. It leaves an older project on port 3000 alone. Sign up, create a workspace, invite your team, and open Chat or Tasks. Your new workspace includes #general. Owners and Admins create projects, then Editors can add tasks. Keep the terminal open; Ctrl+C stops its frontend. Existing `.env` files and database data are preserved. Python and uv are only needed inside the backend container for this workflow.

If this frontend is already running, the launcher refreshes the backend configuration and reuses it. It verifies the `X-Tandem-Project` header rather than identifying an app by its name alone. If port 3001 belongs to another app, it stops with an explanation instead of killing that app. Use `--no-open` to leave browser opening to Codex and `--skip-install` when dependencies are already installed. Local provider keys belong in this new folder's ignored `.env`; keys saved in a cloud workspace do not automatically appear on your computer.

This cloud task cannot start processes on your desktop. A cloud service on port 3000 is separate from your computer's localhost. Run the launcher in a **Local** Codex task or your computer's terminal.

### Individual development commands

From the repository root:

```bash
python3 infra/bootstrap.py
uv sync --project backend --frozen
cd frontend
npm ci
cd ..
docker compose up -d --build --wait
cd frontend
npm run dev
```

The private, ignored `.env` is generated once with random development secrets; reruns preserve it. The frontend uses port 3000, the API 8000, and PostgreSQL 5432. The frontend proxies `/api` to the backend. `GET /health` checks the migrated schema and pgvector. Change `FRONTEND_URL` to match your actual browser origin when using a different hostname. Use `BACKEND_URL` when the frontend must proxy a different backend address.

### Codex cloud

Use the existing checkout in `/workspace/tandem`; tasks already have an isolated environment. Do not create a worktree unless explicitly requested.

The cloud's home directory is read-only and its proxy needs explicit DNS/trust support inside Docker builds:

```bash
export UV_CACHE_DIR=/workspace/.cache/uv
export npm_config_cache=/workspace/.cache/npm
export DOCKER_CONFIG=/workspace/tandem/.local/docker
python3 infra/bootstrap.py
uv sync --project backend --frozen
cd frontend
npm ci
cd ..
python3 infra/cloud_build.py
python3 infra/cloud_start.py
cd frontend
npm run dev
```

`cloud_build.py` uses the machine's existing HTTPS proxy and `SSL_CERT_FILE`, resolves the proxy in the host, and supplies its trusted CA as an ephemeral BuildKit secret. `cloud_start.py` also supplies the proxy DNS and mounts the public CA for provider requests at runtime. Neither disables verification or stores proxy credentials in the image. Later tasks must start services again; a saved environment snapshot does not retain running processes.

## Try AI on web and mobile

Log in as a workspace Owner or Admin and open **Try AI** in the sidebar or mobile tab bar. Select Groq or Automatic, enter a small test question, and send it. A successful reply identifies its provider/model. Failures show safe categories in the recent-trial history. The same authenticated API and responsive screen serve desktop and mobile browsers.

Provider keys live only on the backend. Configure `GROQ_API_KEY`, `GEMINI_API_KEY`, or `DEEPSEEK_API_KEY` in the private `.env` for local development or secure environment settings for cloud/deployment. Never put them in `NEXT_PUBLIC_` variables or frontend code. The supplied temporary keys are not committed. `AI_PRIMARY_PROVIDER=groq` is the default; Automatic mode tries Gemini, DeepSeek, then optional OpenAI on provider failures. Manual selection does not silently fall back.

To add a future OpenAI key yourself, set `TANDEM_OPENAI_API_KEY` securely and use `AI_PRIMARY_PROVIDER=openai` or select OpenAI in the trial screen. The OpenAI adapter uses the official Python SDK and Responses API with `store=false`; Groq/DeepSeek use compatible Chat Completions endpoints, while Gemini uses the official Google Gen AI SDK. No OpenAI key has been supplied or validated. Codex is the development tool used to build this app, separate from the providers the app calls.

Default models are `openai/gpt-oss-120b`, `gemini-3.5-flash`, `deepseek-flash`, and optional `gpt-5.5`; override their respective model variables when provider availability changes. Existing configurations pinning earlier IDs must update their own model settings and restart the backend. Trial output is capped at 512 tokens and input at 4,000 characters, with five trials per user and per workspace per minute and four simultaneous calls per backend process. Switching workspaces does not reset the user's budget. Automatic fallbacks can incur multiple provider requests. Use synthetic test content; only the submitted question is sent externally, and prompt/answer text is not stored in the trial history.

See [the AI provider report](docs/AI_PROVIDER_REPORT.md) for actual live-provider results and limitations. This remains an isolated trial feature. The shared agent has its own permission-aware channel and proposal workflow; Slice 6 adds local memory retrieval separately from Try AI. Mobile support is responsive web, not a native iOS/Android app. No public hosting deployment has been performed.

## What is implemented

- Register, log in, log out, refresh and password reset, with Argon2id hashing, httpOnly cookies, CSRF protection and rate limiting.
- Create/list/switch workspaces; update their names. Creators become Owners.
- List members, change roles, transfer ownership and remove members, enforcing permissions and the last-Owner rule on the server.
- Expiring, email-bound, single-use invitations; preview, accept, list, revoke and reissue. Creation returns a link for the inviter to share.
- Sign-up, login, forgot/reset password, workspace creation, workspace switcher, getting started, members/role matrix, invitation acceptance and general settings screens. Light/dark mode, responsive layout and keyboard-accessible controls.
- PostgreSQL migrations including pgvector, structured logs without passwords/tokens, database-aware health checks, consistent API errors, CI and real-database/browser tests.

The frontend now uses the uploaded **Workspace UI UX - Web + Mobile.html** canvas for the auth, invitation, getting-started, members and general settings screens. Its colors, fonts, indigo linked-circle logo, panel layout, proposal illustration, checklist, tables and mobile sheets were compared with extracted reference screens. See [the frontend design report](docs/FRONTEND_DESIGN_REPORT.md) for screenshots and deliberate differences where the canvas shows future features.

## Shared agent and audit (Slice 4)

An Owner/Admin enables the workspace agent in **Settings → Agent**, then chooses its channels. Public channels are eligible by default; private channels start off. Every member, including a Viewer, can mention **@Agent** in a message or thread. Adding a mention by editing a message schedules it once; retries/edits never create duplicate runs. The agent replies as its own teal actor with expandable read steps. It has no human membership or seat.

Twelve bounded read tools cover messages, full-text workspace search, tasks, projects, channel context, blockers and progress aggregation. They reuse the requesting user's REST authorization services. A shared reply also respects its destination audience: another private channel is excluded even for a requester who can open it. Tool results are untrusted data. Slice 5 adds six proposal tools described below; domain changes require human approval. Slice 6 adds `search_memory`, `find_similar_bugs` and `analyze_bug` as read-only tools. There are no direct mutation, network-fetch, filesystem, execution or document tools.

Groq → Gemini is the default provider chain. Only an Owner can opt in to DeepSeek/OpenAI for workspace data; the settings screen displays a data-sharing warning. Models/keys remain backend configuration, reused from Try AI. Startup checks configured model IDs and exposes discovery failures in settings rather than guessing availability. Missing keys produce a friendly unavailable message. **Try AI** stays an isolated Admin trial with synthetic questions.

Runs use a PostgreSQL queue (`FOR UPDATE SKIP LOCKED`), four worker slots and one concurrent run per workspace by default. `AGENT_RUN_TIMEOUT_SECONDS` defaults to 60; agent calls use a 15-second attempt timeout, one simplified protocol retry and at most two Gemini 5xx retries, with SDK retries disabled. User/workspace admission limits default to 5/20 per minute. Settings control the monthly run limit (default 1,000) and pause-at-limit; disabling pause allows overage. Stale jobs fail safely after restart instead of silently rebilling. Keep one Uvicorn worker as required by live presence/fan-out.

Settings → **Audit log** is Owner/Admin-only, with time, actor/action/status filters, cursor pagination, redacted details and CSV export (10,000 rows maximum per export; narrow the time range beyond that). Database triggers reject audit UPDATE/DELETE/TRUNCATE. Audit/run/tool metadata contains no prompt, retrieved content or answer; normal channel messages and their existing replay journal retain the conversation. Offline disables the Agent chip and keeps unsent drafts without sending on reconnect.

CI uses `AGENT_FAKE_PROVIDER=true` for deterministic tests without keys or external calls. Leave it **false** for real use; missing credentials never silently select a fake. The CI browser backend alone raises `AUTH_RATE_LIMIT` to 100 because the test users share one proxy address. Normal application default remains 10.

```bash
# Optional: synthetic real Groq/Gemini structured-call validation; skips absent keys.
backend/.venv/bin/python infra/check_agent_providers.py
# With an explicitly configured fake-provider backend and frontend running:
backend/.venv/bin/python infra/measure_agent.py --origin http://localhost:3000
# Explicitly allow synthetic real-provider timing when credentials are available:
backend/.venv/bin/python infra/measure_agent.py --origin http://localhost:3000 --live
```

See ADRs 0012–0016 for queue, actor/audit, permission/audience, injection and provider-sharing decisions. Screenshots, measured orchestration latency, actual checks and remaining limitations are in [SLICE4_REPORT.md](docs/SLICE4_REPORT.md).

## Proposals and human approval (Slice 5)

Mention **@Agent** with a task request or a plan such as “plan JWT authentication”. The agent can persist six kinds of proposal: create up to ten tasks with dependencies, edit title/description/status/due date, reassign, change priority, delete, or add a comment. It cannot execute any of these tools directly. The channel card renders the stored structured payload, its risk and approval role, sources, and eventual task links. Try AI remains separate.

Editors and Admins/Owners can approve low-risk task creation, field edits and comments. Reassignment, priority and deletion require Admin/Owner. Viewers can request and cancel their own proposals but can never approve. In **Settings → Agent → Approval rules**, Admins/Owners can tighten task creation to Admin only; high-risk rules stay locked. **Inbox → Approvals** lists actionable proposals, and the Agent panel lists pending proposals with links back to their channel or thread. Mentions and Assigned remain disabled.

Use **Edit** to review/change fields or remove items, then approve the reviewed set. The server checks the displayed version and payload hash, current access and rules, target versions, CSRF and an idempotency key. Approval applies all task/comment/dependency changes in one transaction using the human task services. Competing decisions execute at most once. Changed targets become Stale, invalid execution becomes Failed without partial changes, and proposals expire after seven days. Rejection accepts an optional reason; requester/Admin cancellation is recorded as Rejected with a distinct cancellation audit action. Every lifecycle transition and rule change is audited; task activity attributes the proposal to Agent and approval to the human.

Approval controls require an online connection; offline decisions are never queued. Arabic and mixed user text use automatic direction. The mobile review sheet supports 390px screens and the existing light/dark tokens. See [screenshots](docs/screenshots/slice5/) and [ADRs 0017–0020](docs/adr/0017-proposal-state.md).

`PROPOSAL_EXPIRY_DAYS` defaults to 7 and `PROPOSAL_PENDING_PER_CHANNEL` to 20. CI uses only deterministic fake calls. No real Groq/Gemini keys were available for Slice 5: **live checks skipped**. After supplying fresh keys securely and restarting with `AGENT_FAKE_PROVIDER=false`, run:

```bash
backend/.venv/bin/python infra/check_agent_providers.py
backend/.venv/bin/python infra/check_approval_live.py --provider groq
backend/.venv/bin/python infra/check_approval_live.py --provider gemini
# Explicit fake-provider backend plus frontend, for synthetic two-user WS timing:
backend/.venv/bin/python infra/measure_proposals.py --origin http://localhost:3000
```

The live approval helper creates a new synthetic workspace and acts as its human test owner to approve the returned proposal. It reports safe metadata and fails if the running backend uses fake mode. Fake-provider timing measures orchestration, storage and delivery; it is not model inference latency. [SLICE5_REPORT.md](docs/SLICE5_REPORT.md) records the actual results and limitations.

Before Slice 6, follow [the live acceptance checklist](docs/SLICE4_LIVE_CHECK.md). Run the helper separately for `--provider groq` and `--provider gemini`, each with `--language en` and `--language ar`, and add `--require-live`: missing keys then exit **2**, so a skipped run cannot satisfy the gate. The helper waits for the agent run to finish, checks Arabic titles/descriptions when requested, verifies stored payload/created task fields and a duplicate approval retry. The product owner's manual UI acceptance remains a separate checklist item. Harness tests use mocked HTTP and do not count as real-provider evidence.

The agent uses model-specific output formats, server-side Pydantic validation and bounded recovery; SDK native tool execution stays disabled. `AGENT_MAX_OUTPUT_TOKENS=2048` and `AGENT_PROVIDER_TIMEOUT_SECONDS=15` are separate from Try AI's limits. Gemini retries 5xx/504 twice with exponential delays; protocol errors get one simpler-instruction retry. Authentication and 429 errors are not automatically retried. [ADR 0021](docs/adr/0021-agent-provider-compatibility.md) records supported capabilities, safe JSON repair, model selection and remaining upstream failures. For synthetic model-candidate probes without executing tools, run `backend/.venv/bin/python infra/check_agent_models.py --output /tmp/agent-models.json`; these do not replace full acceptance.

## Password-reset email

Development sends real reset messages to a private local outbox rather than an external mail server. In a native backend, files are under `.local/mail/`; inside Compose, they are in the `mail_outbox` volume at `/app/.local/mail`. Inspect a message privately to use its single-use reset link. Do not commit messages or paste tokens into logs.

Production must set `COOKIE_SECURE=true`, `MAIL_MODE=smtp`, `SMTP_HOST`, and the appropriate SMTP credentials and sender, behind HTTPS. This slice does **not** verify account email ownership; add email verification before using invitations with real teams. SMTP requires STARTTLS with certificate verification. The limiter is for one backend process; a shared limiter and trusted proxy configuration are required before scaling to multiple workers.

## Tests and checks

Start the Compose services first. Backend tests automatically create, migrate and delete their own database and never truncate the development database:

```bash
cd backend
uv run --frozen ruff check app migrations tests
uv run --frozen ruff format --check app migrations tests
uv run --frozen pytest -q
uv run --frozen alembic check
cd ../frontend
npm run lint
npm run typecheck
npm test
npm run build
# Install browser once if needed:
npx playwright install --with-deps chromium
npm run test:e2e
```

Cloud machines with an existing Chromium can run browser tests without downloading another copy:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e
```

Playwright starts Next.js if needed, but expects the backend to be running. Browser tests exercise two independent user sessions, invitations, role changes, workspace switching and a 390px mobile login. Backend tests cover all workspace routes for isolation, role boundaries, concurrent invitation acceptance, invalid/expired/replayed tokens, session revocation, CSRF, password reset and rate limiting. CI runs lint, tests, production build and browser tests against PostgreSQL.

See [session strategy](docs/adr/0001-authentication-and-sessions.md) and [repository layout](docs/adr/0002-repository-layout.md). Slice 6 acceptance includes a real local-model evaluation and the outstanding product-owner manual Slice 5 UI test. Collaborative documents are proposed next only after those gates pass. Collaborative documents, marketing and billing remain future work.


## Slice 2: channels and messaging

Open **Chat** after creating or selecting a workspace. A public `general` channel is created for new workspaces and backfilled when upgrading Slice 1. Public channels automatically include workspace members; leaving tracks participation and keeps public reading access. Editors, Admins and Owners create public channels. Viewers can post and reply. Only Admins/Owners create private channels and manage their membership, and even they must belong to a private channel to see it.

Create a channel from the sidebar (mobile: Channels). Channel details supports topic/name updates, archive/unarchive, public join/leave and private membership. Messages support threads, own edits/deletion, Admin deletion, member mentions, safe bold/italic/code/links, optimistic sends and explicit Retry. @Agent invokes the shared agent when enabled in workspace/channel settings; task requests produce proposals for human approval. It does not use the isolated Try AI trial endpoint. Board/Docs tabs are disabled with Coming soon.

The authenticated `/api/ws` gateway uses the same origin and cookie as REST, with reconnect/catch-up including edits/deletions. Keep **one backend worker**; no Redis is required. The browser sends a ping every 15 seconds. Settings in `.env.example` are `MESSAGE_REQUESTS_PER_MINUTE` (60/user), `WS_CONNECTIONS_PER_USER` (5), `WS_CONNECTIONS_PER_IP` (30), `WS_FRAMES_PER_MINUTE` (120), `WS_IDLE_SECONDS` (60), and `ATTACHMENT_DIR` (native backend only; Compose uses its private `image_attachments` volume). Incoming frames are capped at 8 KiB, subscriptions at 50 channels/10 workspaces per connection, and typing expires after five seconds.

Attach up to **four PNG/JPEG/WebP/GIF images**, each at most **5 MiB** and 20 million pixels. The API accepts raw image bytes, validates magic and image structure, and serves authenticated channel URLs with no-store/nosniff. Neither files nor storage keys are public. Removed private/workspace members lose serving and live access. The dedicated image volume is initialized for the non-root backend user on a fresh start.

Channels and the last 150 synced message/reply records per visited channel remain readable from a per-account browser cache. Drafts stay local, with **no queued offline sends**. Cached image metadata remains visible; image bytes require an online authenticated request. The production build additionally caches the visited Chat shell and static assets for offline reloads; `npm run dev` supports in-page offline reading/drafts, while production offline reload validation uses `npm run build` and `npm run start`. Logout/account switch clears this app's cache; observed access revocation evicts affected channel histories. An offline device cannot discover a server-side revocation until reconnecting.

Additional checks from the repository root:

```bash
backend/.venv/bin/python infra/export_events.py --check
backend/.venv/bin/python infra/measure_channels.py --origin http://localhost:3000
```

On Windows use `backend\.venv\Scripts\python.exe` if running Python checks natively, and `--origin http://localhost:3001` for the desktop launcher. The benchmark creates synthetic accounts/workspace, sends 30 messages between two real WebSocket clients through Next.js, loads history 20 times, and prints timing JSON. It never calls a provider. Browser tests include two sessions, exact reconnect replay, image lightbox, XSS, offline reload/drafts, and 390 px/landscape layouts. Playwright starts the production server: run `npm run build` before `npm run test:e2e`, as CI already does.

See [the Slice 2 report](docs/SLICE2_REPORT.md) for actual validation and measurements, and ADRs [transport](docs/adr/0004-websocket-contract.md), [ordering](docs/adr/0005-channel-ordering.md), [images](docs/adr/0006-image-storage.md), and [fan-out](docs/adr/0007-event-fanout.md) for decisions and scale limits.

## Projects and tasks (Slice 3)

Open **Tasks** or a project in the sidebar. Owners/Admins create projects and manage their names, keys, colors, descriptions, archive state and linked channels. Editors create/edit/assign/move tasks and comment; Viewers read only. Task keys remain immutable even when the type changes. Board cards support drag-and-drop within a project and a keyboard/touch **Actions → Move to** alternative. Table filters, sorting, status grouping and selection support atomic bulk status/assignee changes (up to 100 tasks).

Task details show safe Markdown, field editing, comments, linked tasks/conversations and transactional activity. **Create task from message** shares the chosen title/description with the workspace and preserves a protected conversation link. Private links and their activity are visible only to people who can access both endpoints. Stale task edits require an explicit **Keep mine** or **Take server's** choice; writes are never silently queued offline. Previously synced board/table/details remain readable offline, subject to browser storage availability. Sign-out clears cached application data.

The board fetches up to 1,000 tasks and initially renders at most 40 cards per status. **Show more** expands a column; **Load more tasks** follows the API cursor beyond 1,000. Task filters operate on loaded records, and the UI shows when more records remain. Use a specific project when ordering cards. The server also supports filter/sort/cursor queries directly.

Seed a separate synthetic workspace for an existing local account, without changing its credentials or existing workspaces:

```bash
docker compose exec backend .venv/bin/python -m app.tasks.seed --owner-email you@example.com
```

For host development, from `backend`, use `.venv/bin/python -m app.tasks.seed --owner-email you@example.com` (Windows: `.venv/Scripts/python.exe`). Default count is 1,000; `--count` accepts 1–10,000. The output contains only workspace/project IDs and task count. The new workspace appears after refreshing the workspace picker.

With the local app and host backend dependencies running:

```bash
node infra/measure_tasks.mjs http://localhost:3000
```

This creates synthetic accounts/workspace, seeds 1,000 tasks, measures 20 board HTTP reads, cold board navigation-to-paint and 30 HTTP-edit-to-second-browser-WebSocket deliveries, then signs the test accounts out. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` optionally selects an installed browser. For the desktop launcher origin use `http://localhost:3001` and matching host database configuration. No provider calls occur. See [Slice 3 report](docs/SLICE3_REPORT.md) and ADRs 0008–0011 for validation, measured limits and design decisions.

## Workspace memory and search (Slice 6 branch)

The `slice-6-memory` branch adds persistent message/task/comment indexing, PostgreSQL full-text plus local ONNX/pgvector search, and Owner/Admin controls at **Settings → Memory**. Search is available at **Search** on desktop and through Settings navigation on mobile. Both require a connection. No document indexing is implemented.

Private-channel indexing defaults off. Inclusion never grants access: SQL candidates require current workspace/channel membership and live source/settings state before ranking. Agent retrieval also respects the destination audience. Source chips are re-authorized for the current viewer. Search exposes no inaccessible counts or skipped-source hints.

Memory settings support per-source inclusion, forever/one-year/90-day retention, queued reindexing, and explicit forgetting by source or selected records with a signed count preview. Derived records are removed; original messages/tasks remain. Forgetting a source turns it off and selected record suppression keys survive reindexing. Opt-in resolution summaries create only an extractive add-comment proposal after a new bug completion in an eligible public project channel; a human must approve before any comment exists. All control changes and forgetting are audited.

Embeddings never call an external inference service. The public model files must be downloaded separately and verified before local inference; until then retrieval visibly falls back to full-text. The candidate choice/quality gate is pending in [ADR 0022](docs/adr/0022-local-multilingual-embeddings.md); no semantic quality is claimed from unit-test model stubs.

With the backend container running, download the public E5-small ONNX candidate into its persistent local model directory:

```bash
docker compose exec backend python -m app.memory.embeddings e5-small
```

The downloader pins the upstream revision, requires an MIT/Apache-2.0 model-card license, checks artifact hashes and performs a local mixed-language inference check. It fails safely when model access/verification is unavailable. Installing a candidate does not itself pass the retrieval evaluation. For native development, run `.venv/bin/python -m app.memory.embeddings e5-small --destination ../.local/models/e5-small` from `backend`; an optional absolute `MEMORY_MODEL_PATH` overrides the default. `MEMORY_EMBEDDING_ENABLED=false` explicitly selects degraded full-text behavior.

Reindex from Memory settings, or from the repository root with backend dependencies installed:

```bash
backend/.venv/bin/python infra/memory_backfill.py --workspace WORKSPACE_ID --drain
backend/.venv/bin/python infra/run_eval.py --output eval/similar_bugs/results.json
```

The evaluation uses a disposable database and the committed 30-English/15-Arabic synthetic pairs, not development data. Real candidate comparison instructions and measurement limits are in [the evaluation README](eval/similar_bugs/README.md). Backfill shares the durable queue consumed by the existing worker; normal indexing needs no extra process. Model/version changes requeue missing active-version embeddings; a dimension change needs an explicit vector/index migration.

Strict optional live checks use synthetic data and real agent runs, with fake mode off. They print safe metadata only:

```bash
backend/.venv/bin/python infra/check_memory_live.py --language en --tool analyze_bug --require-live
backend/.venv/bin/python infra/check_memory_live.py --language ar --tool analyze_bug --require-live
backend/.venv/bin/python infra/check_memory_live.py --language en --tool find_similar_bugs --require-live
backend/.venv/bin/python infra/check_memory_live.py --language ar --tool find_similar_bugs --require-live
```

Append `--origin http://localhost:3001` for the desktop launcher. Missing credentials exit 2 in strict mode; failed checks exit 1. Live generation success with degraded retrieval is not a vector/hybrid quality pass. No AWS deployment is performed by Slice 6.

For semantic acceptance, also pass `--require-embeddings --embedding-model MODEL_ID`, where `MODEL_ID` is the exact local model selected by the real comparison. The checker rejects missing embeddings or a different model before requesting paid generation. The ordinary `--require-live` commands above still permit visibly degraded full-text retrieval and cannot close the embedding gate.

CI retains failed-test traces, screenshots and the Playwright HTML report in `browser-test-results-RUN_ATTEMPT` for seven days. Download the artifact from the failed Actions run and open its HTML report or trace locally. A passing rerun does not establish the cause of an earlier failure.
