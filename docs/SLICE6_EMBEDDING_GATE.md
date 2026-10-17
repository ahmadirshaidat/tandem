# Slice 6 embedding gate follow-up — 17 October 2026

**Gate remains BLOCKED. No model has been selected and ADR 0022 is not accepted.** Both candidate model API requests returned `URLError`. Current runtime observations report an enforced policy excluding the requested hosts. The hosts exist in the saved environment draft, but that draft has not been applied to this running environment. This follow-up adds validation and failure evidence only; no application features or retrieval tuning were added.

Machine-readable evidence: [slice6-embedding-gate.json](slice6-embedding-gate.json). Fresh full-text control: [embedding-gate-full-text.json](../eval/similar_bugs/embedding-gate-full-text.json).

## Candidate verification

| Candidate | Download probe | License / artifact size / upstream hashes | Inference speed / RAM / cold start |
| --- | --- | --- | --- |
| `Xenova/multilingual-e5-small` | `URLError`; no installed manifest | Unverified | Unmeasured |
| `Xenova/paraphrase-multilingual-MiniLM-L12-v2` | `URLError`; no installed manifest | Unverified | Unmeasured |

The existing adapter adds `query: ` and `passage: ` for E5 and does not add them for MiniLM. That code path has not been validated with real weights here. The downloader's pinned-revision/license/hash checks cannot be called verified until actual downloads succeed. BGE-M3 was not downloaded or evaluated under the same network block; its size and RAM cost are unknown. No stronger-model quality or resource claim is made.

The environment has a **32 GiB cgroup memory limit and four CPU cores**. The existing backend image is **798,135,795 bytes (761.16 MiB)** with no model weights baked in. Native cache directories are `.local/models/e5-small` and `.local/models/minilm`; container caches live under `/app/.local/models/` in the persistent `tandem_mail_outbox` volume. Both native manifests are absent. Model weights belong in ignored caches, outside Git and the Docker build context. Actual per-model cache cost, peak RAM and cold-load/first-inference time remain unmeasured.

## Untouched evaluation control

Executed:

```bash
backend/.venv/bin/python infra/run_eval.py --output eval/similar_bugs/embedding-gate-full-text.json
```

The disposable database was migrated, seeded, indexed, queried and dropped. The backfill CLI passed with one job. The held-out set remains byte-identical to the previous commit: SHA256 `22890a87048e5ae86acef4f12cf7b69c07d21419d8fd90343eec992598f2965c`. It contains 30 English and 15 Arabic/mixed queries over 75 documents. No normalization, chunking or ranking weights changed; no development-set tuning was performed.

| Method | English recall@5 / MRR | Arabic recall@5 / MRR | Overall recall@5 / MRR | p95 retrieval |
| --- | --- | --- | --- | --- |
| Full-text | 70.00% / 0.5151 | 46.67% / 0.4373 | **62.22% / 0.4892** | 163.43 ms |
| Vector-only | Not run | Not run | Not run | Unmeasured |
| Hybrid | Not run | Not run | **≥70% target unverified** | Unmeasured |

Full-text indexing measured **0.218 s, 344.66 source documents/s and 210.78 ms p95 queue lag** for one job. These measurements contain no embedding inference and do not establish semantic-search throughput. Quality reproduced the previous full-text result; timing changed between runs. Full-text remains below the overall target and does not pass the hybrid gate. Once real comparison is possible, report any miss directly; use a separate development set before changing normalization/chunks/weights and preserve the held-out labels.

## Browser failure investigation

Three separate complete local suites ran against the production frontend and an explicitly fake-provider backend, with one worker and retries disabled:

| Run | Result | Command wall time |
| --- | --- | --- |
| 1 | 8 passed; 0 skipped; 0 unexpected | 109.15 s |
| 2 | 8 passed; 0 skipped; 0 unexpected | 94.30 s |
| 3 | 8 passed; 0 skipped; 0 unexpected | 87.25 s |

All **24 test executions passed**. This did not reproduce the original failure or establish its cause. Successful runs logged some Next.js proxy `ECONNRESET` messages; no evidence ties them to the earlier failed Actions run. No assertion was weakened and automatic retries remain disabled.

The original failed [run 38977784061](https://github.com/ahmadirshaidat/tandem/actions/runs/38977784061) has a `browser-test-results` artifact (ID 12079502710, 5,393,849 bytes). Downloading it was denied at `productionresultssa15.blob.core.windows.net`; its trace contents could not be inspected. Its original check annotation only reports exit 1. The prior intermittent failure remains an open risk.

CI now generates the Playwright HTML report alongside GitHub failure annotations and retains failure traces, screenshots and the HTML report for seven days in `browser-test-results-RUN_ATTEMPT`. [Run 38999002230](https://github.com/ahmadirshaidat/tandem/actions/runs/38999002230) passed on `58f1847` with this configuration. Because it passed, the new HTML upload path has not yet been observed on an actual failed follow-up run. Existing backend checks, frontend lint and typecheck also passed. Final report-only commit checks are available on PR #3.

## Strict live semantic preflight

The live checker now accepts `--require-embeddings` and an optional exact `--embedding-model MODEL_ID`. It rejects missing embeddings or a mismatched model before requesting generation. `--require-live` alone continues to permit degraded retrieval, so the earlier successful Groq/full-text checks do not satisfy this gate.

Both English and Arabic preflights ran with `--require-live --require-embeddings` and stopped with exit 1 / **`embedding_unavailable`**, with model/version null. **No generation was attempted.** These are expected blocked preflights, not successful live semantic checks. A successful strict check with the chosen model remains unverified because no model can yet be selected. The runtime was restored to fake-provider off, auth limit 10; backend health, frontend login and proxied CSRF endpoints returned HTTP 200.

## Required next action

In Codex environment settings, review and save the network changes, then publish the environment. The saved additions preserve existing hosts and include:

- `huggingface.co`, `*.huggingface.co`, `*.hf.co` for model downloads.
- `results-receiver.actions.githubusercontent.com` and the observed `productionresultssa15.blob.core.windows.net` for original CI logs/artifacts.

The configuration tool only saves a draft; it cannot apply/publish the running policy. Runtime access must be rechecked afterward. No new provider keys are needed. Then download/verify both models, measure their resources in isolated processes, run full-text/vector/hybrid comparison, select from observed results, and perform strict English/Arabic live checks against that exact model. Accept ADR 0022 only when the actual comparison supports the decision. Manual Slice 5 owner acceptance and design-canvas comparison also remain outside the verified evidence.
