# ADR 0007: Single-instance fan-out behind an interface

Status: accepted for Slice 2.

Use a process-local `Fanout` protocol (`listen`, `publish`) with a thread-safe callback registry. SQLAlchemy after-commit wakes each socket's event loop for any transaction, including session and workspace membership changes. The gateway checks session and topic access before reading and before transmitting journal messages; unauthorized subscriptions are removed and expired/revoked sessions close. A 500 ms safety poll catches external database changes and typing expiry. Normal application mutations wake immediately; delivery does not wait for the poll.

Durability and replay live in PostgreSQL, so wake coalescing is safe. A connection lock serializes commands, catch-up, and live delivery. Presence and typing remain ephemeral and are revalidated, not persisted in events. No message bodies enter fan-out callbacks or structured request logs. Disconnect cancels the receiver/delivery tasks and removes its listener and ephemeral state.

No Redis is needed for a single backend instance. A future Redis transport can implement this interface, publish workspace/channel wake hints after commit, and share presence/rates/connection limits. Until then, never start multiple Uvicorn workers and assume cross-worker events or revocations work. PostgreSQL journal retention, N+1 history serialization optimization and distributed presence are future scale work, not a hidden dependency for this slice.
