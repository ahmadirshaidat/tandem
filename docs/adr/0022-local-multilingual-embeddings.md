# ADR 0022: Local multilingual E5-small embeddings

**Status: accepted for local model choice and synthetic retrieval quality, 17 October 2026.** Full Slice 6 acceptance still requires successful strict live agent checks and the outstanding manual Slice 5 approval test.

Select `Xenova/multilingual-e5-small`, revision `761b726dd34fb83930e26aab4e9ac3899aa1fa78-q8`, using local CPU ONNX Runtime, a local tokenizer, masked mean pooling and cosine-normalized 384-dimensional vectors. Add `query: ` / `passage: ` prefixes. Keep two inference threads, batches of 16 and 256-token truncation.

[Actual comparison and limitations](../SLICE6_REAL_EMBEDDINGS.md): E5 overall hybrid recall@5 84.44%, MRR .6714; MiniLM 82.22%, .6262; full-text 62.22%, .4892. Both real candidates pass the 70% target. E5 also wins overall vector recall/MRR. MiniLM has higher Arabic hybrid recall (86.67% versus 80%). The unchanged 45-query authored fixture supports this bounded demo choice; it does not establish general production quality.

Both candidates were downloaded and checked against upstream SHA256 values. Conversion cards omit license fields; verify their exact expected original-model links and approved original licenses (E5 MIT, MiniLM Apache-2.0), recording original revisions in each manifest. Fail closed on unexpected links or unapproved licenses. Resource measurements and full manifests are in the linked report/evidence.

Workspace text never leaves the server for embedding inference. Store public weights in ignored persistent caches, outside Git and Docker build context. Missing/failed inference visibly degrades to full-text. Store model ID/version/dimension with each vector and query only the active revision. Maintenance requeues eligible missing-version embeddings. A dimension change requires an explicit schema/index migration.

All four strict English/Arabic live cases verified the E5 vector index without degradation; Groq generation failed with rate limits, so full live semantic acceptance is still open. Earlier network-blocked evidence is retained as history in the embedding gate report.

## Original model license verification

Reverified 17 October 2026 against the original model card at pinned revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`:

- [Original E5-small model card](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md)
- [Raw pinned card](https://huggingface.co/intfloat/multilingual-e5-small/raw/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md)
- Observed YAML metadata: `license: mit`.
- [Selected ONNX conversion card](https://huggingface.co/Xenova/multilingual-e5-small/blob/761b726dd34fb83930e26aab4e9ac3899aa1fa78/README.md) explicitly identifies `base_model: intfloat/multilingual-e5-small`; it does not declare a separate license field.

The verified original-model license is MIT. This records the actual model-card declaration and conversion provenance; it does not invent a license declaration in the conversion repository. [Verification metadata](../slice6-license-verification.json) includes the original card's content hash. The installed manifest records the same original source revision.
