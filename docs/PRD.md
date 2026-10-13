# Product Requirements Document
## AI-Native Collaborative Workspace for Software Teams (working title)

**Status:** Draft v1. Every decision below was agreed section by section with the product owner.
**Audience:** the Codex coding agent and the product owner.
**How to use this document:** treat it as the source of truth. If something is ambiguous or missing, record it under "Open questions" and ask; do not invent scope. Anything marked *Proposed* is a default to be confirmed in the Architecture phase (as an ADR).

---

## 1. Vision and Problem

**Vision.** An AI-native collaboration workspace where software teams communicate, organize development work, and solve problems alongside one shared AI teammate that understands the whole project.

**Problem.** Dev teams juggle Discord, Notion, Jira, GitHub, and AI chatbots. Information is fragmented, decisions get lost, and AI assistants lack the shared context to collaborate effectively.

**Solution.** One workspace where conversations, bugs, tasks, specs, decisions, and AI help are connected in real time. It combines:
- Discord-style real-time channels and threads
- Notion-style documents and tables
- Linear/Jira-style task management (table + Kanban)
- Figma-style multiplayer presence and co-editing
- One shared, context-aware AI agent that is a first-class workspace member

**Differentiation.** This is not a project-management tool with a chatbot attached. The agent is a persistent team member: it participates in channels, links conversations to tasks, remembers decisions, and proposes actions while respecting permissions.

**MVP primary workflow:** Bug triage -> task assignment -> resolution tracking.
1. A developer reports a bug in a channel.
2. A member mentions `@Agent`; it reads the discussion and relevant memory, and identifies likely causes.
3. The agent posts a **Proposal** card (title, description, repro steps, priority, owner).
4. An authorized member approves, edits, or rejects it.
5. On approval the task appears in the shared task table and Kanban board, linked to the original discussion.
6. Developers discuss, assign, and update status; the agent summarizes decisions and progress.
7. On resolution, the agent records the solution in workspace memory. Similar future bugs retrieve it via RAG.

---

## 2. Users and Jobs-to-be-Done

**Target teams:** software teams of 3-15 people (startups, student teams, freelance squads). The architecture must allow growth to larger teams without a rewrite.

| Persona | Pain | Job to be done |
|---|---|---|
| **Tech Lead / PM (primary)** | Writing tickets by hand, tracking who does what, assembling progress reports | "When an important discussion happens, turn it into a clear plan and tasks with minimal effort while keeping control over every change." |
| **Developer** | Context switching between chat and task tool; lost decisions | "When I report a bug or pick up a task, understand the context fast and keep working without leaving this place." |
| **Workspace Admin** | Fear the AI sees or changes something it shouldn't | "Manage members and roles, and decide what the agent may do alone vs. with approval." |

The **Tech Lead** is the primary design persona: the approval experience must be fast and clear.

---

## 3. Core Concepts (shared vocabulary; use these names in code and schema)

- **Workspace** - the whole team; the isolation and permission boundary.
- **Project** - a software project inside a workspace; owns tasks and documents.
- **Channel** - a chat space (public or private). Belongs to the **Workspace** and is *optionally linked to a Project*.
- **Thread** - replies branching from a message.
- **Message** - a chat message (text, mentions, image attachments).
- **Task** - unit of work (status, priority, assignee, due date, comments, subtasks later). A **Bug** is a task type.
- **Board / Table** - Kanban view and table view over the same task data.
- **Document** - spec, ADR, meeting notes, postmortem; versioned; collaboratively edited.
- **Agent** - one shared AI member per workspace.
- **Proposal** - an action or plan the agent proposes. States: `proposed` -> `approved` -> `completed` (or `rejected`, `failed`).
- **Suggestion** - a proposed edit to a document, accepted or rejected by a human.
- **Memory** - searchable knowledge records with permission metadata, used for RAG.
- **Audit Event** - immutable record of every action (actor, time, arguments, result, approval status).

**Relationship rules**
- Everything belongs to exactly one Workspace (strict isolation).
- Messages, documents, and tasks can be linked to each other (polymorphic links).
- The agent can never read anything the requesting user cannot read.

---

## 4. User Journeys

