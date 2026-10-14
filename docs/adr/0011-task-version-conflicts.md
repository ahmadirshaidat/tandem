# ADR 0011: Task versions and replay

Status: accepted for Slice 3.

Every task mutation that changes stored state increments its integer version and writes activity and a durable workspace event in the same transaction. Edits, moves, deletion and the primary task in a link creation carry the expected version. Bulk edits validate all versions before writing. Comments have their own edit/delete version; comment changes also advance the task version.

A stale expected task version returns HTTP 409 with `error.details.kind=task_conflict` and `current`, the authorized current task snapshot. The UI retains the user's draft, offering Keep mine (retry the intended fields against that current version) and Take server's (discard the draft). Further conflicts require another explicit choice.

Workspace subscription uses `workspace_seq`, independent of `last_seq` for channels. The snapshot watermark precedes the list query so concurrent changes cannot be missed; the client deduplicates snapshots by task version and consumes ordered event sequences. Reconnect replays journal rows strictly after its last accepted cursor. The existing gateway/fanout rechecks session and membership on journal reads and immediately before delivery. No events with private link endpoints are broadcast. An existing metadata-only workspace subscription without `workspace_seq` retains its Slice 2 behavior.
