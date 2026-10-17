# Synthetic similar-bug benchmark

`cases.json` contains 30 English and 15 Arabic/mixed query/earlier-bug paraphrase pairs plus 30 distractors, shuffled with seed 20261017. Synthetic task IDs use deterministic UUID5 values and ranking ties use stable source IDs/chunk positions. These are authored synthetic cases, not private project data. All 45 queries are the test set. RRF k=60 and equal weights were declared before the run; there is no hidden test-set tuning. Distractors have limited topic diversity, so this is an initial acceptance fixture rather than a production-quality generalization claim.

Run with an available local PostgreSQL administrator (the development role can create a disposable database):

```bash
backend/.venv/bin/python infra/run_eval.py --output eval/similar_bugs/results.json
```

The harness migrates a disposable database, indexes synthetic bug tasks, runs real SQL full-text/cosine/hybrid retrieval and drops that database in `finally`. It never resets the development database or sends text to an external service. Missing local weights produce full-text measurements plus explicit not-run vector/hybrid statuses. Such a run cannot pass the hybrid gate. Model stubs from unit tests are never used here.

To compare real local candidates, download public weights separately and pass both verified directories:

```bash
backend/.venv/bin/python -m app.memory.embeddings e5-small --destination .local/models/e5-small
backend/.venv/bin/python -m app.memory.embeddings minilm --destination .local/models/minilm
backend/.venv/bin/python infra/run_eval.py --model-path .local/models/e5-small --model-path .local/models/minilm
```

For the module download commands, run from `backend` or set `PYTHONPATH=backend` from the repository root, and use absolute destination paths to avoid ambiguity. A successful download verifies upstream revision/license and artifact hashes, then performs a local mixed-language inference check.

Recall@5 is the fraction of known related bugs found among the first five sources. MRR follows every returned page within the service candidate cap of 200 (the corpus has 75 documents); absent targets contribute zero. Report per-language/overall metrics, p95 request latency and indexing throughput/lag from the actual output. Timing includes service authorization and local database round trips. No production SLA or broad semantic quality is implied by this small dataset.