1. **Bug to ticket (primary):** see section 1. Success: under 2 minutes from report to approved ticket.
2. **Feature planning:** e.g. "`@Agent` we need JWT authentication, help us plan." The agent reviews context, proposes a plan split into backend/frontend/testing tasks with dependencies and priorities, requests approval once for the whole set, creates approved tasks, then tracks progress.
3. **Document with Suggestions:** a developer writes a spec (even offline). The agent proposes improvements as Suggestions; the lead accepts or rejects them; every version is kept.
4. **Agent permissions (Admin):** sets roles, reviews which actions need approval, inspects the Audit Log.

**Approval UX (decided):** an approval card appears **inline in the channel** where the discussion happened, plus a "Waiting for your approval" list in the right panel.

---

## 5. MVP Requirements

### Must
**Collaboration**
- Authentication, workspaces, invitations, roles (Owner/Admin, Editor/Developer, Viewer)
- Public and private channels, real-time messaging, threads/replies, mentions (`@Agent` included), online presence, typing indicators
- Image attachments only (size limit + content-type validation + safe storage)

**Project management**
- Tasks with Bug type; table view and Kanban; assignment, priority, status, due date; comments; activity history
- Links between messages, documents, and tasks
- Every important update visible in real time to authorized members

**Collaborative documents (kept in the MVP by decision)**
- Types/templates: Spec, Meeting notes, ADR, Bug postmortem
- Tiptap editor + Yjs real-time co-editing with live cursors; Markdown shortcuts
- Autosave persisted **server-side**; version history (automatic snapshots + named versions + restore)
- `@` mentions of tasks, messages, documents; backlinks; "convert this conversation to a document"
- Document permissions inherit workspace/project roles; private documents supported
- Documents are chunked by headings and embedded in the background after each save
- The agent edits documents **only through Suggestions** (never direct writes); agent edits are attributed in version history

**Shared AI agent**
- One shared agent; read-only tools run automatically; Proposals and approval cards for mutations
- Clearly distinguishes proposed / approved / completed actions
- Persistent workspace memory with RAG (semantic search + metadata filtering)

**Platform**
- All critical state persisted server-side; Audit Log for every agent action; automated tests

### Offline behavior (decided)
- **Documents:** full offline reading and editing (Yjs + IndexedDB), automatic merge on reconnect.
- **Channels and tasks:** readable offline from a local cache of the last sync; **no offline writes** in the MVP.
- **Agent:** requires internet. If offline, show "Agent unavailable offline"; keep the message as a draft and do **not** auto-send on reconnect (context may have changed); the user presses "Send now".
- **Conflicts:** documents merge via Yjs. Tasks use a `version` field (optimistic concurrency) with a "keep mine / take server's" choice. If a user's permission is revoked while offline, the server rejects those changes and the client keeps a local copy under "Rejected changes" instead of losing them.

### Should (if time allows)
In-app notifications; searchable conversations; progress reports; sprint plan generation; blocker detection; document templates beyond the four; milestones; subtasks; non-image file types.

### Won't (out of MVP)
External integrations (GitHub etc.), code execution, multi-agent architecture, voice/video calls, SSO, billing, native mobile apps (responsive web only), offline writes for tasks/messages, local chat models, enterprise features.


*Billing, payments and the public marketing site are fully designed (see section 14) but are built after the MVP, as slice 9. Authentication pages are part of slice 1.*
---

## 6. Non-Functional Requirements (initial targets, adjustable)

**Performance:** message delivery p95 < 300 ms; board with 1,000 tasks loads < 1 s; first agent response < 3 s; document sync between users < 500 ms.

**Security**
- Server-side authorization on every request and every agent tool call; never trust the model.
- Strict workspace isolation (`workspace_id` on every table, isolation tests).
- Retrieved messages/documents are **untrusted context**, never instructions (prompt-injection defense).
- Rate limiting, uploaded-file validation, secrets only in environment variables, append-only Audit Log.

**Reliability**
- WebSocket auto-reconnect with exponential backoff and catch-up of missed messages.
- Idempotent mutating agent tools; agent execution timeout (e.g. 60 s) with limited retries; background jobs retry on failure.

**Accessibility and UX:** keyboard navigation, dark mode, responsive layout, WCAG AA target, progressive disclosure.

**Observability and testing:** structured logs, health checks, metrics that feed the success metrics, automated unit/integration/e2e tests including multi-user, isolation, and permission tests, with reproducible commands.

**Privacy:** workspace content is sent to third-party LLM APIs. Review each provider's data-use terms (especially free tiers) before real users; development uses test data only.

---

## 7. Agent Permissions and Safety

**Roles:** Owner/Admin, Editor/Developer, Viewer.

