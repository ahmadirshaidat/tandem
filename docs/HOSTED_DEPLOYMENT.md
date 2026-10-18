# Hosted manual-testing deployment

Prepared 18 October 2026. This branch packages the existing Slice 7 snapshot for hosting; it does not implement Slice 8 or satisfy owner acceptance. **No Railway deployment or new Sites publication has occurred.** Existing Sites pages are frontend previews and cannot establish full-stack acceptance.

## Selected route and remaining account requirements

Use Railway for four services: PostgreSQL with pgvector, Python API with local E5 inference, Node document sync, and the existing Next.js frontend. Only the frontend gets a public HTTPS domain. Database, API and sync communicate over private networking. OpenAI Sites cannot run these Docker services directly; a Sites entry point requires a separately reachable deployment first.

The current session has no connected Railway account or confirmed hosted backend. Connect Railway before provisioning. Check the account's actual credits, trial restrictions, resource estimates and spending controls first: the owner's budget remains **$0 out of pocket**. Do not provision a billable plan or promise that this stack fits a free allowance. Persistent PostgreSQL and local ONNX inference require real memory and disk; a sleeping or memory-limited service may not be suitable.

Real SMTP credentials and externally usable provider keys must be supplied through the host's private variables. Runtime proxy placeholders from a development environment are not portable keys. Never paste keys into chat, commit an `.env`, or print resolved Compose configuration. No paid resources, credentials or SMTP delivery have been verified here.

## Deployment inputs

`compose.hosted.yaml` describes the topology and can be used as a Compose import baseline. Import support does not guarantee every Compose field is transferred: review the staged services, variables, build contexts, volumes, health checks, private DNS and target ports before deployment. Start with one instance of each service; do not configure replicas around startup migrations or the in-memory sync rooms.

| Service | Build / image | Private target | Persistent mount |
| --- | --- | --- | --- |
| `db` | `pgvector/pgvector:pg17` | PostgreSQL 5432 | `/var/lib/postgresql/data` |
| `backend` | repository root, `infra/Dockerfile.hosted-backend` | HTTP 8000, health `/health` | `/data` |
| `document-sync` | context `sync`, `Dockerfile` | HTTP/WebSocket 8002, health `/health` | none; Python persists document state |
| `frontend` | context `frontend`, `Dockerfile` | HTTP 3000, health `/login` | none |

In Railway, set service source roots/build paths to match these contexts; a backend service needs access to both `backend/` and `infra/`. Its Dockerfile path is `infra/Dockerfile.hosted-backend`. Frontend Docker build arguments **must** receive the actual private `BACKEND_URL` and `DOCUMENT_SYNC_URL`; Next.js bakes rewrites during the build. Runtime-only changes to those URLs require a frontend rebuild. Use the project's actual private DNS names rather than assuming Compose aliases exist on Railway. New Railway networks support IPv4; verify connectivity for these IPv4-bound API/sync services if using an older IPv6-only project.

Generate fresh database, JWT and document-sync secrets privately. Supply the backend's `DATABASE_URL` using the private database endpoint. The bootstrap accepts `postgres://`, `postgresql://` or the existing `postgresql+psycopg://` form. Backend and sync must share `DOCUMENT_SYNC_SECRET`; the frontend needs neither this secret nor provider keys. Keep database credentials out of public/frontend variables.

Assign the frontend HTTPS domain, then set that exact origin, without a trailing slash, as `FRONTEND_URL` on backend and sync. Set `COOKIE_SECURE=true`, `MAIL_MODE=smtp`, `SMTP_HOST`, the correct SMTP port/authentication, and a verified `MAIL_FROM`. Keep `AGENT_FAKE_PROVIDER=false`. Supply existing authorized Groq/Gemini models and credentials without substitutions to evade quota. Disable agent workers temporarily if real-provider testing is not yet ready, and record that limitation.

Railway mounts volumes with root ownership. Set backend `RAILWAY_RUN_UID=0` (Compose uses `user: 0:0`). The launcher initializes only the controlled `/data` directories, then drops to UID/GID 10001 **before** migrations, model loading and Uvicorn. Confirm the actual main process's `/proc/1/status`, rather than the user of an interactive exec command. Attach a persistent `/data` volume for attachments and E5; avoid recursive ownership changes on every boot.

The bootstrap runs Alembic, downloads E5 only when its manifest is absent, and requires local hash/model validation and an inference call before starting the API. A new download resolves the upstream revision at download time. Record the actual manifest identity after deployment; the historical retrieval benchmark does not automatically validate a changed revision. Give first startup enough time for the model download and initialization, and confirm the volume survives a restart. A successful build does not verify model-download networking on Railway.

Do not expose PostgreSQL, API or sync publicly. Platform TLS terminates at the frontend; preserve the original browser Origin, auth cookies and WebSocket upgrades through Next.js. Check real `https://` login and `wss://` document editing after deployment. Backups, restore drills, capacity measurements and production operations remain separate acceptance work.

## Local verification

Build without credentials in the Docker context:

```bash
docker build -f infra/Dockerfile.hosted-backend -t tandem-hosted-backend:local .
docker build -t tandem-hosted-frontend:local frontend
docker build -t tandem-document-sync:latest sync
backend/.venv/bin/pytest -q -c backend/pyproject.toml infra/test_hosted_backend.py
node infra/check_hosted_stack.mjs
```

Restricted cloud runtimes may require their existing public CA and proxy build arguments; never bake credentials into an image. The smoke driver requires Docker, OpenSSL, installed `sync` dependencies and the existing verified public E5 cache at `.local/models/e5-small`. It creates an isolated network, fresh database and volume, generates ephemeral test credentials and a trusted local TLS certificate, then removes its resources. The local cache avoids an upstream download during this check. It does not modify the normal development database or send mail or agent requests. On abrupt process termination, inspect and remove only resources bearing that run's `tandem-hosted-check-` prefix.

See [the recorded checks](evidence/hosted-deployment/LOCAL_CHECKS.md). The startup regression suite checks fail-closed HTTPS/SMTP/fake-mode configuration and persistent-directory handling; CI includes it. It does not replace the existing integration/browser suite or the [owner checklist](MANUAL_ACCEPTANCE.md).

## Sites follow-through

After the real backend is reachable, connect the existing private Tandem Site to the hosted application and verify the full authentication and WebSocket path. Preserve its owner-only audience. A Sites proxy must forward only Tandem's required cookies/headers and must not send Sites platform authentication upstream. Before treating the Sites audience as an access boundary, protect the separate hosted frontend against bypass. This gateway integration is **not implemented or tested** by these container changes. Do not publish another disconnected frontend or describe a preview as an acceptance environment.

## Hosting reference sources

- [Railway Dockerfiles and build arguments](https://docs.railway.com/builds/dockerfiles)
- [Railway Docker Compose mapping guide](https://docs.railway.com/guides/docker-compose)
- [Railway private networking](https://docs.railway.com/networking/private-networking)
- [Railway volumes and permissions](https://docs.railway.com/volumes)
- [Railway configuration reference](https://docs.railway.com/config-as-code/reference): TOML/JSON config-as-code is deprecated, with legacy support ending 1 December 2026. This branch does not introduce a legacy `railway.toml`.
