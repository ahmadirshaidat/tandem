# First Codex Prompt - Repo Foundation + Slice 1 (Authentication and Workspaces)

Paste everything below the line into Codex. Place `PRD.md` at `docs/PRD.md` in the repository first.

---

You are a Principal Software Architect and Senior Full-Stack Engineer building an AI-native collaborative workspace for software teams.

## Source of truth
Read `docs/PRD.md` completely before doing anything. For anything in the frontend, also read `docs/UI_SPEC.md` and implement its color tokens (light and dark), typography, components and motion rules as CSS variables mapped into the Tailwind theme. It defines the product, vocabulary, decisions, stack, and the delivery plan. Do not invent scope. If something is ambiguous, list it as an open question in your final report instead of guessing silently.

## Your scope in this task: Slice 0 + Slice 1 ONLY
Do **not** start Slice 2 or anything later (no messaging, tasks, agent, RAG, or documents yet).

### Slice 0 - Repo foundation
- If no repository exists, initialize a clean monorepo: `frontend/`, `backend/`, `infra/`, `docs/`.
- `infra/`: Docker Compose with PostgreSQL using the pgvector image (enable the `vector` extension via migration or init script), environment-based configuration, a `.env.example`.
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic. Modular monolith layout (separate modules for auth, workspaces, and shared core). Structured logging, `/health` endpoint, consistent error responses.
- Frontend: Next.js + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query. App shell with dark mode and a responsive layout.
- GitHub Actions workflow that runs backend and frontend tests and lint.

### Slice 1 - Authentication and workspaces
Backend and frontend, with real persistence (no mocks):
1. **Auth:** register, login, logout, refresh. Email + password; hash with argon2 (or bcrypt); short-lived access token plus refresh token delivered in httpOnly cookies *(default; propose an ADR if you recommend otherwise)*. Input validation and rate limiting on auth endpoints.
2. **Workspaces:** create a workspace (creator becomes Owner); list my workspaces; switch workspace in the UI.
3. **Memberships and roles:** `Owner/Admin`, `Editor/Developer`, `Viewer`. Admin/Owner can change roles and remove members.
4. **Invitations:** Admin/Owner creates an invitation (single-use token link with expiry and a target role); an invited user accepts it and joins with that role.
5. **Authorization:** a reusable server-side dependency that checks workspace membership and minimum role on every workspace-scoped endpoint. `workspace_id` on all workspace-owned tables with foreign keys and indexes.
6. **Frontend screens** (match the design canvas listed in PRD section 14): sign up, log in, forgot password, create workspace, workspace switcher in the sidebar, members page with the role permission matrix, accept-invitation page, and the getting-started empty state.

## Acceptance criteria (all must be verified by running tests)
- `docker compose up` starts Postgres and the backend; migrations apply cleanly from an empty database.
- A new user can register, create a workspace, invite a second user, and the second user can accept and join with the assigned role.
- **Workspace isolation test:** a user in workspace A gets 403/404 for every workspace B resource.
- **Role tests:** Viewer cannot invite or change roles; Editor cannot change roles; Admin/Owner can; the last Owner cannot be removed or demoted.
- Expired or reused invitation tokens are rejected.
- Auth endpoints are rate limited; passwords are never logged or returned.
- Backend and frontend test suites pass in CI; provide the exact commands to run them locally.

## Working rules
1. Inspect the repository first; preserve any existing working code.
2. Present a concise implementation plan before coding.
3. Implement incrementally and run the relevant tests after each part; fix failures before continuing.
4. Keep the application runnable at all times.
5. Record architectural decisions as short ADRs in `docs/adr/` (at minimum: auth/session strategy, repository layout).
6. Never fabricate test results or claim a feature works without having implemented and run it.
7. Do not build mock-only UI; every completed flow must use the real API and database.

## Final report (required)
Summarize: changed/added files, features completed, test commands and their actual results, known gaps, open questions, and the proposed next step (Slice 2: real-time channels and messaging).
