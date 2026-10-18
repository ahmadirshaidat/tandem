# Hosted manual-testing deployment

Prepared 18 October 2026. This branch packages the existing Slice 7 snapshot for hosting; it does not implement Slice 8 or satisfy owner acceptance. PostgreSQL, the Python API, document sync and the guarded frontend are now ONLINE with successful Railway deployments. The existing private Site is published and connected to that frontend. See [the failure and recovery evidence](evidence/hosted-deployment/RAILWAY_BUILD_FAILURE.md). See [the current deployed release](evidence/hosted-deployment/LIVE_RELEASE.md) for exact versions, checks and remaining limitations. Owner acceptance remains pending.

## Selected route and remaining account requirements

Use Railway for four services: PostgreSQL with pgvector, Python API with local E5 inference, Node document sync, and the existing Next.js frontend. Only the frontend gets a public HTTPS domain. Database, API and sync communicate over private networking. OpenAI Sites cannot run these Docker services directly; a Sites entry point requires a separately reachable deployment first.

Railway is connected. The private [Tandem project](https://railway.com/project/58f9f37c-aa18-46e7-8e73-0ab6873ede54?environmentId=3ad12379-4643-441c-aea0-9868d6c863a9) has a `manual-testing` environment with the database, API and document sync plus two 500 MB volumes. The owner applied the corrected deployment after the first API and sync builds failed Dockerfile validation. All three current deployments are successful. The fourth, guarded frontend service and private Sites gateway are deployed. Current recovery evidence is linked above. The owner confirmed Free/Trial only with no paid billing enabled; the budget remains **$0 out of pocket**. The connected app does not expose the account balance. Do not upgrade the plan or promise that this stack fits a free allowance.

Railway disables SMTP on Free, Trial and Hobby plans. This branch therefore supports Resend HTTPS delivery for the existing password-reset emails, in addition to the original SMTP and local outbox modes. Secure deployments still reject local outbox mode and incomplete mail configuration. The owner-supplied test `RESEND_API_KEY` and `MAIL_FROM` are saved privately in the Railway environment; the API service references them. A Resend test sender (`Tandem <onboarding@resend.dev>`) can send only to the Resend account owner; arbitrary recipients require a verified domain. Real email delivery remains unverified until a reset is received.

Externally usable Groq/Gemini keys must also be supplied privately before enabling the agent worker. The configured worker is currently disabled and fake mode is off. Runtime proxy placeholders from the development environment are not portable keys. Never paste keys into chat, commit an `.env`, or print resolved Compose configuration. No paid plan upgrade has been authorized.

## Deployment inputs

`compose.hosted.yaml` describes the topology and can be used as a Compose import baseline. Import support does not guarantee every Compose field is transferred: review the staged services, variables, build contexts, volumes, health checks, private DNS and target ports before deployment. Start with one instance of each service; do not configure replicas around startup migrations or the in-memory sync rooms.

| Service | Build / image | Private target | Persistent mount |
| --- | --- | --- | --- |
| `db` | `pgvector/pgvector:pg17` | PostgreSQL 5432 | `/var/lib/postgresql/data` |
| `backend` | repository root, `infra/Dockerfile.hosted-backend` | HTTP 8000, health `/health` | `/data` |
| `document-sync` | context `sync`, `Dockerfile.hosted` | HTTP/WebSocket 8002, health `/health` | none; Python persists document state |
| `frontend` | context `frontend`, `Dockerfile` | HTTP 3000, health `/health` | none |

In Railway, set service source roots/build paths to match these contexts; a backend service needs access to both `backend/` and `infra/`. Its Dockerfile path is `infra/Dockerfile.hosted-backend`. Frontend Docker build arguments **must** receive the actual private `BACKEND_URL` and `DOCUMENT_SYNC_URL`; Next.js bakes rewrites during the build. Runtime-only changes to those URLs require a frontend rebuild. Use the project's actual private DNS names rather than assuming Compose aliases exist on Railway. New Railway networks support IPv4; verify connectivity for these IPv4-bound API/sync services if using an older IPv6-only project.

Generate fresh database, JWT and document-sync secrets privately. Supply the backend's `DATABASE_URL` using the private database endpoint. The bootstrap accepts `postgres://`, `postgresql://` or the existing `postgresql+psycopg://` form. Backend and sync must share `DOCUMENT_SYNC_SECRET`; the frontend needs neither this secret nor provider keys. Give the frontend a separate random `SITES_GATEWAY_SECRET`, stored privately in Sites as `TANDEM_GATEWAY_SECRET` as well. Keep database credentials out of public/frontend variables.

Assign the frontend HTTPS domain, then set that exact origin, without a trailing slash, as `FRONTEND_URL` on backend and sync. The API and sync configuration uses the existing Sites origin; the gateway must use that same origin. Set `COOKIE_SECURE=true`, `MAIL_MODE=resend`, `RESEND_API_KEY` and an authorized `MAIL_FROM`. On an SMTP-capable host, use `MAIL_MODE=smtp`, `SMTP_HOST` and the correct port/authentication instead. Keep `AGENT_FAKE_PROVIDER=false`. Supply existing authorized Groq/Gemini models and credentials without substitutions to evade quota. Disable agent workers temporarily if real-provider testing is not yet ready, and record that limitation.

Railway mounts volumes with root ownership. Set backend `RAILWAY_RUN_UID=0` (Compose uses `user: 0:0`). The launcher initializes only the controlled `/data` directories, then drops to UID/GID 10001 **before** migrations, model loading and Uvicorn. Confirm the actual main process's `/proc/1/status`, rather than the user of an interactive exec command. Attach a persistent `/data` volume for attachments and E5; avoid recursive ownership changes on every boot.

The bootstrap runs Alembic, downloads E5 only when its manifest is absent, and requires local hash/model validation and an inference call before starting the API. A new download resolves the upstream revision at download time. Record the actual manifest identity after deployment; the historical retrieval benchmark does not automatically validate a changed revision. Give first startup enough time for the model download and initialization, and confirm the volume survives a restart. A successful build does not verify model-download networking on Railway.

Do not expose PostgreSQL, API or sync publicly. Platform TLS terminates at the frontend; preserve the original browser Origin, auth cookies and WebSocket upgrades through Next.js. Check real `https://` login and `wss://` document editing after deployment. Backups, restore drills, capacity measurements and production operations remain separate acceptance work.

## Local verification

Build without credentials in the Docker context:

```bash
docker build -f infra/Dockerfile.hosted-backend -t tandem-hosted-backend:local .
docker build -t tandem-hosted-frontend:local frontend
docker build -f sync/Dockerfile.hosted -t tandem-document-sync:latest sync
backend/.venv/bin/pytest -q -c backend/pyproject.toml infra/test_hosted_backend.py
node infra/check_hosted_stack.mjs
```

Railway rejects BuildKit secret mounts, so the hosted Dockerfiles do not contain them. The ordinary development Dockerfiles keep their cloud trust support. In this restricted cloud workspace, use `python infra/cloud_build.py --hosted backend document-sync frontend`: it streams a temporary Dockerfile with dependency-install CA mounts to local Docker, without changing the tracked hosted files or persisting the CA in an image. TLS verification stays enabled. The smoke driver requires Docker, OpenSSL, installed `sync` dependencies and the existing verified public E5 cache at `.local/models/e5-small`. It creates an isolated network, fresh database and volume, generates ephemeral test credentials and a trusted local TLS certificate, then removes its resources. The local cache avoids an upstream download during this check. It does not modify the normal development database or send mail or agent requests. On abrupt process termination, inspect and remove only resources bearing that run's `tandem-hosted-check-` prefix.

See [the recorded checks](evidence/hosted-deployment/LOCAL_CHECKS.md). The startup regression suite checks fail-closed HTTPS/real-mail/fake-mode configuration and persistent-directory handling; CI includes it. Email transport tests mock the external service and verify error redaction and reset-link preservation. These checks do not replace real email receipt, the integration/browser suite or the [owner checklist](MANUAL_ACCEPTANCE.md).

## Sites follow-through

The existing private [Tandem Site](https://tandem-workspace-preview.ahmad-majed.chatgpt.site) is the deployed entry point. `infra/sites-gateway.mjs` is the
Worker source copied into that Site's source repository. Runtime values
`UPSTREAM_ORIGIN` and secret `TANDEM_GATEWAY_SECRET` select the guarded Railway
frontend. The Worker forwards only Tandem session cookies and the necessary
application/CSRF/RSC/WebSocket headers; Sites identity and authorization stay at
Sites. Redirects to the upstream origin return to the Site and responses are
private/no-store. The Site's owner-only audience must remain unchanged.

`frontend/server.mjs` requires the matching `SITES_GATEWAY_SECRET` before serving
HTTP or accepting WebSocket upgrades. Next.js runs on loopback port 3001 behind
this guard, so its own upgrade listener cannot bypass the outer check. Only
GET `/health` is public; it reports readiness after Next responds. The secret is
removed before proxying requests into Next and is omitted from its child process.
Ordinary local `npm run dev` / `npm start` keep their existing behavior; the hosted
Docker image uses the guarded entry point. The Compose baseline also requires the
secret and needs a trusted gateway to inject it for browser use.

Gateway tests cover credential isolation, session and CSRF forwarding, RSC,
WebSocket response preservation, fixed upstream routing, redirects and redacted
failures. The isolated stack smoke also checks direct HTTP/WebSocket rejection
and authenticated document persistence through the guard. These tests do not
establish a live Cloudflare-to-Railway WebSocket connection or owner acceptance.

## Hosting reference sources

- [Railway Dockerfiles and build arguments](https://docs.railway.com/builds/dockerfiles)
- [Railway Docker Compose mapping guide](https://docs.railway.com/guides/docker-compose)
- [Railway private networking](https://docs.railway.com/networking/private-networking)
- [Railway volumes and permissions](https://docs.railway.com/volumes)
- [Railway email restrictions](https://docs.railway.com/networking/outbound-networking#email-delivery)
- [Railway trial limits](https://docs.railway.com/pricing/free-trial)
- [Railway configuration reference](https://docs.railway.com/config-as-code/reference): TOML/JSON config-as-code is deprecated, with legacy support ending 1 December 2026. This branch does not introduce a legacy `railway.toml`.
