# Slice 7: collaborative documents — implementation and acceptance

Implemented 17 October 2026; acceptance follow-up updated 18 October 2026 (Asia/Amman). Branch `slice-7-documents`, based on `v1` merge `99f0b9f`; [draft PR #4](https://github.com/ahmadirshaidat/tandem/pull/4).

## Acceptance decision

Implementation is delivered for review; **keep the PR draft pending owner acceptance and the limits below**. The user explicitly instructed proceeding and merging the green Slice 6 PR #3 while prior manual owner checks were still unrecorded. Those manual Slice 5/6 checks are not recorded as a pass. PR #3 is merged; no Slice 8 work or public/AWS deployment is included.

Latest live outcomes and hosted CI are recorded below. Deterministic fake-provider tests are distinct from real Groq acceptance. No provider/model changes were used to avoid quota.

## Merge order verified

[PR #3](https://github.com/ahmadirshaidat/tandem/pull/3) was merged into `v1` on 17 October at 23:00:15 Asia/Amman, merge `99f0b9f60fecad8fd902598a8e2646b1967973d2`. [PR #4](https://github.com/ahmadirshaidat/tandem/pull/4) targets `v1`, is based on that merge, and remains open/draft. It has not been merged. This verifies dependency order, not the unrecorded owner UI acceptance. [Safe CI/merge metadata](slice7-ci-investigation.json).

## Delivered behavior

- Project documents with Spec, Meeting notes, ADR and Bug postmortem templates; filtered list, title changes, archive/delete, private membership, and conversion of a selected channel message into linked meeting notes. REST conversion supports up to 30 selected messages and keeps private conversations private.
- Tiptap/Yjs editor with formatting, headings/lists/code, Markdown shortcuts, slash block controls, inline @ search and a linked-item selector, automatic block direction, live named/color cursors, saved/offline status, backlinks and Markdown export. Image/file embeds, imports, comment threads and other exports are absent.
- PostgreSQL CRDT state and incremental updates; periodic compaction and bounded update retention. Plain text/Markdown are derived, not authoritative. The existing background worker indexes documents by heading into local E5 memory; the Documents toggle and current private-document membership apply before SQL ranking/limits.
- Automatic snapshots by activity and last-editor leave, named versions, preview and confirmed restore. Restore creates a new mergeable edit/version without deleting history. Versions record the human and accepted Agent proposal attribution.
- Agent `get_document` and `retrieve_documents` reads, plus `propose_suggest_edit` through the existing proposal workflow. Server-generated Yjs relative positions, canonical payload hashes, expiry, current-role checks, stale detection and idempotent human approval protect the reviewed text. No direct document-writing agent tool exists.
- IndexedDB persistence and cached document shell allow offline editing and reload. Authorized reconnect merges changes. Revoked permissions reject updates and preserve a user/workspace/document-specific local copy in Rejected changes, with download and explicit discard. Agent requests/Suggestions require a connection.
- Document-specific audit events and current-viewer authorization for versions, links, source chips, proposals and audit metadata. A workspace Admin without explicit private-document membership does not receive that document's audit target IDs. Suggestion payloads are not copied into channel events.

## Server approach: measured comparison

Choose a small Node/Yjs transport and stateless transformation service, keeping Python as the sole session/role/membership authority and PostgreSQL writer. Every connection, update and recipient is reauthorized through Python; a 500 ms check closes revoked/changed sessions/roles. Origin, cookie authentication, CSRF, frame/rate/idle/document limits are enforced. Awareness is ephemeral; user names/colors come from authenticated identity. The Node service runs as a non-root user with a server-only transformation credential, never sent to browsers.

| Synthetic spike | Python FastAPI/pycrdt | Node/Yjs |
| --- | --- | --- |
| Two-client samples | 100 | 100 |
| p95 sync | 2.47 ms | 1.19 ms |
| Process RSS after samples | 41,932 KiB | 55,620 KiB |
| Server-mediated same-word convergence | Passed | Passed |
| Viewer denial / malformed rejection | Passed / Passed | Passed / Passed |

[Raw spike evidence](slice7-server-spike.json), [ADR 0027](adr/0027-document-sync-server.md). These small-message spikes use a synthetic authorization guard and exclude PostgreSQL/production auth; their latencies are not the product SLA. Python used less memory. The installed pycrdt 0.14.9 binding lacks public XML-text relative-position creation/resolution support needed for the proposed anchoring implementation; Yjs exposes it directly. This favors the Node integration, not a claim that Python synchronization is incorrect. Costs are a second service/image and a backend round trip per sender/recipient.

The initial server-mediated harness matched any broadcast to the next command and produced invalid false-convergence/missing-denial results. Request-ID correlation corrected the harness. [Superseded output](slice7-server-spike-superseded.json) is retained; it is not evidence against either engine. No failing assertion was weakened.

## Document-open analysis added 18 October

The original **2,627.03 ms** navigation-to-visible measurement had no per-stage trace. It cannot retrospectively be attributed to one operation. A new metadata-only profiler, `node infra/measure_document_open.mjs`, separates bundle download, API timings, IndexedDB readiness, editor DOM, first authorized Yjs state and visible content. [Six raw samples](slice7-document-open-profile.json) retain no cookies, response bodies, document text or private IDs.

Production Next server and unthrottled local Chromium, three fresh contexts each followed by one warm-context page; service workers blocked. A fresh context is not a cold process/OS cache. All six samples use the same synthetic 52.8 KB document; no generation calls. This highly repetitive fixture compresses unusually well and does not represent arbitrary document compression.

| Stage in first fresh-context sample | Observed |
| --- | --- |
| Navigation to visible locator, host timer | 2,317.24 ms |
| Initial HTML response complete | 160.10 ms after navigation |
| Loaded JavaScript, total | 1,328,952 decoded bytes; 402,072 encoded bytes |
| Largest shared chunk | 812,979 decoded / 245,591 encoded bytes; download complete at 605.10 ms |
| First `/auth/me` request starts | 1,292.10 ms; request itself 12.20 ms |
| Workspace request | Starts 1,375.50 ms; 22.70 ms |
| Document REST request | Starts 1,458.10 ms; 206.10 ms; 106,283 decoded bytes (882 compressed for this repetitive fixture) |
| First editor DOM / IndexedDB open | 1,760.30 ms / 170.70 ms duration |
| Socket created / first authorized state | 1,866.30 ms / 2,014.30 ms; first state frame 71,260 UTF-8 bytes |
| First state to text appearing in DOM | 142.10 ms; includes Yjs/Tiptap processing and rendering |
| CDP main-thread script / all task time | 983.73 ms / 1,945.62 ms; includes all shared app code, not isolated editor construction |

Stages overlap and must not be added. Browser content appeared at 2,156.40 ms; the host locator timer includes browser/driver observation overhead. The fresh-context totals were 2,317.24 / 915.39 / 1,003.15 ms (median **1,003.15 ms**). Warm-context totals were 1,970.64 / 1,058.40 / 718.85 ms (median **1,058.40 ms**); warm was not consistently faster, and cached IndexedDB text can appear before the new socket state. Six samples are too few for a performance guarantee or a reliable p95.

The evidence points to substantial shared-bundle execution/hydration and a serial auth → workspace → document bootstrap before sync starts; fetching a 52.8 KB state alone does not explain the total. The app statically imports Documents into `WorkspaceApp`, so the shared bundle includes the editor alongside other workspace features. The document REST response contains derived plain text plus Markdown, and Yjs state is then loaded separately. Editor bootstrap also waits for IndexedDB before provider setup. These are measured/inferred contributors, not proof of the historical 2.63-second run's exact cause.

**Proposals only, not implemented:** lazy-load editor code for document routes; narrow the metadata response to avoid unnecessary derived-text duplication; reduce duplicate project/channel reads; and instrument editor construction separately before changing provider initialization. Preserve offline/cached-shell behavior, current authorization and state integrity in any later optimization. The current measurement does not isolate Tiptap's constructor CPU time.

## Production-path performance

[Raw measurements](slice7-document-performance.json), reproduce with `node infra/measure_document_sync.mjs` against the running app. Synthetic data only; no generation calls.

| Measurement | Observed |
| --- | --- |
| Document text size | 52,827 UTF-8 bytes |
| Sync samples | 30 |
| p95 sender-to-second-client sync, including Python authorization and PostgreSQL persistence | **407.22 ms**, below the 500 ms local target |
| Open document to visible content | **2,627.03 ms** |
| Document indexing visible through HTTP full-text search | **18,295.83 ms**, below the approximate 30-second target |

This is one local run, not a capacity/SLA claim. It includes concurrent indexing load and complete authorized fanout. Open time includes browser navigation and editor startup. No fleet/large-room/network impairment benchmark is claimed.

## Verification actually run

| Check | Result |
| --- | --- |
| Full backend suite before final protocol regression additions | **160 passed in 58.04 s** |
| Additional proposal prerequisite regressions | **3 passed in .75 s**; document reads unlock only document Suggestions; task/project reads retain their own gates |
| Focused document/audit/agent scope follow-up | **18 passed in 22.81 s** |
| Node CRDT tests | **4 passed**: Arabic/emoji anchors, preceding concurrent insertions, stale text, restore, malformed/unsupported content |
| Backend lint/format and helper checks using backend configuration | Passed locally |
| Alembic upgrade / check | Passed; no new upgrade operations detected; existing integration tests also downgrade to earlier slices and re-upgrade |
| Generated event contract | Passed, including document-scoped transport metadata |
| Frontend lint / typecheck | Passed locally |
| Frontend unit tests | **35 passed across 8 files** |
| Production frontend build | Passed; `/documents` included |
| Final complete browser suite with real E5 and fake generation | **11 passed, 1.8 min**, one worker, retries disabled; previous complete run: 10 passed, 1.6 min |
| Focused document cold-offline-reload / Viewer / session checks | **2 passed, 25.0 s** |
| Document checks against the final Compose backend + sync containers | **3 passed, 25.8 s**; includes expired access-cookie renewal and subsequent persisted editing |
| Cloud Docker build and Compose startup | Backend and document-sync images built; PostgreSQL/backend/sync all healthy after the non-root file-ownership fix |

The delivered implementation at `d9df90e` passed [hosted run 50](https://github.com/ahmadirshaidat/tandem/actions/runs/39068164321): **163 backend, 35 frontend and 11 browser tests**, including session renewal. Its only check annotation is a Playwright **notice** reporting 11 passes. Current follow-up status is available at [PR #4 checks](https://github.com/ahmadirshaidat/tandem/pull/4/checks); the new launcher smoke job is separate from full Windows/Docker Desktop acceptance.

Browser coverage includes concurrent edits inside the same word and paragraph, convergence, offline plus online edits, cold offline reload, current-permission merge/rejection, private membership revocation, Viewer update denial, session revocation, suggestion approval, version UI, literal HTML/XSS remaining inert, and 390 px mixed Arabic content. Backend tests cover scoped references, private REST endpoints, role boundaries, memory toggle/indexing/deletion, malformed/oversized updates, stale/tampered/double-approved Suggestions and version attribution/restore. Node tests cover relative-anchor Unicode behavior separately from fake generation. Not every operational failure mode is covered.

Commands run (from the repository root unless a frontend/backend working directory is indicated):

```bash
# backend/; disposable integration database, no paid calls
uv run --frozen ruff check app migrations tests
uv run --frozen ruff format --check app migrations tests
uv run --frozen pytest -q
uv run --frozen alembic upgrade head
uv run --frozen alembic check
# root
backend/.venv/bin/python infra/export_events.py --check
node --test sync/crdt.test.mjs
python3 infra/cloud_build.py
python3 infra/cloud_start.py
# frontend/
npm run lint
npm run typecheck
npm test
npm run build
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npx playwright test --reporter=dot
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npx playwright test e2e/documents.spec.ts --reporter=dot
```

Local browser tests use the OS Chromium executable; hosted CI installs Playwright Chromium. Generation is explicitly fake for browser/integration runs; live commands below run separately in real mode. Cloud startup was awaited before the successful final browser invocation.

## Two reported CI errors: identified and already corrected

The user's pasted errors match two historical failed runs, not the final green run:

| Run | Actual error | Correction and subsequent evidence |
| --- | --- | --- |
| [43](https://github.com/ahmadirshaidat/tandem/actions/runs/39067074306) | `ModuleNotFoundError: app.documents.schemas` during event export; the new file was omitted from the commit | `59e9617` added `backend/app/documents/schemas.py`; run 44 passed |
| [46](https://github.com/ahmadirshaidat/tandem/actions/runs/39067480168) | Ruff would reformat `infra/check_document_live.py` and `infra/run_document_sync.py` | `f25d9ca` applied `backend/pyproject.toml`; runs 47–50 passed |

Both were real delivery errors, not flaky browser failures. The same event-export and configured Ruff commands passed again locally on 18 October. The final run's PostgreSQL service logs also contain expected constraint rejections from tests of immutable audit history, duplicate email and cross-workspace foreign keys; those are separate from these two CI failures. None of the checks, assertions or PostgreSQL logging was disabled. [Safe investigation metadata](slice7-ci-investigation.json).

## Failures investigated and corrections

- Fetch `Response.ok` is a property. Calling it as a method made the first transport reject valid users; fixed the guard, keeping the content assertions.
- DOM convergence originally included decorative remote cursor names and compared against a text snapshot taken before convergence. The test now compares the two current semantic document texts with cursor decorations removed, and explicitly exercises same-word insertion too.
- Already-known Yjs deletion sets can make a state-vector diff nonempty. Echoing those on every ACK created a replay loop and rate-budget exhaustion, hiding online edits on reconnect. Pending edits now have explicit local versions/ACK tracking; replay occurs once on reconnect, not on ACK/poll. The regression caps outgoing update frames and retains both online/offline edits.
- Existing Slice 3/5 migration tests exposed an initially incomplete new downgrade. The downgrade now removes document-derived entries and restores prior constraints, preserving unrelated earlier-slice records; those upgrade regressions pass.
- The non-root sync container initially could not read host files copied with restrictive ownership. Docker COPY now assigns package/code ownership to `node`; Compose startup and both document browser flows then passed.
- A local final browser invocation was started before Compose startup completed. Two checks received a proxy setup error and one received 503 before the sync service started. After `cloud_start.py` completed with all services healthy, all three passed; this was a test-start sequencing error, not an unexplained intermittent pass.
- Access-token expiry now uses the existing CSRF-protected refresh-session flow, then reauthenticates the new socket through Python. A forged expired fixture is denied and only selects retry UX; the regression requires a real refresh cookie and verifies a subsequent edit persisted. Logout and revoked membership still retain/reject local edits.
- Hosted CI initially stopped at formatting of two new helpers because their local formatter configuration differed. The helpers now use the backend configuration, matching CI. No test assertion was removed to clear CI.
- Document reads initially unlocked unrelated task proposal schemas. The existing prerequisite protocol now gates `suggest_edit` on `get_document`, task proposals on task reads, and task creation on project reads; three regressions cover the distinction. No descriptions/context trimming or provider/model changes were made.

## Real Suggestion approval checks

[Safe live evidence](slice7-live-results.json), Groq `openai/gpt-oss-120b`, real generation with E5 active:

| Language / attempt | Result | Finished (Asia/Amman) | Agent latency |
| --- | --- | --- | --- |
| English 1 | Failed: provider rate limit | 17 Oct 23:35:02 | 2,310 ms |
| English 2 | **Passed** | 17 Oct 23:38:11 | 2,121 ms |
| Arabic 1 | **Passed** | 17 Oct 23:40:17 | 2,169 ms |

The English retry followed the prerequisite-gating correction described above. There were more than two minutes between attempts; at most two attempts per language were used. Both successful flows verified no edit before approval, one application after duplicate approval and an agent-approved version. The first quota failure remains in the evidence; no provider/model was changed. Provider HTTP headers were not exposed by this document checker, so no retry-after/limit/remaining values are claimed.

Reproduce separately, allowing at least two minutes between attempts; use at most two attempts per language and stop if quota remains the blocker:

```bash
backend/.venv/bin/python infra/check_document_live.py --language en --require-live
backend/.venv/bin/python infra/check_document_live.py --language ar --require-live
```

These create isolated synthetic workspaces and use the existing channel agent/provider path. The checks require real mode, a proposed exact replacement with unchanged document before approval, the authenticated synthetic human's approval, exactly one applied edit after a repeated accept, and an agent-approved version. This is automated HTTP acceptance, not the product owner's manual UI approval.

## Screenshots and visual limits

[Editor with cursors](screenshots/slice7/editor-live-cursors.png), [Suggestions](screenshots/slice7/suggestions.png), [Version history](screenshots/slice7/version-history.png), [Private document](screenshots/slice7/private-document.png), [390 px offline Arabic/mixed document](screenshots/slice7/mobile-document-offline.png). Captured from the actual two-session browser flow with E5 active and explicitly fake generation. They are not screenshots of real-provider answers.

The design canvas request returned `URLError`; no visual canvas comparison is claimed. UI uses `UI_SPEC.md` and existing tokens/components. Screenshots show light theme; physical devices, full Windows Docker Desktop app startup, exact canvas match and long-duration accessibility/session soak tests remain unverified. The mobile evidence is Chromium emulation.

## Launcher verification

`node infra/dev.mjs` uses Compose to start **db, backend and document-sync**, building both app images unless `--skip-build` is supplied. Docker Desktop supplies the Node service; no separate host `npm ci --prefix sync` is needed for this launcher workflow. Native development without the containerized Node service still needs the separate command documented in README.

[Resolved desktop Compose metadata](slice7-launcher-configuration.json) verifies API 8001, database 5433 and document-sync 8003; backend → Node traffic uses `http://document-sync:8002`, Node → authority uses `http://backend:8000`, and the service waits for backend health. Frontend document rewrites use host port 8003 on desktop. The launcher now probes both API/CSRF and document-sync health before reporting ready; a healthy API alone cannot pass.

Eight launcher tests pass locally, including actual native npm process dispatch, paths containing spaces, help, and sync-health failure handling. The separate [`windows-latest` smoke job](https://github.com/ahmadirshaidat/tandem/actions/runs/39126826111/job/117673603282) passed **8/8** on `79fa662`, including actual native npm dispatch and launcher help. This covers Windows dispatch/readiness code, **not** a Docker Desktop end-to-end run. On Linux/cloud, `node infra/dev.mjs --cloud --no-open --skip-install --skip-build` successfully reused the production frontend after all three services became healthy, preserving existing configuration/data. Full Windows Docker Desktop execution remains unverified.

## Files and operation

- `backend/app/documents/{models,service,router,schemas,tools}.py`; migrations `a7dd3485c932`, `f220ae533c78`, `48c11a2883ac`.
- Existing agent/proposal/authorization/audit services and memory models/indexing/retrieval/router; existing generic links; generated event contract.
- `sync/{server,crdt}.mjs`, locked dependencies, non-root Dockerfile, Compose/cloud/desktop launcher configuration.
- `frontend/src/components/documents.tsx`, `frontend/src/lib/document-sync.ts`, document route/navigation, channel conversion control, Memory toggle, document CSS and offline shell.
- Backend/document protocol tests, `sync/crdt.test.mjs`, `frontend/e2e/documents.spec.ts`, spike/live/performance helpers and evidence.
- Follow-up profiling helper `infra/measure_document_open.mjs`, launcher probes/tests `infra/dev-runtime{,.test}.mjs`, Windows CI smoke job, safe CI/launcher metadata and document-open timings.
- ADRs [0027](adr/0027-document-sync-server.md), [0028](adr/0028-document-state-and-compaction.md), [0029](adr/0029-document-suggestion-anchors.md), [0030](adr/0030-document-history.md), [0031](adr/0031-document-privacy-and-offline.md).

Docker: `docker compose up -d --build --wait` starts database/backend/sync; run the frontend as in README. Cloud: `python3 infra/cloud_build.py` then `python3 infra/cloud_start.py`; both backend and sync use supported build proxy/CA trust. Native: `uv sync --project backend --frozen`, `npm ci --prefix sync`, run `backend/.venv/bin/python infra/run_document_sync.py` beside the backend and frontend. Desktop launcher uses document port 8003 alongside API 8001/frontend 3001. Set the actual browser `FRONTEND_URL` consistently; do not expose secrets to frontend variables.

## Known limits and remaining acceptance

- Prior manual Slice 5 approvals and Slice 6 search/Memory owner acceptance remain unrecorded. The owner must also review Slice 7 before merge; automated synthetic checks do not replace that judgment.
- Both English and Arabic live automated Suggestion flows passed. Groq quota failed the first English attempt and remains an operational limit; no sustained quota or production availability guarantee is claimed.
- Gemini fallback has not been revalidated; no provider was substituted for Groq. Physical-device/Windows/canvas checks above remain unverified.
- One backend/sync instance only. Reauthorization polls at 500 ms, and a recipient is checked before each fanout; no distributed fanout, multi-instance consistency or large-workspace load guarantee is claimed.
- Defaults are 64 KiB/update, 1 MiB state/text, 240 frames/minute/connection and 120-second idle reconnect. Large offline bursts can exceed frame limits; local copies remain available. Browser storage capacity/failure and extended outage stress are not exhaustively tested.
- **Accepted MVP capability limit:** Suggestions replace a unique text range within a single XML text node. They cannot span paragraphs, headings or differently formatted text nodes, or perform structural rewrites; an Agent “improve document” request must produce narrower Suggestions. This scope acceptance is separate from still-unverified manual flow acceptance. Staleness is checked before applying. Agent document text is bounded to 10,000 characters and headings to 40; retrieve narrower memory context for large documents. Shared document search conservatively excludes private documents; explicit `get_document` additionally requires a destination audience that can all read the private document.
- Automatic last-editor-leave snapshots are best effort on normal disconnect; persisted state is saved on every accepted update. A process crash may miss the final history boundary, not the persisted edit. Retention/restore and CRDT state size need longer-running tests.
- The UI converts one selected message at a time; the REST conversion accepts multiple selections. No document threads, images, file embeds, format import or Word/PDF export were added.

Proposed Slice 8 direction is **MVP hardening and measurement**, with notifications deferred: email ownership verification, real SMTP validation, a shared limiter, production settings and backup/restore, measurement of the four PRD success hypotheses, and a security review before a pilot with two real developers. Define the acceptance checklist before implementation; do not treat a report as manual owner acceptance. No Slice 8 implementation is included.
