# Hosted packaging checks

18 October 2026, Linux cloud development workspace. Source baseline: Slice 7 manual-testing snapshot `23316008182350037d3b2c0426898772948118f7`, plus the deployment files in this change. This is local container evidence, **not a Railway deployment, Sites publication or owner manual acceptance**.

| Check | Observed result |
| --- | --- |
| Hosted Python image build | Passed, Python 3.12 and locked production dependencies |
| Next.js frontend image build | Passed, Node 24, Next.js production build |
| Bootstrap regression tests | 15 passed; no database/provider calls |
| Email transport and authentication tests | 21 passed; external email mocked, synthetic test database |
| Ruff checks and formatting | Passed for changed Python files |
| JavaScript syntax | Passed for `infra/check_hosted_stack.mjs` |
| Complete isolated stack smoke | One completed pass; [safe metadata](local-stack.json) |

The stack smoke used the newly built backend/frontend images, existing document-sync image, and a fresh pgvector/PostgreSQL 17 database on an isolated Docker network. It exercised a trusted local HTTPS proxy, the containerized Next.js rewrite path, actual CSRF/auth endpoints, secure access and refresh cookies, an unauthenticated 401, workspace/project/document creation, E5 non-degraded status, and a WSS Yjs update acknowledged and read back from PostgreSQL. `/proc/1/status` confirmed all four API UID fields were 10001 after root-owned volume initialization.

E5 cache identity was `Xenova/multilingual-e5-small` / `761b726dd34fb83930e26aab4e9ac3899aa1fa78-q8`. Public model files were copied from the existing verified cache into the isolated volume; startup verified local files and completed inference. **A first-boot upstream model download was not exercised.** Historical embedding/retrieval evidence remains in [the Slice 6 report](../../SLICE6_REPORT.md).

The original smoke used synthetic SMTP configuration. After discovering Railway's Free/Trial SMTP restriction, the updated smoke uses `MAIL_MODE=resend` with a synthetic local-only credential and no external email requests. Fake provider mode is off and the agent worker disabled; provider calls are zero. No real provider keys, normal development database data or user documents are copied into the isolated stack. The driver removes its containers, volume, network and ephemeral TLS files afterward.

Reproduce using the build and smoke commands in [the deployment recipe](../../HOSTED_DEPLOYMENT.md). The smoke script needs the existing E5 cache and `sync` dependencies. It does not substitute for browser/owner testing, and its local-only TLS proxy is not a deployable Sites gateway.

Railway is authenticated. The owner applied the three-service deployment and its two volumes; the database came online and the first API/sync builds failed Dockerfile validation. See [the failure and correction](RAILWAY_BUILD_FAILURE.md). Test email credentials are saved privately. The owner confirmed Free/Trial only with no paid billing; the account balance is not exposed by the connected tools.

Remaining unverified: actual Railway application runtime/private DNS/TLS/WSS, first-boot model download, restart persistence on hosted volumes, real HTTPS email delivery, hosted real-provider agent runs, Sites integration/access boundary, capacity and backups, and all owner checklist results. CI passed for the email transport at `a800337094f8966a03caf03c5d028e07e0fc6b9d` ([run](https://github.com/ahmadirshaidat/tandem/actions/runs/39137522769)); the hosted Dockerfile correction requires its own CI result.
