# ADR 0006: Private image storage and authenticated serving

Status: accepted for Slice 2.

The `ImageStorage` protocol isolates local storage from a future S3-compatible implementation. Local development stores unpredictable 256-bit keys in a dedicated Compose volume; files are not under frontend/public and no storage key is exposed to clients. `ATTACHMENT_DIR` supports native backend development. Requests upload raw binary bytes; a streaming byte limit bounds the body before parsing, so neither MIME nor Content-Length authorizes an upload.

Accept PNG/JPEG/WebP/GIF only, up to 5 MiB and four images per message. Check magic bytes and use Pillow to verify actual image structure and dimensions, rejecting SVG, executables, truncated images and decompression bombs above 20 million pixels. Random file names discard submitted names. Pending uploads belong to one uploader/channel; another user cannot view or claim them. Sending binds all attachments in the message transaction. Access is rechecked after upload and on every retrieval; deleted message attachments are unavailable.

Serve through authenticated `/api/workspaces/{workspace}/channels/{channel}/attachments/{id}`. Apply the current workspace/private-channel check, actual detected image MIME, fixed inline filename, nosniff, sandbox CSP, and no-store. Frontend uses unoptimized Next Image so authenticated bytes are fetched directly rather than through a public optimization cache. Offline text cache stores attachment metadata only; image bytes are not served from an offline/public cache. Failed DB persistence deletes its new file. Abandoned successful uploads need a future retention job; do not silently remove attached files.
