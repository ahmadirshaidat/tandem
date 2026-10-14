# Slice 3 delivery report

## Scope and branch gate

Projects and human-managed tasks are implemented on `slice-3-tasks`. Before starting, Slice 2's browser CI failure was reproduced with a cold development server (`ERR_INTERNET_DISCONNECTED` at offline reload). Playwright now starts the production build. GitHub run [38622491096](https://github.com/ahmadirshaidat/tandem/actions/runs/38622491096) passed on `1a8265cf3bd8bd903c3bed7d2950d02cff9a5c5f`; `v1` was fast-forwarded to that verified commit, then Slice 3 was branched from it.

The remaining `actions/upload-artifact@v4` Node.js 20 warning is addressed with official release v7.0.2, pinned to `cf430e030ddbb5b0abf93d22962f4752f3646cd9`. The release tag and its `action.yml` were checked on GitHub: the action uses Node.js 24. Existing checkout/setup-node/setup-uv actions already use Node.js 24. Slice 3 was added to the workflow's branch triggers.

## Completed behavior

- Workspace-visible projects with name, key, color, description and archive state; Owner/Admin management, channel linking and deletion of empty projects. The channel/project relation now has a real compound workspace foreign key.
- Immutable BUG-n/TASK-n keys from one transactional workspace counter. Creation, versioned edits/moves/deletion, assignment, priorities, nullable due dates, safe Markdown descriptions and a read-only created_by_agent flag.
- PostgreSQL fractional ranks: normal moves change one task; rare tiny gaps trigger an audited column rebalance. Concurrent creations receive unique consecutive numbers; stale edits/moves return 409 with the current authorized snapshot.
- Cursor-based task filters/sorting, atomic bulk changes, versioned comments with own-edit/own-or-Admin-delete permissions, and actor/time/old/new activity in the same transaction as each change.
- Workspace-scoped typed task/message links. Create-from-message is atomic. Both endpoints are authorized on every link read/write; hidden conversation links and their activity are filtered before pagination. Task events never contain private link endpoints or counts.
- The existing gateway/Fanout now carries a separate durable workspace task sequence. Reconnect delivers exactly missed ordered task events, alongside existing independent channel replay. Session/membership checks apply on reads and immediately before delivery; observed membership removal revokes subscriptions.
- Responsive board, table, status grouping, text/status/priority/type/assignee filters, sortable columns, selection and bulk status/assignee editing. Cards support drag-and-drop and keyboard/touch quick actions.
- Project navigation/switching/settings, new-task and message-to-task dialogs, a desktop side panel and mobile full-screen details, editable fields, comments, accessible links and activity. Source conversation links retrieve and focus even messages older than the initial 50-message page.
- Explicit Keep mine/Take server's conflict handling retains drafts. Previously synced board/table/details remain readable offline; task writes are disabled and never queued. Sign-out/account switch clears app cache; observed access revocation evicts task/link caches.
- 390 px status tabs/counts, filter chips, compact expandable filters, quick-action sheet and floating New task control, safe-area padding, shared light/dark tokens, visible focus and live announcements.

Try AI/provider adapters were not changed. This slice makes no LLM calls and adds no agent actions, documents, proposals, approvals, memory, RAG, notifications, search product, subtasks, milestones or billing. The task text filter is limited to loaded task records.

## Changed files

Backend additions: `backend/app/tasks/{models,schemas,service,router,seed}.py`, migration `4cf3fce3b278_workspace_projects_tasks_activity_links_.py`, and `backend/tests/test_tasks.py`. Integration changes are limited to channel/project constraints, authenticated single-message retrieval for deep links, the gateway/schema, application router/errors, Alembic model registration, membership unassignment and isolation tests.

Frontend additions: `/tasks`, `tasks-page.tsx`, `task-dialogs.tsx`, `task-detail.tsx`, `lib/tasks.ts`, `task-live.ts`, `online.ts`, task unit tests and Playwright acceptance flows. Shared changes add project/task navigation, optional non-modal detail dialogs, task theme styles, typed conflict details, channel project typing, message actions/deep links and visited task-shell caching. The generated live contract and JSON schema include typed task/project/comment payloads.

Documentation and tools: ADRs 0008–0011 (numbering, ordering, links, optimistic versions/replay), the supplied Slice 3 prompt, this report, screenshots, `task-performance.json`, `infra/measure_tasks.mjs`, README/local update instructions, `.env.example` comments and the CI workflow. No dependency declarations or lockfiles changed. No credentials were put in these files.

## Verification actually run

