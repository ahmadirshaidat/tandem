# Slice 2 implementation and validation report

Completed in the new `ahmadirshaidat/tandem` AI workspace repository on `slice-2-channels`, created from `v1`. The user's older desktop project named Tandem is unrelated and was not accessed. `v1` remains the prior foundation branch; no `main` or merge was created.

## Delivered behavior

- Every new workspace has public `general`; migration upgrades existing Slice 1 workspaces and joins their members without replacing their data. Public/private channel lists, topics, rename, archive/unarchive, participation and private membership management are functional.
- Viewers read/post/reply, Editors create/edit public channels, and Owners/Admins manage private membership. Private channels require channel membership for everyone, including Owners/Admins. Lists, counts, message/thread endpoints, images and sockets check workspace/channel access; inaccessible and nonexistent channels share a generic error.
- Persistent messages, threads, own edits, soft deletion and Admin deletion; 4,000-character validation, bounded per-user sends, and retry-safe client message IDs. PostgreSQL locks and uniqueness handle concurrent retries. Member and Agent mentions are stored server-side. No channel invokes Try AI or a provider.
- The cookie-authenticated, Origin-checked socket carries live messages, edits, deletions, replies, channel/member changes, read state, presence and typing. Journal sequences include edits/deletions, and replay/live delivery share one ordered path. Session revocation closes sockets; membership changes invalidate topics. Commands, frame size, subscriptions, idle time and per-user/IP connection counts are bounded.
- Validated PNG/JPEG/WebP/GIF uploads, at most four per message, 5 MiB each. Magic-byte/structure checks reject executables, SVG, malformed PNG and oversized input. Random private storage keys sit behind a storage interface and a dedicated non-root Compose volume. Retrieval authenticates again; deleted message images are unavailable.
- Canvas-based channel/sidebar/thread layouts, date/grouped messages, image lightbox, mentions autocomplete, optimistic sends, explicit failed-send Retry, typing/presence, and an inactive Agent chip. Mobile uses a thread screen, 16 px inputs, 44 px controls, safe-area bottom tabs and a composer above them. Board/Docs are disabled Coming soon. Small Markdown supports formatting/code/links with HTML rendered as text.
- Per-account local cache saves visited channels and the latest 150 synced message/reply records. Offline drafts survive reload and are never queued or automatically sent. Production additionally caches the visited Chat shell/static assets; API/image responses are excluded. Observed revocation removes affected histories; logout/account changes clear this app's cache.

## Files and architectural decisions

Backend: new `backend/app/channels/{models,schemas,service,router,gateway,fanout,storage}.py`; migration `24b996e9d4c9`; `tests/test_channels.py`; configuration/main-router/workspace-creation/invitation integration and test cache isolation. Pillow was added with a committed uv lock. Existing AI source/tests were left unchanged.

Frontend: new `/channels` route, `channel-room.tsx`, `safe-markdown.tsx`, channel/cache helpers, generated event types, `public/chat-sw.js`, unit tests and two-session browser coverage. Shared shell/navigation gains Chat; the API helper permits binary uploads. CSS reuses the existing design tokens. No board/document/search/billing/agent execution was added.

Infrastructure/docs: Compose image volume/limits, Docker non-root image directory and 8 KiB WebSocket transport limit, CI branch trigger/shared contract check, `infra/export_events.py`, `infra/measure_channels.py`, `.env.example`, README and the uploaded Slice 2 brief. ADRs 0004–0007 cover transport, ordering, images and fan-out. The additional `channel_events` table is needed to catch up edits and deletions; `project_id` deliberately has no FK until Slice 3. Redis remains unnecessary for one worker.

Logical implementation commits: `a53eb18` (backend/REST/images/live gateway), `a8cc592` (live UI/offline/typed contract and stronger acceptance checks), followed by the validation/documentation commit.

## Commands actually run and results

| Command / scope | Actual result |
|---|---|
| `uv sync --project backend`; frozen install inside Docker build | Pillow installed; locked image build succeeded with verified TLS |
| In `backend/`: `.venv/bin/ruff check app migrations tests` | Passed |
| In `backend/`: `.venv/bin/ruff format --check app migrations tests` | Passed, 37 files checked |
| In `backend/`: `.venv/bin/pytest -q --tb=short` | **53 passed**; one existing Starlette/httpx TestClient deprecation warning |
| In `backend/`: `.venv/bin/alembic upgrade head`; `.venv/bin/alembic check` | Existing development DB upgraded; no pending schema operations |
| Migration fixtures | Fresh disposable DB migrated; downgrade to Slice 1, insert existing workspace/member, upgrade and verify backfilled general/data preservation passed |
| `backend/.venv/bin/python infra/export_events.py --check` | Backend JSON schema and generated frontend contract match |
| In `frontend/`: `npm run lint`; `npm run typecheck`; `npm test`; `npm run build` | Passed; **24 tests across 4 files**; optimized Next.js build includes `/channels` |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | **3 passed** against the production frontend and real Compose backend |
| `python3 infra/cloud_build.py`; `python3 infra/cloud_start.py` | Build and startup succeeded; database/API healthy; existing cloud data preserved |
| `node infra/dev.mjs --cloud --skip-install --skip-build --no-open` | Correct existing frontend/API reused and verified |
| Fresh desktop-mode fixture: `node infra/dev.mjs --skip-install --skip-build --no-open` | Started on 3001, API 8001, DB 5433, separate Docker namespace/volumes; browser signup/workspace/default general/live send/image upload at 390 px passed |
| Credential scan | 955 source/build files scanned, no private provider values found; root `.env` remained ignored with mode 0600 |

