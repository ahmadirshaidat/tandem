# Slice 0 + Slice 1 validation

Validated in the current Codex cloud machine on 2026-10-13. These results do not claim deployment, environment publication, or a successful remote GitHub Actions run.

| Check | Actual result |
| --- | --- |
| `cd backend && .venv/bin/pytest -q` | 23 passed; no skipped tests. Uses a new PostgreSQL database, runs Alembic from empty, then deletes only that test database. |
| Backend `ruff check app migrations tests` and `ruff format --check app migrations tests` | Passed. |
| `cd backend && .venv/bin/alembic check` | Passed; no schema drift. |
| `cd frontend && npm test` | 13 passed across 2 files. Tests API/CSRF contracts, refresh, safe redirects and connected auth form behavior. |
| Frontend `npm run lint` and `npm run typecheck` | Passed. |
| `cd frontend && npm run build` | Passed; optimized Next.js build for all 9 application routes. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | 2 passed. Two independent browser accounts register, create/join a workspace, enforce Viewer restrictions, promote to Admin, switch workspaces and exercise light/dark mode. Mobile checks cover login and members at 390px without page overflow. |
| Fresh isolated Compose project | Passed. New PostgreSQL volume, automatic migrations, pgvector, API health, registration, workspace creation and password-reset email delivered to the private container outbox. Disposable services/volumes removed afterwards; the development database preserved. |
| `bash infra/install_cloud.sh` replay | Passed. Existing `.env` preserved, locked Python/Node dependencies installed, Docker image rebuilt through the existing trusted proxy. |
| Development Compose startup | PostgreSQL and backend healthy; `/health` returns connected database and `vector: true`. |

Backend tests also cover all workspace-scoped endpoints for isolation, Viewer/Editor restrictions, Admin/Owner management, the last-Owner invariant (including concurrent demotions), invitation expiry/reuse/revocation/reissue and concurrent acceptance, session rotation/replay/logout/expiry, invalid input without password disclosure, CSRF, rate limits and concurrent password resets.

The initial browser attempt required selecting the machine's existing Chromium. A later run overlapped container recreation; it was rerun after health verification. An extended mobile check then found hidden accessibility labels escaping their scroll containers; relative positioning fixed the containment and the complete browser suite passed afterwards. No assertions were removed or disabled.

## Limits and open questions

- The Claude design canvas is inaccessible through the current network policy. The written UI spec is implemented; exact comparison to its 39-screen canvas needs an exported design or accessible reference. Later-slice screens are intentionally not built.
- Physical-device testing with a real mobile keyboard and landscape orientation has not been performed. Chromium viewport checks are distinct from physical-device validation.
- Email verification is not in this slice. Invitation acceptance binds to the logged-in email, but registration does not prove mailbox ownership; verification must precede use with real teams.
- Development reset email uses the private file outbox. Production SMTP delivery requires deployment configuration and has not been tested against an external mail server.
- Auth rate limiting is designed for one backend process. A shared limiter and trusted proxy IP forwarding are needed before multi-worker deployment.
- The dependency stack reports a Starlette deprecation warning for its httpx TestClient compatibility. All 23 tests execute and pass; this is not a skipped suite.

Next proposed work: Slice 2, real-time channels and messaging. No work from Slice 2 or later was started.
