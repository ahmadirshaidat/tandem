# ADR 0001: Cookie sessions with rotating refresh tokens

Status: accepted for Slice 1.

Use email/password authentication, Argon2id password hashes, a 15-minute JWT access cookie, and a 14-day opaque refresh cookie. Cookies are httpOnly, host-only and SameSite=Lax. Production sets Secure. Frontend requests pass through Next.js to FastAPI on the same origin; tokens never enter localStorage. JWTs include issuer, audience and a database session ID, and every authenticated request checks that the session remains active.

Store only SHA-256 hashes of random refresh, invitation and password-reset tokens. Refresh rotates the token and revokes the previous session. Reuse revokes its entire session family; logout does the same. Password reset revokes all the user's sessions and outstanding reset links. The frontend serializes refresh attempts within a browser tab. Separate tabs racing refresh may require a new login; a future cross-tab coordinator can improve this without weakening replay protection.

Require a double-submit CSRF token on all mutations, including login and registration, and reject unexpected Origin headers. Reset links expire after 30 minutes and invitations after 7 days. Invitations are single-use, email-bound, and shared manually as links; reissuing or revoking one invalidates earlier links. Only Owners can grant ownership, and the last Owner cannot be demoted or removed. Workspace row locks serialize membership mutations and invitation acceptance.

Auth endpoints share a configurable per-IP sliding-window rate limit. This is appropriate to one backend process in the MVP. Multiple workers/instances require a shared limiter and trusted proxy IP forwarding; do not scale this implementation by simply increasing uvicorn workers. Production email requires configured TLS SMTP. Development uses a private file outbox, with no reset tokens in responses or logs. Email verification, SSO and external identity providers are outside this slice. Unverified email accounts must not be used for production invitations until an email-verification flow is added.
