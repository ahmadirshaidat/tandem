# Codex Prompt - Slice 3: Projects and Tasks

Run this only after Slice 2 has been verified (see the checklist in the chat), CI is green on `slice-2-channels`, and that branch is merged into `v1`. Then paste everything below the line into Codex (Local task, repository folder, branch `v1`).

---

You are a Principal Software Architect and Senior Full-Stack Engineer continuing the Tandem project. Slices 0 to 2 are done (foundation, authentication and workspaces, real-time channels and messaging). Your task is **Slice 3: projects and tasks**, and nothing beyond it.

## Read first
1. `docs/PRD.md` (sections 3, 4, 5, 6, 7, 11, 12 and 14) and `docs/UI_SPEC.md`.
2. `README.md`, `docs/adr/`, `docs/SLICE2_REPORT.md`, and the existing code. Reuse the existing patterns: module layout, authorization dependency, CSRF, error format, the WebSocket gateway and its event contract and catch-up mechanism, test fixtures. Do not refactor unrelated code.
3. Visual reference (design canvas, PRD section 14): "Task board with task detail", "Task table", "Mobile board", and the Projects section of the sidebar. Match tokens, components and motion from `UI_SPEC.md`.

## Hard boundaries
- Do not touch the "Try AI" feature. No agent behavior, proposals, approvals, memory or RAG. The `created_by_agent` flag exists on tasks (default false) and is only displayed.
- Do not build documents, notifications, search, subtasks, milestones, timeline views, integrations or billing.

## Decisions for this slice (state any disagreement in your plan; do not silently change them)
- **Projects** belong to a Workspace and are visible to all its members. Fields: name, short key (for example `WEB`), color, description, archived flag.
- **Task numbering:** every task gets an immutable key `BUG-n` or `TASK-n` from a per-workspace counter assigned in the same transaction as creation (no duplicates under concurrency).
- **Fields:** title, description (safe Markdown subset), type (`bug`, `task`), status (`todo`, `in_progress`, `done`), priority (`P1 High`, `P2 Medium`, `P3 Low`), assignee (nullable), reporter, due date (nullable), `created_by_agent`, `version` (integer for optimistic concurrency), manual order within a status column.
- **Roles:** Viewer reads only. Editor/Developer creates, edits, moves, assigns, comments. Owner/Admin additionally deletes tasks and manages projects. (Later, when the agent proposes changes, reassigning, changing priority and deleting are high-risk and need an Admin. Human edits by Editors stay allowed.)
- **Channel to project link:** the nullable `project_id` on channels (added in Slice 2) becomes a real foreign key; Owner/Admin can link a channel to a project.

## Scope

### Backend
1. **Data model and migrations** (every table carries `workspace_id`, with foreign keys, indexes, constraints): `projects`, `tasks`, `task_comments`, `task_activity` (created, status changed, assignee changed, priority changed, due date changed, commented, linked, edited), and a generic `links` table (`workspace_id`, `source_type`, `source_id`, `target_type`, `target_id`, created_by) that can connect messages, tasks and, later, documents.
2. **REST API** (CSRF-protected, role-checked server-side on every endpoint): CRUD for projects; CRUD for tasks with filtering (status, assignee, priority, type, text), sorting and cursor pagination; move a task (status and position) in one call; comments (create, edit own, delete own, Admin deletes any); activity feed per task; create and list links; "create task from message" which creates the task and a link to the source message.
3. **Optimistic concurrency:** updates carry the expected `version`; a mismatch returns `409` with the current server state. Concurrent moves of the same card resolve deterministically.
4. **Ordering:** choose a reordering approach that does not rewrite whole columns on every move (for example fractional ranks with periodic rebalancing) and record the choice in an ADR.
5. **Real-time:** reuse the existing WebSocket gateway. Add events `task.created`, `task.updated`, `task.moved`, `task.deleted`, `task.comment_created`, `project.updated`. Authorize subscriptions per workspace and re-check on role or membership change. Reconnect catch-up must return exactly the missed task events, in order, without duplicates.
6. **Activity integrity:** every change to a task writes an activity record in the same transaction (actor, timestamp, field, old and new value).
7. **Performance:** a board with 1,000 tasks must load in under 1 second locally; paginate or virtualize as needed. Provide a seed command that creates 1,000 synthetic tasks for measuring.

