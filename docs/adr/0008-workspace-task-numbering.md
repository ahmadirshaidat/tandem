# ADR 0008: Immutable task numbers per workspace

Status: accepted for Slice 3.

Lock the workspace row, recheck membership, and increment `workspace_task_state.last_number` in the same transaction as task creation, initial activity and its workspace event. One counter covers bugs and tasks; the prefix reflects the initial type. Changing type or project never changes the key. Unique workspace/number and workspace/key constraints guard against duplicate writes. A failed transaction rolls the increment back. Soft deletion preserves keys and activity; deleted numbers are never reused.

The workspace lock also serializes membership changes and task writes. This deliberately favors correctness for the MVP over parallel writes within one workspace. The same state row holds an independent workspace journal sequence; channel sequence numbers remain separate.