The security tests cover workspace/private channel REST and socket isolation, Viewer restrictions, immediate topic invalidation after private/workspace removal, session logout closure, reinvitation not restoring private access, concurrent idempotency, mentions/counts/history/thread behavior, image magic/CRC/size/access, CSRF, archive behavior, socket Origin/connection/frame/command limits, binary rejection and typing expiry. The browser tests cover two-user messages/replies/presence/typing, XSS text, image upload/lightbox, optimistic failure/explicit Retry, exactly three missed creates and one edit ordered without duplicates, unsent offline drafts, offline reload, 390 px layouts and landscape.

Failures found and corrected: disconnect cancellation cleanup; malformed PNG checksum handling (now 415); fresh image volume ownership; initial channel width/mobile bottom-tab placement; and message acknowledgement/reply-count reconciliation. The temporary launcher fixture reused dependencies through a symlink, requiring a fixture-only Turbopack root setting. That was a validation fixture problem; ordinary fresh clones install their own node_modules. Only this task's temporary desktop fixture and its data were removed afterward; the new cloud app remains running.

## Measured local performance

Final idle production run through Next.js on cloud loopback, one FastAPI worker/PostgreSQL, two authenticated Python WebSocket clients. The clock starts immediately before the HTTP send and stops when the second socket receives the message, including proxy, authorization, transaction and fan-out; it excludes browser painting. History requests include response receipt and JSON validation.

| Measurement | Samples | p50 | p95 | Maximum |
|---|---:|---:|---:|---:|
| Message delivery | 30 | 16.14 ms | **19.53 ms** | 30.31 ms |
| History with 30 messages | 20 | 24.77 ms | **34.05 ms** | — |

Target p95 delivery <300 ms passed. An earlier run was 24.08 ms; a run during a frontend build was 87.96 ms, also below target. These are development-machine observations, not internet latency or production capacity promises. The final raw result is [channels-local.json](benchmarks/channels-local.json).

## Screenshots

- [Desktop channel and thread](screenshots/slice2/channel-thread-desktop-light.png)
- [Mobile channel, light](screenshots/slice2/channel-mobile-light.png)
- [Mobile channel, dark](screenshots/slice2/channel-mobile-dark.png)
- [Mobile thread](screenshots/slice2/thread-mobile-light.png)
- [Fresh localhost launcher at 3001](screenshots/slice2/localhost-3001-mobile.png)

Screens follow the uploaded channel/thread canvas while showing actual available functions and real synthetic team content. Future proposal/task/document panels are intentionally inactive. Screenshots demonstrate the app here, not a desktop browser launched on the user's PC.

## Remaining limits and open questions

- GitHub Actions run status could not be retrieved from this environment (GitHub API network access fails). The workflow now triggers on `slice-2-channels`, and its application checks pass locally. **Remote CI green is unverified**, not claimed. Check the branch run in GitHub Actions after the push.
- No native Windows execution, physical mobile keyboard/device test, public deployment or fresh published-cloud restoration was performed. The launcher was exercised in Linux. This cloud task cannot start processes on the user's PC.
- One worker only. Redis/shared presence/rates, trusted production proxy IPs, event retention/snapshot reset, history query optimization, and abandoned-upload cleanup remain scale/operations work. Old versions remain in the authorized event journal; defining retention is a follow-up.
- Offline devices cannot learn of a server-side permission revocation until reconnecting. Cached image bytes are not available offline. Browser storage can be disabled/full, reducing persistence; live messages still work.
- Mentions use display names; duplicate names need a future unique-handle/product decision. Agent is reserved and only a stored flag. Messages contain no LLM behavior.
- Slice 1 email ownership verification/production mail configuration remain prior gaps. No provider generation or provider-feature changes were made by this slice.
- Next proposed work is **Slice 3: projects and tasks**, after reviewing this branch and the remote CI result. It is not implemented here.

## Open the new project on the PC

With Node.js 24 and Docker Desktop running, use a new folder in a **Local** Codex task or terminal:

```powershell
git clone --branch slice-2-channels --single-branch https://github.com/ahmadirshaidat/tandem.git tandem-workspace-v1
cd tandem-workspace-v1
node infra/dev.mjs
```

The launcher opens `http://localhost:3001/login`. Sign up, create a workspace and open **Chat**. Keep the terminal open. If this new folder already exists, update that verified new repository; do not clone over it or pull into the older unrelated Tandem project. Local provider credentials are optional for Slice 2 and do not transfer from this cloud machine.

Reusable cloud installation/start instructions and the current repository commit are saved in the environment draft for review. Saving does not apply or publish it; use environment settings Review/Save/Publish for future tasks. Actual secrets are never included in those instructions.
