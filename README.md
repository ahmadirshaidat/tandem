# Tandem

An AI-native collaborative workspace for software teams. This repository implements **Slice 0 (foundation), Slice 1 (authentication and workspaces), Slice 2 (real-time channels and messaging), and Slice 3 (projects and tasks)** from [the PRD](docs/PRD.md), with [the UI specification](docs/UI_SPEC.md). Slice 2 is merged into `v1` after verified green CI. Slice 3 is on `slice-3-tasks`, branched from that verified `v1`; `main` has not been created.

## Requirements

Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 24, Docker with Compose v2. PostgreSQL runs in Docker; no LLM credentials are required. The test database user needs CREATE DATABASE permission (the local Compose user has it).

## Run locally

### Codex desktop / Windows

This is the new **AI workspace** project at `ahmadirshaidat/tandem`, branch `slice-3-tasks`. An older local project named Tandem is a different project. Clone this repository into a **new folder** and open that folder in Codex desktop:

```powershell
git clone --branch slice-3-tasks --single-branch https://github.com/ahmadirshaidat/tandem.git tandem-workspace-v1
cd tandem-workspace-v1
```

If you already cloned the new project into `C:\Users\ahmad\Documents\tandem-workspace-v1`, update that folder without cloning again:

```powershell
cd "C:\Users\ahmad\Documents\tandem-workspace-v1"
git fetch origin refs/heads/slice-3-tasks:refs/remotes/origin/slice-3-tasks
git switch slice-3-tasks
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

Default models are `openai/gpt-oss-20b`, `gemini-3.8-flash`, `deepseek-flash`, and optional `gpt-5.5`; override their respective model variables when provider availability changes. Output is capped at 512 tokens and input at 4,000 characters, with five trials per user and per workspace per minute and four simultaneous calls per backend process. Switching workspaces does not reset the user's budget. Automatic fallbacks can incur multiple provider requests. Use synthetic test content; only the submitted question is sent externally, and prompt/answer text is not stored in the trial history.

See [the AI provider report](docs/AI_PROVIDER_REPORT.md) for actual live-provider results and limitations. This is an isolated trial feature requested after Slice 1; the shared agent's channel integration, tools, memory and approvals are still future work. Mobile support is responsive web, not a native iOS/Android app. No public hosting deployment has been performed.

## What is implemented

- Register, log in, log out, refresh and password reset, with Argon2id hashing, httpOnly cookies, CSRF protection and rate limiting.
- Create/list/switch workspaces; update their names. Creators become Owners.
- List members, change roles, transfer ownership and remove members, enforcing permissions and the last-Owner rule on the server.
- Expiring, email-bound, single-use invitations; preview, accept, list, revoke and reissue. Creation returns a link for the inviter to share.
- Sign-up, login, forgot/reset password, workspace creation, workspace switcher, getting started, members/role matrix, invitation acceptance and general settings screens. Light/dark mode, responsive layout and keyboard-accessible controls.
- PostgreSQL migrations including pgvector, structured logs without passwords/tokens, database-aware health checks, consistent API errors, CI and real-database/browser tests.

The frontend now uses the uploaded **Workspace UI UX - Web + Mobile.html** canvas for the auth, invitation, getting-started, members and general settings screens. Its colors, fonts, indigo linked-circle logo, panel layout, proposal illustration, checklist, tables and mobile sheets were compared with extracted reference screens. See [the frontend design report](docs/FRONTEND_DESIGN_REPORT.md) for screenshots and deliberate differences where the canvas shows future features.

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

See [session strategy](docs/adr/0001-authentication-and-sessions.md) and [repository layout](docs/adr/0002-repository-layout.md). Next planned slice: projects and tasks (Slice 3). Shared agent execution, RAG, collaborative documents, marketing and billing remain future work.


## Slice 2: channels and messaging

Open **Chat** after creating or selecting a workspace. A public `general` channel is created for new workspaces and backfilled when upgrading Slice 1. Public channels automatically include workspace members; leaving tracks participation and keeps public reading access. Editors, Admins and Owners create public channels. Viewers can post and reply. Only Admins/Owners create private channels and manage their membership, and even they must belong to a private channel to see it.

Create a channel from the sidebar (mobile: Channels). Channel details supports topic/name updates, archive/unarchive, public join/leave and private membership. Messages support threads, own edits/deletion, Admin deletion, member mentions, safe bold/italic/code/links, optimistic sends and explicit Retry. @Agent only stores a mention; it never calls Try AI or a model. Board/Docs tabs are disabled with Coming soon.

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
