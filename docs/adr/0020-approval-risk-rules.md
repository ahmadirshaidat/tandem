# ADR 0020: Risk tiers and workspace rules

Accepted for Slice 5. Risk is derived from kind on the server and constrained in PostgreSQL. Create tasks, status/title/description/due-date edits and adding a comment are low risk (Editor minimum). Reassignment, priority changes and deletion are high risk (Admin/Owner only). Viewers never approve or mutate domain data. Self-approval follows the same role rules.

Owner/Admin may tighten create_tasks approval from Editor to Admin or restore Editor. All other rows are read-only; high-risk approval can never be loosened through the API. The current rule is checked under the workspace lock at decision time, including for already-pending proposals. Each rule change is audited. Initial priorities/assignees on newly created tasks remain part of low-risk creation; changing those fields on existing tasks is high risk.

Cancellation is available to the requester (including Viewer) or Admin, and is audited as cancellation while storing rejected state. Rejection otherwise requires the same eligibility as approval. Expired/stale proposals cannot execute; all decision paths preserve current workspace/channel authorization.
