# ADR 0017: Proposal records and state transitions

Accepted for Slice 5. The agent may persist validated proposal records, never task/comment mutations. Six fixed kinds map server-side to low/high risk. Workspace-scoped proposal and ordered item records preserve the exact canonical payload, its SHA-256, sources, target versions, requester, decision and execution metadata. A run plus canonical tool key is unique so repeated propose calls cannot duplicate a proposal. A channel has a bounded pending cap and a seven-day default expiry.

States are proposed → approved → completed, or rejected/failed/expired/stale. Cancellation uses rejected with a distinct cancellation audit action, preserving the specified state vocabulary. Human approval and execution happen in one transaction: approved is still recorded in the journal/audit before completed. A savepoint permits all task work to roll back while preserving a failed decision record. Expiry runs in the existing worker and is rechecked on decisions, so a delayed worker cannot authorize an expired proposal.

Task dependencies use directional `links.relation=depends_on` (dependent → prerequisite); ordinary existing links default to related. Initial proposal dependencies are bounded to its own new items and must form a DAG. No document or memory operations are introduced.
