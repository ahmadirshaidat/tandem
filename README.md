# Tandem

An AI-native collaborative workspace for software teams. This repository implements **Slice 0 (foundation) and Slice 1 (authentication and workspaces)** from [the PRD](docs/PRD.md), with [the UI specification](docs/UI_SPEC.md). Development is on `v1`; `main` has not been created.

## Requirements

Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 24, Docker with Compose v2. PostgreSQL runs in Docker; no LLM credentials are required. The test database user needs CREATE DATABASE permission (the local Compose user has it).

## Run locally

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

The Claude canvas could not be fetched through the current network policy. The implementation follows the supplied written design tokens and screen definitions; exact canvas comparison remains outstanding.

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

See [session strategy](docs/adr/0001-authentication-and-sessions.md) and [repository layout](docs/adr/0002-repository-layout.md). Next planned slice: real-time channels and messaging. Chat, tasks, agent, RAG, documents, marketing and billing are not implemented in these slices.
