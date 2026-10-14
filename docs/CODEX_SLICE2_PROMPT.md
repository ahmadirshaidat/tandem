# Codex Prompt - Slice 2: Real-time Channels and Messaging

Paste everything below the line into Codex (Local task, in the cloned `tandem-workspace-v1` folder, branch `v1`).

---

You are a Principal Software Architect and Senior Full-Stack Engineer continuing the Tandem project. Slice 0 (foundation) and Slice 1 (authentication and workspaces) are done. Your task is **Slice 2: real-time channels and messaging**, and nothing beyond it.

## Read first
1. `docs/PRD.md` (especially sections 3, 5, 6, 7, 11, 12 and 14) and `docs/UI_SPEC.md`.
2. `README.md`, the existing ADRs in `docs/adr/`, and the current backend and frontend code. Follow the existing patterns (module layout, error format, authorization dependency, CSRF handling, logging, test fixtures). Do not refactor unrelated code.
3. Use the design canvas screens listed in PRD section 14 as the visual reference: channel view, thread, no-access, and the mobile channel and thread screens. Match tokens, components and motion from `UI_SPEC.md`.

## Hard boundaries
- Do **not** touch or extend the "Try AI" provider-trial feature, and do **not** connect any LLM to channels. `@Agent` in this slice is only a parsed and stored mention (see below). No agent replies, tools, proposals, memory or RAG.
- Do not build tasks, boards, documents, notifications, search, reactions, direct messages, or billing.
- Keep Redis out unless you can justify it in an ADR; single backend instance is the target, but isolate the event fan-out behind an interface so Redis pub/sub can replace it later.

## Decisions for this slice (state any disagreement in your plan, do not silently change them)
- **Roles in channels:** Owner/Admin and Editor/Developer can create public channels and post; Viewers can read and post messages and replies (so they can ask questions) but cannot create or edit channels or manage members.
- **Channels** belong to the Workspace and may later link to a Project (add a nullable `project_id` column without a foreign key target yet, documented in the ADR).
- **Private channels:** visible only to their members. Owner/Admin can manage membership. Non-members never see the channel in lists, counts, search results, WebSocket events or error messages that confirm it exists.
- **Default channel:** every new workspace gets `general` (public); all members auto-join public channels they can see.

## Scope

### Backend
1. **Data model and migrations** (all tables carry `workspace_id` with foreign keys, indexes, constraints):
   - `channels` (name unique per workspace, topic, `is_private`, `last_seq` counter, archived flag), `channel_members`.
   - `messages` (channel_id, author_id, body, `seq` per channel, `thread_root_id` nullable for replies, `client_message_id` for idempotency unique per channel and author, `edited_at`, `deleted_at` soft delete), `message_mentions` (user mention or agent mention), `attachments` (message_id nullable until sent, storage key, content type, size, dimensions), `channel_read_state` (last read seq per user and channel).
2. **REST API** (CSRF-protected, role-checked server-side on every endpoint): list/create/update/archive channels; join/leave public channels; manage private channel members; paginated history (cursor by `seq`, newest first); send message (idempotent via `client_message_id`); edit and delete own messages (Admin can delete any); thread replies and thread fetch; mark channel read; unread and mention counts per channel.
3. **Mentions:** parse `@name` and `@Agent` on the server, store them, return them in message payloads. The agent mention only sets a flag (`mentions_agent`).
4. **Attachments (images only):** PNG, JPEG, WebP, GIF; max 5 MB each, max 4 per message. Validate by magic bytes, not by the client's content type; reject SVG and everything else. Store with random keys behind a storage interface (local volume for dev, S3-compatible later). Serve only through an authenticated endpoint that re-checks channel access, with `X-Content-Type-Options: nosniff` and safe headers. Never serve from a guessable public URL.
5. **WebSocket gateway:**
   - Authenticate with the existing session cookie; check `Origin`; reject unauthenticated or cross-origin connections.
   - Subscribe per workspace and per channel; **re-check authorization on every subscribe** and when membership, role or session changes (remove the user from the topic or close the socket).
   - Event contract (document it in an ADR and a typed schema shared with the frontend): `message.created`, `message.updated`, `message.deleted`, `thread.reply_created`, `channel.created`, `channel.updated`, `channel.archived`, `member.joined`, `member.left`, `presence.update`, `typing.start`, `typing.stop`, `read.updated`, `error`.
   - **Reconnect with catch-up:** the client sends its last seen `seq` per active channel; the server replays exactly the missed events in order with no duplicates. Heartbeat/ping, server-side idle timeout, per-connection rate limiting and a message size limit.
   - Presence and typing are ephemeral (not stored). Typing events expire automatically.
