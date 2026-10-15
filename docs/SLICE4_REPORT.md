# Slice 4: shared read-only agent and audit

Implemented on `slice-4-agent` from `v1` at `73c8dad4d0ebe416d5efc5ac72af4309194d8b3b`. Read-only Git confirmed both `v1` and `slice-3-tasks` pointed to that commit. Slice 3's report records green run 38630125874; the current GitHub API request returns Forbidden and the private run HTML is unavailable, so hosted CI cannot be independently asserted from that evidence.

## Completed behavior

The shared agent is a first-class message actor without a user account, membership or seat. Workspace enablement is off initially; public channels are eligible, private channels off. Any member including Viewers can mention it in top-level messages, replies or an edit adding a first mention. Trigger-message uniqueness and locked finalization provide one run and one final reply under retries. Agent-authored messages never enqueue another run.

PostgreSQL-backed queue claims use `FOR UPDATE SKIP LOCKED`, workspace serialization, four process worker slots and default workspace concurrency one. Run/call/step bounds, per-user and workspace admission limits, monthly usage/pause controls and stale-job recovery are implemented. Failure states return normal friendly agent messages. Provider fallback is audited. Runs persist only provider/model, usage, timing and status, with no prompt/context/answer text outside the existing channel conversation/journal.

The closed registry contains search_messages, search_workspace (PostgreSQL full-text search), list_tasks, get_task, list_projects, summarize_channel, identify_blockers, generate_progress_report and get_channel_context. Pydantic forbids extra arguments and bounds inputs/results. Tools recheck existing REST authorization services as the requester, expose no hidden conversation links or linked activity, and label returned data untrusted. Unknown/unauthorized calls are denied, audited and stop the run. Common change requests receive a deterministic manual-action refusal; no registered tool can mutate domain data regardless of phrasing.

A deliberate refinement to requester-only access protects the shared destination audience: private source channels are excluded except the destination itself, even for an Owner requester who can open another private channel. Source authorization is checked across provider turns and publication. Access revoked during a provider call prevents its answer from being posted.

AgentLLM uses a server-validated structured JSON tool protocol on shared provider SDK transports; SDK automatic function execution is disabled. Groq → Gemini is the default. Only an Owner can add DeepSeek/OpenAI, with a visible workspace-data warning. Model IDs remain configurable on the backend and are checked at startup when keys exist. Try AI retains its existing isolated Admin trial workflow.

Agent channel events (run_started, step, message_created, run_failed) extend the generated schema and use existing authorized journal replay. UI provides teal agent messages, real expandable tool steps, working/error states, active/offline-disabled mention chip, Agent scope/recent actions panel, future approval placeholder, settings with channel/model/limit controls and immutable audit detail/filter/export views. Mobile has four primary tabs, a 390px Agent panel and draft retention without auto-send. Existing light/dark tokens are reused.

Audit records lifecycle, tools (including denials), provider switches and all agent settings/channel/provider/limit changes. Arguments containing free text are wholly redacted. Database UPDATE, DELETE and TRUNCATE triggers enforce append-only behavior; tests reset only their disposable database with triggers explicitly disabled inside the fixture. Owner/Admin audit read/export uses workspace scope, time/type/actor ID/action/status filters and timestamp/ID cursors. CSV protects formula-leading values and rejects exports over 10,000 rows rather than silently truncating.

## Changed files

- Backend: new `app/agent/{models,audit,service,router,llm,tools,worker}.py`, migration `e18d26760b88`, new agent/audit acceptance tests; shared provider transports, message actor/mention scheduling/serialization, typed events, lifespan/configuration and disposable-test isolation updated.
- Frontend: `components/agent.tsx`, `lib/agent.ts`, `/settings/agent` and `/settings/audit`, channel rendering/composer/live cache/panel, shell navigation, token-based styles, generated event contract, unit tests and two-session browser acceptance test.
- Infrastructure: Compose worker/test settings, CI fake-provider and browser-only auth-rate configuration, optional `infra/check_agent_providers.py`, reproducible `infra/measure_agent.py`.
- Documentation: ADRs 0012–0016, README, `.env.example`, event schema, this report, performance JSON and screenshots under `docs/screenshots/slice4/`. Dependency manifests/locks are unchanged. No secrets are committed.

## Validation actually run

