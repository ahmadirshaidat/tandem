# Slice 5: proposals and human approval

Implemented on `slice-5-approvals` from `v1` at `9ff712f570391e4344f13201db30165ae923f784`. Slice 4 was fast-forwarded into `v1` after its hosted [CI run 38739692568](https://github.com/ahmadirshaidat/tandem/actions/runs/38739692568) was verified successful. Slice 5 remains on its review branch. No real provider credentials were available: **live checks skipped**. This is a remaining gate before claiming real-model readiness or proceeding to Slice 6.

## Completed behavior

- The closed agent registry contains the existing nine read tools and exactly six `propose_*` tools. The latter persist proposal/item records only. Direct task/comment mutations and approval are absent from the registry; unknown and malicious calls fail without domain changes. Try AI remains isolated.
- Proposal kinds are create tasks, update title/description/status/due date, reassign, change priority, delete and add comment. Strict schemas, size bounds, ten-item cap, channel pending cap, open-task duplicate checks, destination-safe sources and requester authorization apply before storage. Planning supports a DAG of dependencies between new tasks.
- Human approve/reject/edit-approve/cancel endpoints require CSRF and current workspace/channel access. Approval verifies the displayed proposal version and SHA-256 payload hash, including recomputing the stored hash, before execution. Editing can change/remove existing items but cannot redirect an existing-task proposal or silently rebase its target version.
- Low-risk creation, field edits and comments require Editor/Admin/Owner. Reassignment, priority and deletion require Admin/Owner. Viewers can ask and cancel their own request but cannot approve. Admin/Owner may tighten creation to Admin only; high-risk rules cannot be loosened. The server reads current rules when deciding.
- Workspace/proposal locks and operation keys serialize decisions. An exact successful same-user/key retry returns the existing result; other terminal decisions conflict. Domain work reuses human task services inside a savepoint and one enclosing transaction. A failing item rolls back every task/comment/link change while retaining the failed approval lifecycle. Target changes produce Stale. Expiry defaults to seven days and runs in the existing worker, with an additional decision-time check.
- Created tasks are marked `created_by_agent`; activity identifies Agent as proposer and the approving human. Directional `depends_on` links use the existing links table. Every proposal transition, edit, execution and rule change is audited. Cancellation uses Rejected plus `proposal.cancelled`, preserving the requested state vocabulary. Approved and Completed have separate audit/journal records within one committed transaction.
- Generated events add `proposal.created`, `proposal.updated` and `proposal.executed`, using existing authorized replay. Frontend merging deduplicates IDs and never regresses versions. Inbox/channel deep links fetch older proposal/trigger records when needed and open reply threads.
- Inline cards render the stored payload, named properties, source chips, risk, approval role, human attribution and result links. The review dialog/sheet edits fields and removes items before atomic approval. The Agent panel lists real pending proposals; Inbox lists actionable approvals, with Mentions/Assigned disabled. Settings exposes approval rules. Offline decisions are disabled and never queued. User text uses `dir="auto"`; Arabic, dark theme, keyboard controls, state announcements and 390px layouts use existing components/tokens.

## Files added and changed

| Area | Files |
|---|---|
| Proposal backend | New `backend/app/proposals/{models,schemas,service,router}.py` and package initializer; migration `3073fbdfd371`; migration registration in `backend/migrations/env.py` |
| Agent integration | `backend/app/agent/{llm,models,tools,worker}.py`, `backend/app/{main.py,core/config.py,channels/schemas.py}` |
| Shared domain services | `backend/app/tasks/{models,schemas,service,router}.py`; comment/delete operations extracted for reuse; dependency relation and agent-created flag added |
| Frontend | New `components/proposals.tsx`, `lib/proposals.ts`, `/inbox/page.tsx`; updates to agent panel/settings, channel rendering/events/deep links, shell/navigation, task detail/dialog/list, safe Markdown and global styles |
| Contract | `infra/export_events.py`, `docs/channel-events.schema.json`, `frontend/src/lib/events.generated.ts`; JSON maps generate `Record<string, unknown>` |
| Tests | New `backend/tests/test_proposals.py`, `test_proposal_schema.py`, `frontend/tests/proposals.test.tsx`, `frontend/e2e/proposals.spec.ts`; existing agent tests updated for proposal-only behavior |
| Runtime/checks | `.env.example`, `compose.yaml`, `.github/workflows/ci.yml`; new `infra/check_approval_live.py` and `infra/measure_proposals.py` |
| Documentation | README; ADRs [0017 state](adr/0017-proposal-state.md), [0018 integrity](adr/0018-approval-integrity.md), [0019 execution](adr/0019-approval-execution.md), [0020 risk/rules](adr/0020-approval-risk-rules.md); this report, timing JSON and screenshots |

Dependency manifests and lockfiles are unchanged. No provider keys are committed. Local configuration and synthetic test data stay private/ignored.

## Validation actually run

Commands use `backend/.venv` from the repository root, or `.venv` when run inside `backend`. Frontend commands run inside `frontend`.

| Command / workflow | Actual result |
|---|---|
| Backend `.venv/bin/ruff check app migrations tests` | Passed |
| Backend `.venv/bin/ruff format --check app migrations tests` | Passed, 64 files |
| Backend `.venv/bin/pytest -q` | **95 passed**, 51.52 s; one existing Starlette/httpx TestClient deprecation warning |
| Backend `.venv/bin/alembic check` | No new upgrade operations detected |
| Disposable migration tests | Empty database and Slice 4 downgrade/upgrade preserve existing private channel/message; proposal constraints verified |
| `backend/.venv/bin/python infra/export_events.py --check` | Passed |
| `ruff check` / `ruff format --check --config backend/pyproject.toml` for the new helpers/exporter | Passed |
| Frontend `npm run lint`; `npm run typecheck` | Passed |
| Frontend `npm test` | **32 passed across 7 files** |
| Frontend `npm run build` | Passed, including Inbox production route |
| `CI=true PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | **7 passed**, 44.9 s; production frontend, all previous slices plus proposals |
| `python3 infra/cloud_build.py` | Backend image built successfully with verified TLS |
| `AUTH_RATE_LIMIT=100 AGENT_FAKE_PROVIDER=true python3 infra/cloud_start.py` | Healthy backend/PostgreSQL for deterministic browser tests |
| `DOCKER_CONFIG=/workspace/tandem/.local/docker AGENT_FAKE_PROVIDER=false AUTH_RATE_LIMIT=10 docker compose up -d --no-build --wait` | Passed; PostgreSQL and backend healthy |
| `node infra/dev.mjs --cloud --no-open --skip-install` with fake off/default auth budget | Passed; healthy services, project identity verified, login/API ready, dev frontend started |
| `backend/.venv/bin/python infra/check_agent_providers.py` | Groq and Gemini both `skipped_no_key` |
| `backend/.venv/bin/python infra/check_approval_live.py --provider groq` and `--provider gemini` | Both **live checks skipped**, reason `no_key`; no external call or approval attempted |
| `backend/.venv/bin/python infra/measure_proposals.py --origin http://localhost:3000` | Five synthetic fake-provider samples, two actual users and real WebSocket delivery; results below |
| `git diff --check`; logical commits followed by pushes | Passed; branch pushed after each commit |

The 16 proposal-specific backend tests exercise every kind, roles/current rules, workspace/private-channel/source isolation, malicious/unknown tools, absence of unapproved changes, CSRF, stored/displayed hash tampering, version checks, edited/removed items, target redirection denial, due dates, dependencies/cycles, caps/duplicates, concurrent decisions, successful retry, multi-item rollback, stale/expired/cancelled transitions, audit attribution and live/replayed events. Existing append-only audit and injection tests still pass.

The two-user browser flow requests a three-task JWT plan, verifies zero tasks before approval, edits a title/removes an item, approves two tasks, observes both users' updates, checks actionable Inbox and locked rules, denies Editor high-risk controls, rejects a high-risk proposal, tests Arabic direction, a mobile review sheet/offline controls/dark mode, reload deduplication and a proposal deep link into a reply thread. The task board used for timing belongs to the requester, a different user from the approver.

## Hosted CI

Hosted [run 38757364335](https://github.com/ahmadirshaidat/tandem/actions/runs/38757364335) was verified **successful** on final implementation commit `357328ac964060e1f89e7c539572f584d9c5ba04`, including the added integrity/deep-link tests, lint, backend tests, schema check, frontend checks/build and browser tests. The preceding [run 38751987711](https://github.com/ahmadirshaidat/tandem/actions/runs/38751987711) was also successful. The report/screenshots/README follow in a separate evidence commit.

Two earlier failures were repaired without removing behavior assertions: run #15 rejected generated `{}` TypeScript types, so JSON dictionaries now generate map types in the exporter; run #16 still expected the Slice 4 fake answer to say `read-only`, so the test now expects `human approval`. The closed registry and no-direct-mutation tests remain enforced. Neither old failure describes the later green run. Browser tests use fake mode explicitly and raise the auth budget only in their test backend; normal runtime defaults remain fake off and auth limit 10.

## Measured latency — fake provider only

Five synthetic Viewer mentions were observed through Next.js; an independent Owner approved, and the Viewer's WebSocket received the task. The helper soft-deletes its generated tasks between samples to avoid duplicate-title rejection. [Machine-readable samples summary](proposal-performance.json):

| Observation | Median | p95 |
|---|---:|---:|
| Mention HTTP start → `proposal.created` on requester WebSocket | 250.17 ms | 597.38 ms |
| Human approval HTTP start → task event on second user WebSocket | 61.15 ms | 88.27 ms |

The final Playwright run separately measured an actual approval button click to a visible task on the second user's board: **211 ms**, with the task WebSocket event at **155 ms**. Mention-to-visible-proposal was **1,089 ms**, including browser interaction/waits. [Browser measurement](proposal-browser-performance.json). These are local observations with five helper samples and one browser timing, not a load test or production SLA. The local under-500 ms approval target was met.

These figures measure queue/orchestration, persistence, rendering and transport with a deterministic fake. They are **not AI inference latency**. Slice 4's 255 ms figure was also fake-provider overhead. Real-model structured-output behavior, latency and cost remain unverified.

## Live provider gate

Neither the running environment, the private local configuration, nor the saved environment bindings contained usable Groq/Gemini credentials. Both optional checks explicitly skipped. No real model name/result/latency is claimed. Missing credentials never silently enable a fake in normal runtime.

Fresh keys must be supplied securely in local `.env` or environment settings and the backend restarted with fake mode off. Run the structured-provider checker, then `check_approval_live.py` for each provider. The latter uses a new synthetic workspace and its human test owner to mention → inspect proposal → approve, checks zero tasks before approval, and prints only safe status/model/count/timing metadata. Its live HTTP approval path is present but **unexecuted** in this task. Provider access domains and secret requirements are saved in the environment draft; values and publication remain outstanding.

## Screenshots

Captured from the actual application with synthetic users/data, under [screenshots/slice5/](screenshots/slice5/):

| Screen | Artifact |
|---|---|
| Proposed multi-item card and pending Agent panel | [proposal-multi.png](screenshots/slice5/proposal-multi.png) |
| Completed proposal | [proposal-completed.png](screenshots/slice5/proposal-completed.png) |
| Rejected proposal | [proposal-rejected.png](screenshots/slice5/proposal-rejected.png) |
| Editor sees Admin-only high-risk message | [proposal-admin-only.png](screenshots/slice5/proposal-admin-only.png) |
| Arabic proposal | [proposal-arabic.png](screenshots/slice5/proposal-arabic.png) |
| 390px review sheet | [proposal-mobile-sheet.png](screenshots/slice5/proposal-mobile-sheet.png) |
| Mobile light/dark | [proposal-mobile.png](screenshots/slice5/proposal-mobile.png), [proposal-mobile-dark.png](screenshots/slice5/proposal-mobile-dark.png) |
| Actionable Inbox | [approvals-inbox.png](screenshots/slice5/approvals-inbox.png) |
| Approval rules | [approval-rules.png](screenshots/slice5/approval-rules.png) |

The external design canvas was unavailable. Implementation and visual inspection use `UI_SPEC.md` and existing components; no pixel-perfect canvas comparison is claimed. The screenshots cover Proposed, Completed and Rejected; Failed, Stale and Expired are covered by backend behavior tests and frontend status rendering, without dedicated screenshots.

## Remaining limits and next step

- Real Groq/Gemini structured proposals remain the main unverified integration. Resolve the live gate before Slice 6.
- Chromium desktop and emulated 390px mobile were tested. Physical mobile keyboards/devices and Windows/Docker Desktop execution were unavailable. The existing cloud launcher was exercised; no public deployment was performed.
- Existing single-backend-process live fan-out/presence limits still apply. Timings are local and small-sample. Synthetic accounts/workspaces remain in the development database.
- Audit append-only triggers protect application writes, not a database owner who can remove triggers. Administrative erasure/retention policy remains a future design question.
- Cancellation maps to Rejected with a cancellation audit action; approval and execution commit together, so Approved may appear only briefly during journal replay. These choices are documented in ADR 0017/0019.
- No memory/RAG, documents, notifications, integrations or code execution were added. Proposed next work is **Slice 6: memory and RAG**, after review/merge and genuine provider verification; preserve the requester/audience boundary and human-only execution.

## Final runtime and source verification

Plain Compose startup and the existing cloud launcher both passed. Backend health returned HTTP 200 with `status=ok`, `database=connected`, `vector=true`. Frontend login returned HTTP 200 with `X-Tandem-Project=tandem-workspace-v1`; proxied CSRF returned HTTP 200. The running container confirms fake mode **false**, auth limit **10**, expiry **7 days**, pending cap **20**. The normal dev frontend remains running. Provider calls remain unavailable until keys are configured.

The setup skill's reusable install instructions were preserved; its startup draft was updated to explicitly enable fake mode only for browser tests and restore normal runtime afterward. This draft save is confirmed, but environment publication and a fresh-machine restore were not performed. GitHub API access worked for the hosted run verification. The remote `slice-5-approvals` implementation at `357328a` is green; `v1` remains at Slice 4. No Slice 5 merge or deployment was performed.
