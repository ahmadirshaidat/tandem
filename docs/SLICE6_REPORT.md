# Slice 6: workspace memory and RAG

Validation: 16 October 2026 UTC / 17 October 2026 Asia/Amman. Branch: `slice-6-memory`, based on merged `v1` commit `8d1b3ce`. Draft review: [PR #3](https://github.com/ahmadirshaidat/tandem/pull/3).

**Implementation is delivered for review; acceptance is BLOCKED.** Full-text indexing/search, permission boundaries, APIs, tools and UI passed the automated checks below. Real local embedding weights could not be downloaded under this environment's enforced network policy. Vector/hybrid evaluation and the required ≥70% hybrid recall@5 are unverified. All four latest real Groq checks passed; both Arabic cases required one later bounded retry after initial rate limits. Earlier failures remain recorded. The product owner's manual Slice 5 approval test remains unverified. No AWS deployment or Slice 7 work was performed.

## Delivered behavior and files

- `backend/app/memory/{models,indexing,embeddings,retrieval,router,tools,resolution}.py`: source-linked records, versioned vectors, durable coalescing source jobs, local ONNX adapter, SQL-filtered full-text/cosine/RRF retrieval, search/settings/forget APIs, three read tools and opt-in resolution proposals.
- Migration `d746053b64a6`: scoped foreign keys, GIN/HNSW indexes, Arabic normalization, source queue triggers and existing-source backfill. `backend/migrations/env.py` registers the models. Domain changes and queue revisions commit together.
- Existing `backend/app/agent/{worker,tools,llm}.py`, proposal validation, main router and configuration: reuse the worker, registry, audience rules, audit metadata and validated provider path. No parallel LLM client or direct mutation tool was introduced. Generated event contracts are unchanged.
- `frontend/src/components/memory.tsx`, workspace navigation/routes, channel source chips, shared CSS and API types: global Search, Owner/Admin Memory settings, accessible source toggles, filters, highlights, cursor pages, forgetting preview, degraded/offline states and mobile layout. React renders snippets as text, never HTML.
- `backend/tests/test_memory.py`, `frontend/tests/memory.test.tsx`, `frontend/e2e/memory.spec.ts`: boundary/lifecycle regressions, safe Unicode highlighting and a full bilingual browser flow. Existing registry expectations include the three new reads.
- `infra/{memory_backfill,run_eval,check_memory_live}.py`, `eval/similar_bugs/`, CI, `.env.example`, Compose and README: reproducible backfill, isolated evaluation, strict live metadata checks and operating instructions.
- ADRs [0022](adr/0022-local-multilingual-embeddings.md), [0023](adr/0023-memory-hybrid-ranking.md), [0024](adr/0024-memory-query-time-authorization.md), [0025](adr/0025-memory-indexing-lifecycle.md), [0026](adr/0026-memory-retention-and-forgetting.md). ADR 0022 remains **proposed**, pending actual model comparison.

Messages are grouped within their channel by thread/time window, with overlap; tasks include title, description, status and comments. Hashes retain unchanged records/vectors. A changed source revision immediately hides stale records while the worker rebuilds that channel/project. Deletes, task moves and archives propagate. Claims use `SKIP LOCKED`, stale-claim recovery and bounded failures; embedding runs outside publication locks. Missing or failing local inference still publishes full-text records with visible degradation.

Every candidate query applies current workspace membership, channel membership/private setting, live task/project state, source inclusion, retention and index revision **before ranking and LIMIT**. Services reauthorize results afterward. Agent retrieval also respects its destination audience. Source chips are fetched for the current viewer rather than copied with labels into replayed events. Search returns no unauthorized counts or skipped-source hints.

Private indexing and resolution summaries default off. Retention supports forever, 365 or 90 days and affects derived memory only. Explicit source/record forgetting uses an authorized count preview, signed expiring confirmation, lock/recheck and audit; originals survive. Record suppression keys survive reindexing; forgetting a source disables its inclusion. A newly completed bug after summary opt-in may create an extractive `add_comment` proposal in an eligible public project channel, using the existing approval flow. It creates no comment before human approval and deduplicates completion offers. No extra generation call is needed for that extractive proposal.

The optional Search “Agent answer” card is omitted. Channel agent runs already provide audited answers, tools and sources. Try AI remains isolated. Documents, notifications, billing and integrations are outside this change.

## Actual automated verification

Commands ran with installed backend dependencies and a local PostgreSQL/pgvector database. Browser tests used the production frontend build, Chromium and an explicitly fake-provider backend. That fake mode validates orchestration/permissions, not real AI performance.

| Check | Actual result |
| --- | --- |
| Backend `.venv/bin/ruff check app migrations tests` plus the new infra helpers | Passed; final combined check clean |
| Backend `.venv/bin/ruff format --check app migrations tests` plus helpers | Passed; 81 files already formatted |
| Backend `.venv/bin/pytest -q` | **152 passed, 58.22 s** |
| Final focused `.venv/bin/pytest -q tests/test_memory.py` | **19 passed, 10.61 s** |
| `.venv/bin/alembic upgrade head` / `.venv/bin/alembic check` | Upgrade passed; no new upgrade operations detected |
| Empty-schema and existing-data upgrades | Tested in integration/evaluation; Slice 5 fixture upgrades preserve original data and backfill sources |
| `backend/.venv/bin/python infra/export_events.py --check` | Passed; no generated-contract drift |
| `npm run lint` / `npm run typecheck` | Passed |
| `npm test` | **35 passed across 8 files, 11.67 s** |
| `npm run build` | Passed; `/search` and `/settings/memory` included |
| `CI=true PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | **8 passed, 1.2 min**, including Arabic/mobile/offline memory flow |
| `python3 infra/cloud_build.py` and cloud Compose start | Backend image built; database/backend/frontend started; health, login and frontend API returned HTTP 200 |
| Evaluation/backfill | Disposable database migrated, indexed, evaluated and dropped; backfill CLI exit 0, one job processed |

The final focused check followed the cold-start model-load lock change. A redundant `uv run` invocation could not use its default read-only cache, so the checks were run through the already installed `.venv/bin` executables; no checks were skipped for that reason. The native Windows launcher and physical devices were not exercised in this Linux environment. Cloud containers use the session proxy and trusted CA, with TLS verification enabled. The final runtime has `AGENT_FAKE_PROVIDER=false` and the normal auth rate limit of 10.

Tests cover cross-workspace references/retrieval; private membership and workspace revocation; all three retrieval modes with explicit model stubs; include-private off/on/off; no-leak response shapes; source-chip reauthorization; agent audience restrictions; idempotency; edit/delete/comment/move/archive propagation; retention; model-version requeue; missing and failing inference; signed pagination; forget preview actor/content races; preservation of domain originals; and opt-in proposal-only summaries. Stub embeddings test SQL/lifecycle behavior and never enter the quality harness.

Hosted CI has been read from GitHub, not inferred from local tests. [Run 38977113759](https://github.com/ahmadirshaidat/tandem/actions/runs/38977113759) **passed** on `8e817ff`, including the expanded evaluation-helper lint and all eight browser tests. The PR Checks tab records the subsequent report/configuration commit. Final current-head CI status is recorded in the task completion message.

## Retrieval evaluation: real measurements, missing semantic comparison

Reproduce from the repository root:

```bash
backend/.venv/bin/python infra/run_eval.py --output eval/similar_bugs/results.json
```

The committed synthetic corpus has **30 English pairs, 15 Arabic/mixed pairs and 30 distractors**, totaling 75 indexed earlier bugs and 45 queries. Seed: 20261017. IDs and ranking ties are deterministic. RRF k=60 and equal weights were fixed before evaluation; no test-set tuning occurred. After correcting nondeterministic tie ordering, quality metrics reproduced exactly on two runs. Timings vary; the table uses the latest committed [results.json](../eval/similar_bugs/results.json). MRR follows all result pages within the 200-candidate service cap, including zeros for absent targets.

| Method | English recall@5 / MRR (30) | Arabic recall@5 / MRR (15) | Overall recall@5 / MRR (45) | p95 retrieval |
| --- | --- | --- | --- | --- |
| Full-text | **70.00% / 0.5151** | **46.67% / 0.4373** | **62.22% / 0.4892** | **195.97 ms** |
| Vector only | Not run: weights unavailable | Not run | Not run | Unmeasured |
| Hybrid | Not run: weights unavailable | Not run | **≥70% target unverified** | Unmeasured |

Full-text indexing: **1 job, 0.142 s, 528.32 source documents/s, p95 queue lag 135.28 ms**. Separately, the normal background worker made a newly created task visible through HTTP full-text search in **996 ms**, below the approximate 30-second goal for that small case. These numbers exclude embedding inference and do not establish vector throughput or a production SLA. Distractors have limited topic diversity; this fixture alone cannot establish general semantic quality.

Planned local candidates are quantized ONNX `Xenova/multilingual-e5-small` and `Xenova/paraphrase-multilingual-MiniLM-L12-v2`, both configured for 384 dimensions. **Their actual availability, license, artifact size and inference speed were not verified.** The downloader verifies these at installation: pinned revision, MIT/Apache-2.0 card license, hashes, artifact bound and a local mixed-language inference probe. An initial model API request failed with the safe category `URLError`; the runtime host allowlist still excludes Hugging Face. Required additions (`huggingface.co`, `*.huggingface.co`, `*.hf.co`) are saved in the environment draft but require application. No alternate-host/proxy bypass was attempted.

Use the two-directory comparison command in [the evaluation README](../eval/similar_bugs/README.md) after access is applied. Choose the model from actual recall/MRR, latency, throughput and artifact/resource measurements; update ADR 0022. If hybrid misses 70%, report the miss and use a separate development set for normalization/chunking/weight changes before rerunning a held-out test. Do not relabel full-text fallback as a vector or hybrid pass.

## Live agent checks

The four strict scenarios used synthetic workspaces, real **Groq `openai/gpt-oss-120b`**, the normal agent/provider path, and visibly degraded full-text retrieval. Both English cases passed initially; both Arabic cases passed on one later bounded retry after rate limits. All six attempts are retained in the metadata. [Raw safe metadata](slice6-live-results.json) contains no credentials, questions, answers or provider bodies.

```bash
backend/.venv/bin/python infra/check_memory_live.py --language en --tool analyze_bug --require-live
backend/.venv/bin/python infra/check_memory_live.py --language ar --tool analyze_bug --require-live
backend/.venv/bin/python infra/check_memory_live.py --language en --tool find_similar_bugs --require-live
backend/.venv/bin/python infra/check_memory_live.py --language ar --tool find_similar_bugs --require-live
```

| Requested tool / language | Result | Agent latency / HTTP wall | Successful-generation input / output tokens | Source chips |
| --- | --- | --- | --- | --- |
| `analyze_bug` / English | **Passed** | 2744 / 11236.40 ms | 5113 / 599 | 2 |
| `analyze_bug` / Arabic | **Passed on bounded retry** | 2412 / 2835.39 ms | 6097 / 510 | 2 |
| `find_similar_bugs` / English | **Passed** | 2188 / 2561.81 ms | 5214 / 550 | 2 |
| `find_similar_bugs` / Arabic | **Passed on bounded retry** | 2413 / 2641.35 ms | 6390 / 605 | 2 |

The table shows the latest result for each scenario. All six attempts preserved the two original tasks and created zero proposals. Initially, Arabic analysis failed with `rate_limited` at 229 ms (0/0 successful-generation tokens); Arabic similar-bug failed at 2705 ms after successful tool steps (6388/241 tokens), without finishing its answer. Those initial attempts remain failures, even though later fresh strict runs completed. No provider body was printed or recorded. Usage covers successful generations only; failed HTTP attempt usage is unknown. The first wall measurement includes frontend route compilation/transport/polling and is not model generation time. No Gemini live run was added in Slice 6; its previously documented fallback availability/rate-limit risk remains open. Real answer generation with lexical retrieval does not validate local embeddings.

## Screenshots and visual limits

Captured from the actual deterministic browser flow; agent text in these images uses the fake provider, and the degraded banner reflects missing local weights:

- [Memory settings](screenshots/slice6/memory-settings.png)
- [English search](screenshots/slice6/search-english.png)
- [Arabic search](screenshots/slice6/search-arabic.png)
- [390 px Arabic search](screenshots/slice6/search-mobile-arabic.png)
- [Channel agent answer with authorized source chips](screenshots/slice6/agent-memory-sources.png)

The external design canvas could not be inspected under the environment's access policy; implementation follows `UI_SPEC.md` and existing components. No canvas pixel-match or physical-device acceptance is claimed. Existing light/dark theme tokens are reused; screenshots here show the captured light flow. Browser coverage checks no horizontal overflow at 390 px, automatic text direction, offline state and viewer no-access behavior.

## Remaining gates and practical limits

1. Apply saved model-download host additions; download/verify both real candidates, run local comparison and record size/speed/resource use. Semantic search and the hybrid quality target are still unaccepted.
2. Product owner must perform and record the outstanding real-provider Slice 5 UI approval test. Automated approval tests do not replace that manual acceptance.
3. Groq rate limits remain an operational risk: the initial Arabic attempts failed, while later bounded retries passed. Gemini remains an explicitly unverified fallback for this slice.
4. Keep PR #3 draft until the embedding/quality and manual acceptance gates are resolved; no merge into `v1` or AWS deployment is claimed here.

Whole-source rebuilds favor deletion correctness for small workspaces and temporarily hide that source after edits; very large channels/projects need incremental-window throughput measurements. Retrieval caps each candidate stream at 200, so broad searches may omit low-ranked sources. Cursor pages recompute ranking and can move as content changes. Vector dimensions are fixed at 384; dimension changes require a migration. Stable record-key forgetting suppresses selected chunks through reindexing, not every semantic paraphrase or independent copy elsewhere. Task retention is based on creation time. Resolution offers require an eligible public project channel and recorded facts may be incomplete until a human reviews them.

The proposed next product step is **Slice 7: collaborative documents**, after Slice 6's model/quality/manual gates pass and the owner accepts this review. No Slice 7 implementation is included.