| Command / workflow | Actual result |
|---|---|
| Backend `ruff check app migrations tests` | Passed |
| Backend `ruff format --check app migrations tests` | Passed, 56 files |
| Backend `pytest -q` | **78 passed**, 39.51 s; one existing Starlette/httpx TestClient deprecation warning |
| Backend `alembic upgrade head`; `alembic check` | Migrated; no new upgrade operations detected |
| Disposable-database migration tests | Empty database migrations and Slice 3 upgrade with existing private channel/message preservation passed |
| `backend/.venv/bin/python infra/export_events.py --check` | Passed; generated frontend/schema contract matches backend |
| Frontend `npm run lint`; `npm run typecheck` | Passed |
| Frontend `npm test` | **29 passed across 6 files** |
| Frontend `npm run build` | Passed, production routes generated |
| `CI=true PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | **6 passed**, 36.8 s; new two-session agent/steps/export/offline/390px/dark flow plus all existing flows |
| `python3 infra/cloud_build.py` | Backend Docker image rebuilt successfully with verified TLS |
| `AUTH_RATE_LIMIT=100 AGENT_FAKE_PROVIDER=true python3 infra/cloud_start.py` | PostgreSQL and backend healthy for deterministic browser validation |
| `AUTH_RATE_LIMIT=100 AGENT_FAKE_PROVIDER=true docker compose up -d --no-build --wait` (writable DOCKER_CONFIG) | Existing Compose startup passed with healthy services |
| `backend/.venv/bin/python infra/check_agent_providers.py` | Groq/Gemini both **skipped_no_key**; no live result claimed |
| `backend/.venv/bin/python infra/measure_agent.py --origin http://localhost:3000` | Five synthetic two-user fake-provider runs; results below |
| `node infra/dev.mjs --cloud --no-open --skip-install` | Passed: backend healthy, project identity checked, login/API ready; normal dev server running with fake mode off |
| `git diff --check` | Passed |
| `git push -u origin slice-4-agent`; read-only `git ls-remote` | Branch pushed and remote SHA confirmed |
| `gh run list --branch slice-4-agent …` | **Blocked**: environment proxy rejects CONNECT to api.github.com with HTTP 403; hosted CI is unverified |

Initial browser attempts exposed an ambiguous summary selector and the shared-proxy signup rate budget; both were corrected in the harness/CI setup. A run launched during backend recreation encountered connection resets; a health-gated rerun passed. No assertions were disabled. Browser-only auth budget is explicit; the application default stays 10.

Backend implementation commit: `5e4d701`; frontend commit: `ade999e`; final edit/protocol/filter coverage: `7edcbc7`. Final documentation/validation follows as a separate commit. The branch is pushed and is not merged into v1. GitHub Actions is configured to run this branch, but its conclusion is not observable here. Internet settings currently omit api.github.com; a narrow domain addition was saved in the cloud environment draft, preserving the existing package-manager preset and setup/start instructions. Apply that network setting before retrying hosted CI verification. No new GitHub secret was requested: existing Git proxy authentication successfully pushed the branch.

The final normal launcher restored fake mode **off** and the default auth budget. Provider keys remain absent, so real agent mentions correctly report unavailable until secure credentials and required provider destinations are configured. Synthetic test workspaces/accounts remain in the development database; production data was not used.

## Measured latency

Five real HTTP mentions by a Viewer, observed on a second user's WebSocket through Next.js, with the explicit deterministic fake provider. This measures queue/orchestration/transport overhead, not inference latency. [Machine-readable results](agent-performance.json):

| Observation | Median | p95 |
|---|---:|---:|
| Mention → first agent.step | 241.58 ms | 309.78 ms |
| Mention → final agent message | 255.33 ms | 325.93 ms |

No real-provider timing is claimed. The optional live check reported `skipped_no_key` for Groq and Gemini. The fake never silently substitutes for a missing credential.

## Screenshots

Captured by Chromium against the actual running app with synthetic accounts and the explicit fake provider:

- [Channel with answer and expanded steps](screenshots/slice4/agent-channel.png)
- [Agent settings](screenshots/slice4/agent-settings.png)
- [Audit log](screenshots/slice4/agent-audit.png)
- [390px channel](screenshots/slice4/agent-mobile.png)
- [390px Agent panel](screenshots/slice4/agent-mobile-panel.png)
- [390px dark channel](screenshots/slice4/agent-mobile-dark.png)

## Limits, risks and open questions

- Real Groq/Gemini generation, quota and structured-output compatibility remain unverified without keys; the startup status and optional synthetic live script make this explicit. DeepSeek/OpenAI workspace opt-in is permission-tested, not live-provider-tested. SDK token totals cannot account for failed upstream attempts lacking usage metadata.
- Prompt boundaries and registry/permission enforcement prevent tool privilege escalation, but do not guarantee factual prose or semantic immunity to injection. Output is safe-rendered. The deterministic write-refusal heuristic covers common English wording; all other phrasing still encounters a read-only registry.
- One backend process is required for existing live presence/fan-out. A cancelled orchestration may leave a provider thread running until its bounded SDK timeout; it cannot publish late results. Queue fairness under continuous load and a distributed worker are later scale work.
- Audit immutability protects normal application operations, not a database owner who can drop triggers. Retention, trusted administrative erasure and workspace deletion policy need a dedicated design. No mutation/approval workflow exists yet.
- Source context is conservative: other private channels are excluded from shared answers. Confirm any future private-to-public sharing UX before broadening this rule.
- Chromium desktop and emulated 390px mobile were tested. Physical devices, Windows/Docker Desktop execution and a real mobile keyboard were not available. The design-canvas URL could not be fetched; visual implementation/review uses UI_SPEC tokens, documented screen requirements and existing components. No pixel-perfect comparison with the external canvas is claimed.
- No proposals, approval actions, documents, memory, embeddings, notifications, integrations or agent code execution were added. The approval-rules display is read-only with a future-release note.

Proposed next step: **Slice 5 — proposals and the approval workflow**, after hosted Slice 4 CI is verified and this branch is reviewed/merged into v1. Preserve this slice's requester/audience checks and immutable audit when adding carefully authorized mutation tools.
