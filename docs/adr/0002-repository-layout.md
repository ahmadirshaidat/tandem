# ADR 0002: Modular monolith and same-origin frontend

Status: accepted for Slices 0 and 1.

Keep `frontend/` (Next.js, React, TypeScript, Tailwind 4, shadcn-style Radix UI primitives, TanStack Query), `backend/` (FastAPI, Pydantic, SQLAlchemy, Alembic), `infra/`, and `docs/` in one repository. Backend modules separate authentication, workspaces and shared infrastructure. PostgreSQL 17 with pgvector is the only service dependency. No Redis, AI providers or worker are needed for these slices.

Use synchronous SQLAlchemy/psycopg sessions per request. Alembic migrations define schema and constraints, including the vector extension. All workspace-owned rows have indexed workspace foreign keys; users, sessions and password resets are account-level entities and therefore intentionally have no workspace ID. A reusable membership dependency enforces workspace scope and minimum role. Requests without membership return 404. Tests use an independently migrated, disposable PostgreSQL database.

Use the Next.js rewrite as the browser's API entry point. This keeps authentication same-origin and avoids exposing the backend publicly. Docker Compose starts PostgreSQL and FastAPI; Next.js runs as a local development process. The backend image runs as a non-root user, applies migrations before serving, and reports database and vector readiness through `/health`. Dependency locks are committed. An optional cloud build helper passes the platform's existing proxy, DNS resolution and CA using build arguments and a temporary BuildKit secret; it retains TLS and package verification.

Theme colors come exclusively from CSS custom properties mapped into Tailwind. Fonts are bundled from fontsource packages, so builds do not require Google Fonts access. Dark mode follows the OS until overridden. A responsive authenticated shell supports workspace selection, members, settings and getting started. It deliberately does not implement later slices.