### Frontend (match the design canvas and `UI_SPEC.md`)
1. Sidebar Projects section with a project switcher, create-project dialog, minimal project settings (rename, key, color, archive, linked channels).
2. **Board view:** three columns (To do, In progress, Done) with task cards (ID, title, priority chip, due date, comment count, assignee, agent badge when applicable), drag and drop, and a keyboard-accessible alternative (a "Move to" menu on each card). Real-time updates without page reload.
3. **Table view:** sortable columns, filters, grouping by status, selection with a bulk bar (bulk status and assignee changes for Editors and Admins).
4. **Task detail panel** (side panel on web, full screen on mobile): editable fields, linked items (conversation, other tasks), activity timeline, comments with composer.
5. **New task dialog**, and a "Create task from message" action in the channel message menu that opens the dialog prefilled and links the message. The task's "Conversation in # channel" link deep-links back to that message.
6. **Conflict handling:** on `409`, show a clear "This task changed" state with "Keep mine" and "Take server's" choices.
7. **Mobile (390 px):** status tabs with counts, card list, floating "New task" button, bottom sheet for quick actions, safe-area padding, 44 px touch targets.
8. **Offline (PRD section 5):** board, table and task details stay readable offline from the last sync; edits are disabled with a clear "You are offline" notice (no offline writes in the MVP).
9. Accessibility: keyboard navigation across board and table, `aria-live` for remote changes, visible focus, correct roles, light and dark themes via existing tokens.

## Acceptance criteria (verify by running tests; report real results)
- Existing launcher, `docker compose up`, migrations (empty and upgrade paths) still work.
- Two users see each other's task creates, edits, moves and comments in real time.
- **Concurrency tests:** simultaneous creation produces unique, gapless-or-documented task numbers; two simultaneous edits with the same `version` produce one success and one `409`; two simultaneous moves of one card leave a consistent order.
- **Reconnect test:** a client offline for several task events recovers exactly the missed events in order, no duplicates.
- **Isolation and role tests:** no cross-workspace read, write or event leakage; Viewer cannot create, edit, move, comment or delete; Editor cannot delete tasks or manage projects; link creation cannot connect objects from different workspaces.
- **Activity test:** every field change produces an activity entry with correct actor and values.
- **Link test:** "create task from message" creates the task and link, and the deep link returns to the message; a user who cannot access the channel cannot follow the link or learn the message exists.
- **Performance check:** report the measured load time with 1,000 tasks and the p95 delivery latency of task events.
- Backend lint, format, tests and `alembic check` pass; frontend lint, typecheck, unit tests, build and Playwright tests pass, including a 390 px mobile run, a two-session real-time board test, and a conflict test. CI is green (verify it on GitHub and say so honestly if you cannot).

## Working rules
1. Inspect the repo and present a concise plan (including disagreements with the decisions above) before coding.
2. Create branch `slice-3-tasks` from `v1`, commit in logical steps, keep the app runnable throughout.
3. Implement incrementally: data model, REST, real-time, frontend board, table, detail, mobile, offline, tests. Run relevant tests after each part and fix failures before continuing.
4. ADRs in `docs/adr/` for: task numbering, ordering strategy, the `links` model, optimistic concurrency and conflict handling.
5. Update `README.md` and `.env.example` for any new commands or settings.
6. Never fabricate results. Say plainly what you could not verify (real devices, CI, anything not run).

## Final report (required, in `docs/SLICE3_REPORT.md` and summarized in your final message)
Files added and changed, features completed, commands run with actual results, measured performance numbers, screenshots of board, table, task detail and mobile, known gaps and risks, open questions, and the proposed next step (Slice 4: shared agent with read-only tools, audit log and the first connection to channels).