6. **Limits and safety:** message length 4,000 characters, per-user send rate limit, per-IP and per-user connection limits, structured logs without message bodies, consistent API errors. Escape and sanitize everything rendered; support a small safe Markdown subset (bold, italic, inline code, code block, links) rendered without raw HTML.

### Frontend (match the design canvas and `UI_SPEC.md`)
1. Sidebar channel list with unread and mention badges, public/private icons, create-channel dialog.
2. Channel view: header, message list with date dividers and grouped messages, image attachments with a lightbox, composer with attach, `@` autocomplete (members and Agent), Enter to send, optimistic send with a clear failed/retry state, typing indicator, presence dots, "Agent not connected yet" tooltip on the Agent chip.
3. Thread panel (web) and thread screen (mobile) with replies and a reply composer.
4. No-access and empty states from the canvas. Disabled "Board" and "Docs" tabs (not built yet) must not look broken: show them disabled with a short "Coming soon" label or omit them.
5. Mobile layout at 390 px: latest message pinned above the composer, safe-area padding, 16 px inputs, 44 px touch targets, bottom tab bar as in the canvas.
6. **Offline behavior (PRD section 5):** channels and recent messages stay readable offline from a local cache of the last sync; the composer shows an "You are offline" state, keeps the draft, and does not queue sends. Reconnect resumes with catch-up.
7. Accessibility: `aria-live="polite"` for incoming messages, keyboard navigation, visible focus, correct roles. Light and dark themes via the existing tokens.

## Acceptance criteria (verify by running tests; report real results)
- `docker compose up` and the existing launcher still work; migrations apply cleanly from an empty database and upgrade an existing one.
- Two logged-in users in a browser see each other's messages, replies, typing indicators and presence in real time.
- **Reconnect test:** drop user A's socket, user B sends 3 messages and edits one, A reconnects and sees exactly the missed changes, in order, without duplicates.
- **Idempotency test:** retrying a send with the same `client_message_id` creates one message.
- **Isolation tests:** a user in workspace A can never read, subscribe to, or receive events for workspace B; a non-member can never learn a private channel exists (list, REST, WebSocket, attachment URL, error text).
- **Authorization tests:** Viewer cannot create channels or manage members; removing a member from a private channel or workspace immediately stops their live events; revoking a session closes its socket.
- **Attachment tests:** an executable or SVG renamed to `.png` is rejected; oversize is rejected; an attachment URL is inaccessible without channel access.
- **XSS test:** message bodies containing HTML or script render as text.
- **Mention tests:** `@Agent` and `@member` are parsed and stored; no agent behavior is triggered.
- **Performance check:** measure and report local p95 message delivery latency for two clients (target under 300 ms) and channel history load.
- Backend lint, format, tests and `alembic check` pass; frontend lint, typecheck, unit tests, build and Playwright tests pass, including a 390 px mobile run and a two-session real-time test. CI is green.

## Working rules
1. Inspect the repo and present a concise plan (including any disagreement with the decisions above) before coding.
2. Work on a new branch `slice-2-channels` from `v1`, commit in logical steps, and keep the app runnable at every step.
3. Implement incrementally: data model, REST, WebSocket, attachments, frontend, offline, tests. Run the relevant tests after each part and fix failures before moving on.
4. Write ADRs in `docs/adr/` for: WebSocket transport and event contract, message ordering and catch-up (`seq`), attachment storage and serving, and the event fan-out interface.
5. Update `README.md` with new commands, environment variables and limits. Document every new setting in `.env.example`.
6. Never fabricate test results or claim a feature works without running it. If you cannot verify something (for example a real device), say so.

## Final report (required)
Summarize: files added and changed, features completed, the commands you ran with their actual results, measured latency numbers, known gaps and risks, open questions, and the proposed next step (Slice 3: projects and tasks).
