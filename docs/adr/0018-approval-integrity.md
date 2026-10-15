# ADR 0018: Displayed payload integrity and versions

Accepted for Slice 5. Canonical UTF-8 JSON (sorted keys, compact separators) is hashed with SHA-256. The card renders the stored validated payload, not model prose. Decisions carry that hash, the proposal version and a client operation key. The server locks workspace then proposal, reloads current membership/channel access, checks the displayed version/hash and recomputes the stored payload hash before doing anything.

Edit-and-approve checks the original proof first, validates the edited payload, records old/new hashes without text in audit, and executes exactly the edited payload. It may edit/remove existing creation items, not add unseen IDs or redirect an existing-target proposal. Dependency references must still form a bounded DAG. Target versions are captured at proposal creation; edits do not silently rebase stale targets. A changed/deleted target makes the proposal stale with no execution. The human must ask for a new proposal after reviewing the new target.

Source messages are limited to the destination channel and source tasks to its workspace; chips contain IDs/labels, never source message bodies. Hidden channels/workspaces use generic errors. Pending/inbox queries filter channel permissions before pagination. Offline decisions are disabled in the UI and always rechecked server-side.