| Command/check | Result |
|---|---|
| Backend Ruff lint + format checks | Passed; 45 Python files formatted |
| `backend/.venv/bin/pytest -q backend/tests` | 62 passed; one existing Starlette/httpx deprecation warning |
| Fresh disposable test-database migration to head | Passed via backend fixture; development data never truncated |
| Existing development database upgrade from Slice 2 | Applied successfully; existing accounts/channels retained |
| `alembic check` | Passed: no new upgrade operations |
| `backend/.venv/bin/python infra/export_events.py --check` | Passed |
| Frontend `npm run lint`, `npm run typecheck` | Passed |
| Frontend `npm test` | 27 passed in 5 files |
| Frontend `npm run build` | Passed; static `/tasks` route included |
| `CI=true … npm run test:e2e`, no pre-existing frontend | 5 passed (15.5 s), including previous authentication/channel flows |
| Extended task flow with source message older than 50-message history | Passed separately (7.9 s) |
| Production Docker cloud build/start | Passed; database/backend healthy |
| Native-mode `node infra/dev.mjs --skip-install --skip-build --no-open` | Passed in a task-owned Linux fixture on 3001/8001/5433, using a freshly verified backend image and installed dependencies |
| Cloud launcher reuse, `--cloud --skip-install --skip-build --no-open` | Passed; existing project/API ready at localhost:3000/login |
| Native-mode browser, 390 px | Real signup/workspace and UI-created project/task passed; X-Tandem-Project was tandem-workspace-v1 |

The task tests verify concurrent numbering, concurrent edits/moves, activity values/actors, normal single-card reordering, rollback of invalid/bulk operations, roles, workspace isolation, private link filtering, channel/project scope, removal/unassignment, archive/deletion and read-only agent inputs. The live test checks ordered replay after missed edit/create/link events, privacy of event payloads, deduplication and membership revocation. Browser tests use two independent sessions for creates, edits, moves, assignment, comments, both conflict choices, reconnect, private-link Viewer behavior, keyboard/touch/drag flows, mobile/landscape, dark mode and offline reload of board/table/details.

The fixture needed a fixture-only Turbopack root setting because it borrowed installed node_modules through a symlink; normal npm-ci clones do not. Its private configuration was freshly generated, with no provider keys copied. Only its task-owned containers, volumes and files were cleaned after testing. Root cloud configuration stayed mode 0600. This is Linux validation, not execution on the user's Windows machine.

## Measured performance

One local Next production proxy and one backend instance with PostgreSQL. `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium node infra/measure_tasks.mjs http://localhost:3000` seeded a separate synthetic workspace through the documented backend command. The browser had a fresh context (cold browser asset cache); the application/server were running, with the board API warmed by the HTTP sample set. No provider requests occurred.

| Measurement | Result |
|---|---:|
| Tasks in snapshot | 1,000 |
| Initial rendered cards | 120 (40 per status) |
| Board HTTP p50 / p95, 20 reads | 61.88 / 82.49 ms |
| Navigation → initial board paint | 655.55 ms |
| Under-1-second board target | Met locally |
| HTTP edit → second-browser WebSocket p50 / p95, 30 edits | 34.01 / 67.42 ms |
| Maximum measured delivery | 153.71 ms |

Raw non-secret measurements are in [task-performance.json](task-performance.json). Numbers are observations on this machine, not internet/device capacity guarantees. Progressive card rendering and cursor pagination bound the initial DOM; Show more/Load more exposes remaining records.

## Screenshots

Actual synthetic data from browser acceptance and native-mode checks, using the uploaded board/table/mobile design's surfaces, spacing, tokens and panel structure. Agent/proposal content from the canvas is outside this slice.

- [Desktop board](screenshots/slice3/task-board.png)
- [Desktop table](screenshots/slice3/task-table.png)
- [Desktop task detail](screenshots/slice3/task-detail.png)
- [390 px mobile board](screenshots/slice3/task-mobile.png)
- [Native-mode localhost:3001 mobile](screenshots/slice3/localhost-3001-mobile.png)

## Remote CI

Slice 3 GitHub run [38630125874](https://github.com/ahmadirshaidat/tandem/actions/runs/38630125874), on `3a2122eaf7f982d8b05c7b2dfd62d790250deccc`, completed successfully. This includes backend integration, shared schema, frontend checks/build and all browser flows with the corrected production server. This report-only follow-up records the observed result; the latest documentation commit is also checked before delivery.

## Limits, risks and open questions

- Native Windows, physical mobile keyboards/devices, public hosting and fresh published-cloud restoration were not tested. This cloud task cannot launch a process on the user's PC. README gives the exact update/start commands for the already-cloned new folder; the older unrelated Tandem project is preserved.
- The board/table filter/sort the loaded snapshot. A page initially fetches at most 1,000 tasks; the UI explicitly reports remaining cursor pages. Manual placement is meaningful within a project/status; cross-project neighbors are rejected.
- Workspace writes are serialized for numbering, permissions, ordering and transaction integrity. The measured MVP target is met; high-write multi-worker deployments need future transport/locking/retention decisions. Journal retention, generic-link cleanup and full virtualization are future operations work.
- Offline devices cannot learn permission revocations until reconnecting. Browser storage can be disabled/full, limiting cached views; no task writes are queued. Private links are reauthorized online and evicted when revocation is observed.
- Project edits use last-write-wins; optimistic versions apply to tasks and comments. Human task fields remain editable by Editors; agent high-risk permission rules await a separate slice.
- Existing foundation email ownership/production SMTP and provider account availability remain earlier limitations. No live provider checks were performed here.

Next proposed work: **Slice 4**, scoped separately to a shared agent with read-only tools, audit logging and a first channel connection. Keep mutation proposals/approval rules explicit and test private-channel/workspace isolation before extending access. No Slice 4 work has begun.