**Runs automatically (read-only, within the requester's permissions):**
`search_workspace`, `search_messages`, `retrieve_documents`, `list_tasks`, `summarize_channel`, `analyze_bug`, `identify_blockers`, `generate_progress_report`

**Requires approval:**
- Creating tasks (one or many) - low risk
- Creating document drafts / editing documents (as Suggestions) - low risk
- Reassigning work, changing priorities, any deletion - high risk
- External integrations - out of MVP

**Who can approve (decided):**
- **Low risk:** any Editor/Developer or Admin/Owner.
- **High risk:** Owner/Admin only.
- **Viewers** may ask and read, but cannot trigger any agent action that changes data.

**Fixed rules**
- Every tool call re-checks permissions server-side.
- Visible state machine: `proposed` -> `approved` -> `completed` (or `rejected` / `failed`).
- Every action is logged: actor, timestamp, arguments, result, approval status.
- The agent cannot run arbitrary commands or access the filesystem, repositories, or network outside defined tools.
- Tools are idempotent (idempotency keys).

---

## 8. Success Metrics (hypotheses to test, not guarantees)

**Core**
1. **Report-to-ticket time** = timestamp(task created after approval) - timestamp(first message of the bug report). Median. Target: < 2 min.
2. **Agent ticket acceptance rate** = proposals approved with no or minor edits / all proposals decided. "Minor" = 20% or fewer of fields changed. Target: >= 80%.
3. **Similar-bug recall@5** = fraction of evaluation queries where the known related past bug appears in the top 5 retrieved results. Target: >= 70%. Evaluation set: 30 synthetic bugs, each with a related earlier bug phrased differently (built in the RAG slice).
4. **Workflow completion without other tools** = two developers complete the 12-step MVP flow using no tool outside the workspace. Pass/fail.

**Additional**
- Time saved per workflow = time with disconnected tools (stopwatch) - time in product.
- Agent action success rate = successful tool calls / all tool calls (excluding human rejections).
- Approval rejection rate = rejected / decided proposals.
- Task creation latency = approval click -> task visible to a second user (p95).
- Search relevance = recall@5 and MRR.
- User satisfaction = 1-5 rating after each session.

---

## 9. Out of Scope and Risks

**Out of scope:** see "Won't" in section 5.

| Risk | Mitigation |
|---|---|
| Yjs server in Python is less mature than the Node ecosystem | ADR in the Architecture phase: `pycrdt-websocket` inside FastAPI vs. a small dedicated Node service |
| Free-tier LLM rate limits with several users | Agent request queue, retries, Groq -> Gemini fallback |
| Prompt injection via retrieved content | Treat as untrusted data; server-side permissions independent of the model |
| Permission leaks through RAG | Apply permission filters inside the retrieval query; dedicated isolation tests |
| Uneven tool-calling quality across models | Test suite validating Proposal structure per model |
| Scope creep (five systems) | Vertical slices; each slice verified before the next |
| WebSocket scaling beyond one instance | Single instance in MVP; Redis pub/sub later |

---

## 10. Technology Decisions

**Frontend:** Next.js, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand where useful, Tiptap, Yjs.
**Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic, WebSockets. Modular monolith (no microservices in the MVP).
**Data:** PostgreSQL + pgvector; Redis only when justified (queues, pub/sub, caching).
**Infra:** Docker Compose, environment-based configuration, background worker, GitHub Actions.
**AI**
- Provider-agnostic LLM interface with structured outputs and tool calling.
- **Groq = primary** chat/agent provider; **Gemini = fallback** (automatic switch on error or rate limit, logged in the Audit Log; also suitable for long-context summarization).
- **Embeddings:** a local open-source embedding model behind an abstraction (final model chosen by ADR), independent of the chat providers.
- Free/open-source software vs. paid APIs must be clearly separated in docs.

**UI layout (suggested):** left sidebar (workspace switcher, channels, projects, documents, tasks); main area (chat, board, table, or document); right panel (AI teammate, suggestions, task details, related knowledge, pending approvals).

---

## 11. Data Model Overview (*Proposed*; finalized in the Architecture phase)

Entities: users, workspaces, memberships (with role), projects, channels, messages, threads, attachments, documents, document_versions, tasks, task_comments, links, agent_conversations, agent_runs, tool_calls, proposals/action_approvals, memory_records, embeddings, notifications, audit_events.

Principles:
- `workspace_id` on every table, with foreign keys, indexes, and constraints enforcing isolation.
- `links(workspace_id, source_type, source_id, target_type, target_id)` connects messages, documents, and tasks.
- `memory_records` reference their source (`source_type`, `source_id`), carry `workspace_id` and a visibility scope (channel/project/private) used for retrieval filtering; `embeddings` reference memory records.
- Tool calls reference their agent run and (when needed) the approval that authorized them; audit events are append-only.

---

## 12. Delivery Plan (vertical slices)

Each slice includes frontend, backend, persistence, authorization, and tests, and must be verified before the next one starts.

0. **Repo foundation:** monorepo (`frontend/`, `backend/`, `infra/`, `docs/`), Docker Compose (Postgres + pgvector), health check, CI.
1. **Authentication and workspaces:** register/login, workspaces, invitations, roles, workspace isolation tests.
2. **Real-time channels and messaging:** channels, messages, threads, mentions, presence, typing, image attachments, WebSocket reconnect + catch-up.
3. **Projects and tasks:** tasks/bugs, table + Kanban, comments, activity history, links, optimistic concurrency.
4. **Shared agent, read-only tools:** `@Agent` in channels, provider interface (Groq + Gemini fallback), read-only tools, permission-aware context, Audit Log.
5. **Proposals and approvals:** Proposal cards, two-tier approval, idempotent mutation tools, action logs.
6. **Memory and RAG:** embeddings pipeline, permission-filtered retrieval, similar-bug retrieval, 30-bug evaluation set and recall@5 measurement.
7. **Collaborative documents:** Tiptap/Yjs, versions, Suggestions, offline editing, indexing.
8. **Notifications and usability polish** (plus "Should" items by priority).
9. **Public site and billing (post-MVP):** landing and pricing pages, plan and billing settings, checkout, invoices, usage limits. Requires a payment-provider decision (see section 13).

**Verification phase:** multi-user collaboration, workspace isolation, role permissions, agent tool execution, approval requirements, concurrent edits, RAG quality, WebSocket reconnection, mobile responsiveness, failure recovery, with reproducible test commands.

---

## 13. Open Questions (to resolve via ADRs)

- Yjs server approach (Python vs. small Node service).
- Final local embedding model.
- Session strategy details (cookie vs. token) and invitation mechanism (link vs. email).
- Exact agent execution timeout and queue limits per provider.
- Product name (the designs use the working name "Tandem").
- Payment provider: confirm which providers accept a business registered in Jordan, and whether a merchant-of-record service is preferable.
- Real plan prices and limits (the designs use sample values: Free, Team $12, Business $24 per member per month).

---

## 14. UI/UX Design Reference

**Source of truth for visuals:** the design canvas (39 screens, web and mobile, light and dark) and `docs/UI_SPEC.md` (tokens, components, motion, mobile rules). Implement screens from the canvas; when canvas and text disagree, ask.

**Design canvas:** https://claude.ai/artifact/25hwnVHsfUirQYJ4iR9o3t

**Screen inventory and the slice that builds each**

| Area | Screens | Slice |
|---|---|---|
| Auth and first run | Sign up, Log in, Forgot password, Accept invitation, Getting started (empty state), Mobile log in | 1 |
| Members | Members and roles (with role permission matrix), Mobile members | 1 |
| Channels | Channel with agent proposal, Thread, No access, Mobile channel, Mobile thread | 2, 5 |
| Tasks | Task board with task detail, Task table, Mobile board | 3 |
| Agent | Agent panel, Proposal card, Mobile Agent and review sheet, Inbox (approvals and mentions), Mobile inbox | 4, 5 |
| Search and memory | Search with agent answer, Mobile search, Settings: Memory | 6 |
| Documents | Document with Suggestions, Mobile document (offline) | 7 |
| Settings | General, Agent, Audit log, Notifications, Profile and security, Mobile settings | 1, 4, 5, 8 |
| Onboarding | Invite your team | 1 |
| Billing (post-MVP) | Plan and billing, Checkout, Mobile billing | 9 |
| Public site (post-MVP) | Landing, Pricing, Mobile landing | 9 |

**Rules that apply to every screen**
- The agent is always visually distinct (teal) from human actions (indigo); proposal states are always labeled `Proposed`, `Approved`, `Completed`, `Rejected`, `Failed`.
- Risk is always shown in words (`Low risk`, `High risk`, `Admin only`), never by color alone.
- Light and dark themes both ship; every color comes from a design token.
- Mobile is responsive web (390 px reference width); touch targets are at least 44 px.
