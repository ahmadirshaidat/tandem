# Real local embeddings — 17 October 2026

E5-small is selected and installed in the cloud backend's persistent model volume. The earlier network/download block is resolved. Both candidates passed pinned revision, SHA256 and mixed English/Arabic local inference verification. The ONNX conversion cards omit license metadata, so the downloader now checks their exact expected `base_model` link and records the original model's approved license and revision. Unexpected links and unapproved licenses fail closed.

## Unchanged synthetic comparison

Evidence: [retrieval results](../eval/similar_bugs/real-embedding-results.json), [resources and manifests](../eval/similar_bugs/embedding-resources.json), [strict live checks](../eval/similar_bugs/real-embedding-live.json).

All 45 existing queries (30 English, 15 Arabic/mixed) and 75 documents were evaluated using real local inference and SQL in a disposable database. No labels, normalization, chunking, ranking weights or RRF parameters changed. The database was dropped; the backfill CLI also passed.

| Model / method | English recall@5 / MRR | Arabic recall@5 / MRR | Overall recall@5 / MRR | p95 retrieval |
| --- | --- | --- | --- | --- |
| Full-text (E5 control) | 70.00% / .5151 | 46.67% / .4373 | 62.22% / .4892 | 88.33 ms |
| E5 vector | 83.33% / .7418 | 86.67% / .6806 | 84.44% / .7214 | 371.60 ms |
| E5 hybrid | 86.67% / .7064 | 80.00% / .6015 | **84.44% / .6714** | 302.28 ms |
| MiniLM vector | 70.00% / .5450 | 80.00% / .5855 | 73.33% / .5585 | 261.05 ms |
| MiniLM hybrid | 80.00% / .6419 | 86.67% / .5950 | 82.22% / .6262 | 336.12 ms |

Both pass the 70% overall hybrid target. E5 has the higher overall hybrid recall/MRR and vector recall/MRR; MiniLM has higher Arabic hybrid recall. This small authored fixture supports the E5 demo choice, not a production generalization claim. E5 still misses 7/45 hybrid targets; no held-out tuning was performed.

E5 indexing: 1.233 s, 60.85 source documents/s, 1224.05 ms p95 lag. MiniLM: .781 s, 96.07 documents/s, 776.99 ms lag. Each cache is approximately 129.12 MiB (118.31 MB ONNX plus 17.08 MB tokenizer). Weights remain outside Git and the image build context.

Separate native processes measured E5 load 940.05 ms, first inference 4.86 ms, mean of ten warm short-query inferences 5.75 ms, peak process RSS 543.12 MiB. MiniLM measured 933.05 ms, 3.93 ms, 2.66 ms and 542.92 MiB respectively. These single-run, short-input CPU measurements include Python/runtime memory; loading includes checksum verification. They are neither throughput guarantees nor OS cold-cache measurements.

## Runtime and remaining acceptance

The updated backend image was built and started, E5 files copied to `/app/.local/models/e5-small` in its existing persistent volume, ownership set for the backend user, and local model identity verified. Maintenance queued eligible missing active-version vectors, preserving source inclusion and authorization rules. Backend health passed. No external embedding inference is used.

All four strict live cases verified the selected E5 identity and both synthetic tasks through non-degraded vector-only retrieval. Real Groq answer generation then failed with `rate_limited` in all four cases; three completed their required retrieval tool and returned two authorized source chips before the failure. These are failed live acceptance checks, not passes. Both original tasks remained unchanged and zero proposals were created. The separate manual Slice 5 owner approval gate remains outstanding. PR #3 remains draft.

Validation: memory and live-checker regression suite plus initial download guards: 23 passed; expanded downloader suite: 3 passed. Ruff checks passed. No frontend changes were made. No merge or deployment was performed.
