# ADR 0025: Durable source revisions and indexing lifecycle

Accepted for Slice 6. Extend the existing PostgreSQL worker; do not create a second daemon or repurpose an AgentRun with a fabricated human trigger.

`memory_sources` is a coalescing durable queue and indexing state per channel/project. Database triggers on channels, messages, projects, tasks and task comments update its revision in the same transaction as the domain change. Workers claim with `FOR UPDATE SKIP LOCKED`, snapshot source content and revision, release database locks for local embedding, then publish only if the revision is still current. Stale claims are recoverable; failures use bounded retry and fixed safe categories.

Query-time checks require indexed_revision = revision and idle status. Edits/deletions therefore remove stale results immediately, before reindexing finishes. Rebuild the affected channel/project to propagate changes to overlapped chunks. This favors straightforward deletion correctness for small workspaces over high throughput for very large channels; source rebuild costs must be measured and reported. Message windows never span channels. Task chunks include comments and status. Content hashes preserve unchanged record IDs/vectors and explicit forget tombstones survive reindexing.

Store a model ID, pinned version and dimension on each vector. A newly configured model version queues missing vectors; queries use only the active version. The initial HNSW column is dimension 384; a future dimension change requires an explicit schema/index migration rather than mixing dimensions. Indexing and retrieval use only local model files; public weights are downloaded separately, never on a workspace-content request.

Backfill/reindex use the same queue and current settings. Retention removes only derived memory. Source data, audit records and proposal execution remain outside the indexing mutation boundary. No document indexing is included.
