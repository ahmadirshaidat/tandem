# ADR 0026: Derived-memory retention and explicit forgetting

Retention is forever (default), 365 days or 90 days. Apply the cutoff in indexing, retrieval SQL and periodic expiry. Retention deletes derived memory/vectors only; it never deletes original messages, tasks, task comments, audit history or proposals. Message windows exclude expired messages before creating overlapped chunks. Task retention is measured from the task's creation date.

Owner/Admin forgetting selects an accessible channel/project or up to 100 explicit records. No free-text topic deletion exists. Preview only currently authorized records. Bind the confirmation to user, workspace, selected IDs/content hashes and a five-minute signed expiry. Lock workspace then source, refresh after locks, and reject a changed preview. Audit only selection scope/count and IDs, never content.

Record forgets preserve stable suppression keys through reindexing. Forgetting a source turns its inclusion off; only a deliberate later include toggle permits new source indexing. Source originals remain available through normal domain APIs. Turning off private indexing or a source removes its derived records immediately. All settings and deletion actions are audited.

Resolution summaries default off. On a new completed bug after opt-in, an eligible public project channel may receive an extractive add-comment proposal through the existing proposal service. The summary copies recorded facts for review, uses no parallel LLM provider path and creates no comment until authenticated human approval. Deduplicate by completion history, including subsequent comment/version updates. If settings, channel eligibility, permissions or pending limits prevent a proposal, fail closed.
