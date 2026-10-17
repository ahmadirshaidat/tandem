# Slice 6: workspace memory and RAG — current acceptance report

Updated 17 October 2026 (Asia/Amman). Branch `slice-6-memory`; [draft PR #3](https://github.com/ahmadirshaidat/tandem/pull/3). No new product features were added during acceptance housekeeping.

## Current decision

Local E5 embeddings and the synthetic retrieval quality gate are verified. **Full Slice 6 acceptance remains open pending the product owner's manual Slice 5 real-provider UI approval test.** Strict live rerun results and current CI are recorded below; no automated test substitutes for that manual acceptance. Do not merge or begin Slice 7 on the strength of the embedding benchmark alone.

This is the current report. Earlier model-unavailable, proposed-model-choice and lexical-only live results are historical and superseded by the real E5 evidence. [The earlier embedding investigation](SLICE6_EMBEDDING_GATE.md) and [initial real-model measurements](SLICE6_REAL_EMBEDDINGS.md) retain their dated evidence, not current acceptance instructions. ADR 0022 is accepted for local model choice and synthetic quality.

## Delivered scope

Memory indexes messages and tasks, including task comments. It provides persistent source-linked records, content hashes, model/version/dimension metadata, coalescing indexing jobs, settings and migration/backfill support. Documents, notifications, billing and integrations remain outside Slice 6. Try AI is isolated. The optional Search Agent answer card is omitted; audited channel agent runs already expose tools and sources.

Messages are chunked by thread/time window with overlap; tasks include title, description, status and comments. The existing worker processes indexing with `SKIP LOCKED`, bounded failures and stale-claim recovery. Source revisions hide stale records while rebuilding. Edits/deletes, task moves and archives propagate; unchanged content retains records/vectors. Maintenance queues eligible missing active-version vectors. Dimension changes require a migration.

Retrieval combines normalized Arabic/English PostgreSQL full-text search with HNSW cosine candidates and equal-weight reciprocal rank fusion (k=60). SQL applies live workspace/channel membership, private-channel inclusion, source/settings state, retention and index revision before ranking/limits. Services reauthorize results afterward; shared agent replies also respect their destination audience. Source chips are fetched for the current viewer. Search never returns unauthorized totals or skipped-source hints.

Private-channel indexing and resolution summaries default off. Owners/Admins control per-source inclusion, include-private, forever/365/90-day retention, reindexing and explicit forgetting. Forgetting uses an authorized count preview and signed confirmation, is audited, and preserves originals. Record suppression persists through reindexing; forgetting a source disables inclusion. Opt-in resolution summaries create only an extractive add-comment proposal for human approval, never a direct comment.

Read tools are `search_memory`, `find_similar_bugs` and `analyze_bug`; the closed registry, existing provider protocol, worker and audit path are reused. Search/settings provide filters, text-safe highlighted snippets, cursor pagination, offline/degraded states, mobile layout and `dir="auto"` content. Missing local inference visibly degrades to full-text.

## Implementation map

| Area | Main files |
| --- | --- |
| Memory schema, indexing, retrieval, settings, tools | `backend/app/memory/{models,indexing,embeddings,retrieval,router,tools,resolution}.py` |
| Database migration | `backend/migrations/versions/d746053b64a6_permission_filtered_workspace_memory_.py` |
| Agent integration | Existing `backend/app/agent/{worker,tools,llm}.py` and proposal validation |
| UI | `frontend/src/components/memory.tsx`, workspace routes/navigation, channel source chips, CSS/API types |
| Tests | `backend/tests/test_memory.py`, `test_memory_live_checker.py`, `test_embedding_download.py`; `frontend/tests/memory.test.tsx`; `frontend/e2e/memory.spec.ts` |
| Reproduction | `infra/{run_eval,memory_backfill,check_memory_live}.py`, `eval/similar_bugs/` |
| Decisions | ADRs [0022](adr/0022-local-multilingual-embeddings.md), [0023](adr/0023-memory-hybrid-ranking.md), [0024](adr/0024-memory-query-time-authorization.md), [0025](adr/0025-memory-indexing-lifecycle.md), [0026](adr/0026-memory-retention-and-forgetting.md) |

## Selected model and license

Select quantized ONNX `Xenova/multilingual-e5-small`, version `761b726dd34fb83930e26aab4e9ac3899aa1fa78-q8`, 384 dimensions. Inference/tokenization run locally, using E5 query/passage prefixes, masked mean pooling and normalized vectors; public weights are stored in ignored persistent caches outside Git and the Docker build context. Workspace text is never sent to an embedding endpoint. This does not mean agent generation is local: authorized agent context is sent to the configured generation provider.

Both candidates passed pinned-revision, artifact SHA256 and mixed English/Arabic inference checks. The ONNX conversion card identifies its original model but omits a license field. The original [E5-small card at pinned revision](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md) was re-fetched on 17 October and declares `license: mit`. See [ADR 0022](adr/0022-local-multilingual-embeddings.md) and [license verification metadata](slice6-license-verification.json). The downloader verifies the expected original-model link and approved license and records the original revision; it rejects unexpected links/unapproved licenses.

## Real retrieval evaluation

Evidence: [raw comparison](../eval/similar_bugs/real-embedding-results.json), [resources/manifests](../eval/similar_bugs/embedding-resources.json). Seed 20261017; unchanged 30 English and 15 Arabic/mixed queries over 75 documents including distractors. No label, normalization, chunk or ranking changes and no test-set tuning. MRR follows all returned pages within the 200-candidate service cap. The harness migrates and drops a disposable database; it does not reset development data or use stub vectors.

| Model/method | English recall@5 / MRR | Arabic recall@5 / MRR | Overall recall@5 / MRR | p95 retrieval |
| --- | --- | --- | --- | --- |
| Full-text (E5 control) | 70.00% / .5151 | 46.67% / .4373 | 62.22% / .4892 | 88.33 ms |
| E5 vector | 83.33% / .7418 | 86.67% / .6806 | 84.44% / .7214 | 371.60 ms |
| E5 hybrid | 86.67% / .7064 | 80.00% / .6015 | **84.44% / .6714** | 302.28 ms |
| MiniLM vector | 70.00% / .5450 | 80.00% / .5855 | 73.33% / .5585 | 261.05 ms |
| MiniLM hybrid | 80.00% / .6419 | 86.67% / .5950 | 82.22% / .6262 | 336.12 ms |

Both pass the 70% overall hybrid target. E5 wins overall hybrid/vector recall and MRR; MiniLM has higher Arabic hybrid recall. E5 hybrid retrieves 38/45 known targets in the first five, missing seven. This small authored fixture supports a demo choice, not production-wide generalization. Fixed weights were retained rather than tuned on held-out labels.

E5 indexing: 1.233 s, 60.85 source documents/s, p95 lag 1224.05 ms. MiniLM: .781 s, 96.07/s, 776.99 ms. The backfill CLI passed with one job. An earlier background-worker HTTP full-text probe measured 996 ms; it is a separate measurement without embedding inference, not vector freshness evidence.

Each cache is about 129.12 MiB. Separate native processes measured E5 load 940.05 ms, first short-query inference 4.86 ms, mean ten warm inferences 5.75 ms, peak process RSS 543.12 MiB; MiniLM 933.05 ms, 3.93 ms, 2.66 ms, 542.92 MiB. Load includes checksums; RSS includes runtime memory. Single-run short-input timings are not capacity guarantees or OS cold-cache measurements.

Reproduce from repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.memory.embeddings e5-small --destination "$PWD/.local/models/e5-small"
PYTHONPATH=backend backend/.venv/bin/python -m app.memory.embeddings minilm --destination "$PWD/.local/models/minilm"
backend/.venv/bin/python infra/run_eval.py --model-path .local/models/e5-small --model-path .local/models/minilm
backend/.venv/bin/python infra/memory_backfill.py --workspace WORKSPACE_ID --drain
```

## Strict live checks and input tokens

All **four strict live checks passed on the first attempt**, using Groq `openai/gpt-oss-120b` and exact E5 model/version above. Each next check started 121 seconds after the preceding one finished; no overlapping runs, second attempts, provider/model changes or quota-avoidance probes were used. [Safe per-check/per-turn evidence](../eval/similar_bugs/acceptance-live-spaced.json) retains UTC timestamps, outcomes, HTTP status, an explicit allowlist of retry-after/limit/remaining headers, and token usage. No request/response bodies or credentials were retained. A temporary process-local wrapper observed the existing transport and agent-turn return values; application source and wire payloads were unchanged, and the wrapper was removed after the checks.

| Check | Start (Asia/Amman, 17 Oct) | Input turn 1 | Input turn 2 | Total input | Total output | Agent latency | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| en `analyze_bug` | 22:35:39 | 2,277 | 2,835 | 5,112 | 582 | 2496 ms | Passed |
| ar `analyze_bug` | 22:37:46 | 2,578 | 3,562 | 6,140 | 379 | 2288 ms | Passed |
| en `find_similar_bugs` | 22:39:52 | 2,260 | 2,958 | 5,218 | 882 | 3125 ms | Passed |
| ar `find_similar_bugs` | 22:41:58 | 2,656 | 3,743 | 6,399 | 710 | 2861 ms | Passed |

Every case verified both synthetic tasks through non-degraded vector-only retrieval before generation, completed its required tool, returned two authorized source chips, preserved the two tasks and created zero proposals. All eight provider HTTP calls returned 200 and all eight agent turns used one provider attempt. `retry-after` was absent; response headers reported request limit 1000 and token limit 8000. Observed remaining requests ranged 995–999 and remaining tokens 1516–5499. These are observed headers, not a guarantee of future quota or an inferred billing balance. Groq quota did not block this spaced run.

Reproduction: run each command separately with at least two minutes between completed checks, at most two attempts per case; stop if quota remains the blocker:

```bash
backend/.venv/bin/python infra/check_memory_live.py --language en --tool analyze_bug --require-live --require-embeddings --embedding-model Xenova/multilingual-e5-small
backend/.venv/bin/python infra/check_memory_live.py --language ar --tool analyze_bug --require-live --require-embeddings --embedding-model Xenova/multilingual-e5-small
backend/.venv/bin/python infra/check_memory_live.py --language en --tool find_similar_bugs --require-live --require-embeddings --embedding-model Xenova/multilingual-e5-small
backend/.venv/bin/python infra/check_memory_live.py --language ar --tool find_similar_bugs --require-live --require-embeddings --embedding-model Xenova/multilingual-e5-small
```


The previous [four rate-limited E5 attempts](../eval/similar_bugs/real-embedding-live.json) remain failure evidence. Earlier successful lexical-only runs in `slice6-live-results.json` do not establish semantic acceptance. Latest outcomes are exclusively the spaced runs linked above.

Input reduction proposals only; none implemented:

1. Shorten repeated instructions and schema metadata used as tool descriptions, while preserving authorization rules, required fields and proposal constraints. The current descriptors are name/mode/JSON argument schemas rather than prose descriptions, so inspect schema titles/defaults and repeated protocol text before assuming prose is the main cost. Keep schema validation and the closed registry.
2. Offer only tools relevant to the current intent/phase, retaining prerequisite reads and the human-approval boundaries. The current protocol already gates proposals after reads; narrowing other tools would require routing and authorization regression checks.
3. Trim repeated context and bound source snippets/result fields. Send only necessary evidence and current identifiers/versions; preserve untrusted-data labels, source IDs and hypothesis/citation requirements. Measure quality and usage on a separate development set before changing the held-out evaluation.

Actual successful turn counts above are provider-reported usage, not tokenizer estimates. Failure usage is unknown when absent; zero successful-generation tokens does not establish zero billed failed-attempt usage.

## Automated verification

The implementation's earlier complete local checks passed: backend 152 tests; frontend 35 tests across eight files; browser eight tests. These are historical counts, not claimed fresh counts for this housekeeping commit. The fresh housekeeping regression command `.venv/bin/pytest -q tests/test_memory.py tests/test_memory_live_checker.py tests/test_embedding_download.py` passed **24 tests in 7.87 s**. Earlier embedding checks passed 23 focused tests followed by the expanded three-test downloader suite; Ruff and diff checks passed. Alembic upgrade/check, empty/existing-data upgrade tests, event-contract checks, frontend lint/typecheck/build and backfill are recorded in the earlier implementation evidence.

[CI run 39025113617](https://github.com/ahmadirshaidat/tandem/actions/runs/39025113617) passed on exact application/evidence commit `cb69e104264c865a8b34e05f8c6056fe01efe166`: backend lint/format/tests/migrations, event schema, frontend lint/typecheck/unit/build and browser suite. **Housekeeping test revision `6bf9837596c4dae14d8e527d32a433d3d516d138` also passed [CI run 39063854380](https://github.com/ahmadirshaidat/tandem/actions/runs/39063854380)**, including all browser tests. Current branch checks, including later report-only commits, are available on [PR #3 checks](https://github.com/ahmadirshaidat/tandem/pull/3/checks); their results must be verified independently. CI uses fake agent generation and does not validate real provider availability or download benchmark models.

Tests cover workspace/private isolation, membership revocation, include-private off/on/off, no-leak response shapes, source authorization/audience, idempotency, edit/delete/comment/move/archive propagation, retention, model-version requeue, missing/failing inference, signed cursors, forget preview races/preserved originals and proposal-only summaries. Controlled embedding stubs verify boundary/lifecycle behavior; real weights are used separately for quality.

## Browser CI investigation and fresh captures

**Investigated, with a bounded conclusion.** Original run [38977784061](https://github.com/ahmadirshaidat/tandem/actions/runs/38977784061) exposed only exit 1. A later failed [run 38999835232](https://github.com/ahmadirshaidat/tandem/actions/runs/38999835232) exposed a missing `.memory-source-chips` assertion after a retention change. A deterministic SQL/service regression reproduced an indexing-readiness race: old records disappear immediately when retention queues rebuilding, so an agent asked then has no source to cite. The browser fixture now waits for the exact task to be searchable before asking. Assertions/timeouts remain unchanged; retries are zero.

Three post-fix complete local suites passed 8/8 each (92.36, 89.79, 81.58 seconds), and [CI 39000223061](https://github.com/ahmadirshaidat/tandem/actions/runs/39000223061) passed on fix `1205e7f`. Three earlier local suites also passed, for 48 executions in that investigation. These results support the readiness fix but do not prove the oldest failure had that cause. Its artifact download was retried during this housekeeping and still returned HTTP 403; the original trace remains uninspected.

`frontend/playwright.config.ts` already retains traces and screenshots on failure, with one worker and retries disabled. CI already generates the HTML/GitHub report and uploads both `frontend/test-results/` and `frontend/playwright-report/` on failure for seven days. The later failed run uploaded its failure artifact. No duplicate reporting change was needed.

Fresh E5-active browser verification is recorded in [safe run summaries](slice6-browser-housekeeping.json). The initial startup attempt was invalid: the replacement native backend initially lacked its module path and the suite started before health readiness (1 passed/7 failed). That failed attempt is retained. After correcting startup and checking health, a full suite returned 7 passed/1 failed: `.memory-result` resolved to multiple authorized results with real vector retrieval, while the old English assertion assumed one element. The English and Arabic checks now assert that the required text occurs within the list, retaining the expected task titles and all authorization/source assertions. No product behavior, timeout or retry policy changed.

After that assertion correction, three independent complete suites passed with real E5 embeddings, a production frontend, Chromium, one worker and fake generation:

| Fresh post-correction suite | Passed / failed / skipped / flaky | Wall time | Retries |
| --- | --- | --- | --- |
| 1 | 8 / 0 / 0 / 0 | 80.98 s | 0 |
| 2 | 8 / 0 / 0 / 0 | 73.60 s | 0 |
| 3 | 8 / 0 / 0 / 0 | 71.80 s | 0 |

That is **24/24 fresh post-correction browser executions**. The two preceding failed attempts remain in the linked summary. Targeted ESLint and `npm run typecheck` passed for the two assertion changes. These runs do not reproduce the old missing-source-chip failure. They verify the complete bilingual/mobile/forget/source flow against real embeddings, while fake generation keeps browser tests deterministic and makes no provider calls.

Screenshots below replace earlier degraded-state captures. E5 identity/version and non-degraded vector retrieval were checked for the capture fixture; Memory settings visibly shows Hybrid. The refreshed agent screenshot comes from the final deterministic suite with E5 active and fake generation; it is not a real-provider answer screenshot. [Screenshot verification and hashes](slice6-screenshot-evidence.json) record that provenance.

- [Memory settings](screenshots/slice6/memory-settings.png)
- [English search](screenshots/slice6/search-english.png)
- [Arabic search](screenshots/slice6/search-arabic.png)
- [390 px Arabic search](screenshots/slice6/search-mobile-arabic.png)
- [Agent answer with authorized sources](screenshots/slice6/agent-memory-sources.png)

The external canvas was not inspected; UI follows `UI_SPEC.md` and existing components. Screenshots use light theme; physical-device acceptance and pixel matching are unverified. Mobile evidence is 390 px Chromium emulation. No native Windows launcher verification was added here.

## Remaining acceptance and operational limits

- Product owner must perform and record real-provider Slice 5 UI approval acceptance in [the manual checklist](SLICE4_LIVE_CHECK.md#product-owner-manual-ui-acceptance--pending). Automated synthetic HTTP approval evidence does not satisfy it. PR #2 and Slice 5 are merged; earlier strict Groq English/Arabic approval checks are documented there.
- The strict Slice 6 English/Arabic live gate passed in the spaced run above. Historical rate limits remain an operational risk; future concurrent calls were not load-tested.
- Gemini fallback quota/availability remains an open risk; this task does not switch providers/models or revalidate Gemini.
- The oldest browser failure trace is uninspected despite the later reproduced race and passing fix validation.
- Whole-source rebuilds temporarily hide changed sources and need large-workspace throughput testing. Each candidate stream caps at 200; cursor order can shift with content. Retention uses task creation time. Forgetting suppresses selected record keys, not independent copies or semantic paraphrases elsewhere. Resolution offers require an eligible public project channel and human review of potentially incomplete evidence.

After browser verification the runtime was restored to `AGENT_FAKE_PROVIDER=false`, auth limit 10, and the verified E5 model/version. Backend health returned HTTP 200 with database/pgvector connected. Temporary diagnostic monkeypatches ran only in the stopped native acceptance process and are not in application source.

PR #3 remains draft. No merge into `v1`, AWS deployment, new features or Slice 7 work was performed. Proposed next product slice is collaborative documents only after the outstanding acceptance gate is resolved.
