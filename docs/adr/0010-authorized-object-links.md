# ADR 0010: Workspace-scoped object links

Status: accepted for Slice 3.

A generic links table stores typed endpoints and a workspace, with a unique directed edge. Message and task endpoints are resolved against the same workspace and the caller's current permissions before insertion and on every read. Document is reserved in storage but is not an available API operation. Every link must include a task. Create-from-message creates the task and its link atomically.

Polymorphic endpoint IDs cannot have a single relational foreign key. The service enforces endpoint existence, workspace identity and access while holding the workspace lock; links retain provenance across soft deletion. Listing links and linked activity filters inaccessible endpoints before pagination. Unknown and inaccessible endpoints use the same error. Workspace events contain task snapshots but no message endpoints, link counts or private link activity. The task title/description explicitly shared by its creator are workspace-visible; linking a private message does not grant access to its channel.
