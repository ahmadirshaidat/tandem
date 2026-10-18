# Tandem manual-test handoff for a new chat

Prepared 18 October 2026 (Asia/Amman). Goal: help the product owner manually test and record Slices 5, 6 and 7. This acceptance handoff does not authorize new features, Slice 8, extra resources, paid billing or a wider Sites audience. The owner separately authorized the existing Free/Trial Railway deployment and private Sites connection; see HOSTED_DEPLOYMENT.md for current evidence.

## Repository and acceptance state

- Existing project: <https://github.com/ahmadirshaidat/tandem>.
- Historical application review before the checklist: `876c6ae`. The hosted release adds deployment/email transport fixes; use the exact pinned commits in the hosted report for hosted testing.
- Full evidence: [Slice 7 report](SLICE7_REPORT.md), [CI investigation](slice7-ci-investigation.json), [document-open measurements](slice7-document-open-profile.json).
- Record owner observations in [MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md). All results initially say Not tested; nobody has recorded a manual pass.
- PR #3 is merged into `v1`. PR #4 contains Slice 7, targets `v1`, and remains draft/unmerged until owner acceptance. The requested `main` branch is a testing snapshot of the latest Slice 7 code plus this pending checklist. It is not the canonical `v1` acceptance branch; inspect remote refs and record the tested commit.
- Follow [README](../README.md) and the existing [ADRs](adr/). Preserve the application's architecture and safety rules.

## What Sites can and cannot establish

The Sites runtime guidance states that hosted server code executes in Cloudflare Workers (128 MB per isolate, HTTP-based external connections, no raw TCP). This repository currently runs a Next frontend, Python/FastAPI backend, PostgreSQL/pgvector and a separate Node/Yjs document-sync service through Docker Compose. It has not been ported to the Sites runtime.

Sites alone does not start that Docker/Python/PostgreSQL/Node stack. A working Sites-hosted page without the existing backend and authenticated document WebSockets does not establish manual acceptance for this app. Before starting checks, establish that the original backend, database, local E5 embeddings and document-sync service are actually running and reachable from the chosen browser. The current hosted gateway must retain session cookies, CSRF, exact Origin checks, HTTP APIs and WebSocket authorization. Do not silently replace persistence, authentication, providers or collaboration behavior with browser-only substitutes.

The existing private Site now has a deployed gateway to the Railway deployment;
current deployment status and limitations are in [HOSTED_DEPLOYMENT.md](HOSTED_DEPLOYMENT.md)
and [its evidence](evidence/hosted-deployment/RAILWAY_BUILD_FAILURE.md).
The Python API, database and document sync have successful current deployments.
Keep the Site's owner-only audience and the frontend's server-only gateway guard.
A new chat should inspect that release before creating or rebuilding anything.
Real agent-provider credentials are still missing on Railway: fake mode is off
and the worker is disabled. Agent-dependent starred items cannot pass until that
configuration is supplied privately and real-provider behavior is verified.

The local launcher with Docker Desktop remains a separate full-stack test route.
A new local/cloud execution environment must verify its own services and keys;
localhost and credentials from a prior chat do not automatically carry over.

## Owner test procedure

1. Select the existing Tandem repository and the latest testing revision; record the exact commit, browser URL, device and OS.
2. Read MANUAL_ACCEPTANCE.md. Use synthetic data, real configured provider keys kept server-side, and `AGENT_FAKE_PROVIDER=false`.
3. Use the current hosted Site and record its deployed revision, or start the existing local full stack. On Windows: `node infra/dev.mjs`. Wait for database/backend/document-sync health and confirm a real authorized co-editing connection, not just a rendered page.
4. Use the four accounts and two browser sessions from the checklist. Verify E5 is active; record degradation if it is not.
5. Run the starred smoke checks, then the remaining scenarios. Allow 1–2 minutes between Agent requests. Provider quota failures are blockers to record, not a reason to change providers/models.
6. The human tester records observed Pass/Fail/Not tested outcomes, tester identity and time. Automated checks may provide supporting evidence but cannot be relabeled owner testing.
7. Stop merge approval on a failed starred item. Fix the reported issue first and retain the failure evidence.
8. Record the explicit owner decision. Do not merge PR #4 or start Slice 8 based on blank fields, successful CI, a successful Sites deployment or this handoff alone.

## Copy into the new chat

```text
Continue the existing Tandem project at ahmadirshaidat/tandem. Inspect the current deployment report and pinned release on deploy-railway; main remains the earlier manual-testing snapshot. Do not rebuild the product as a new app.

Read README.md, docs/MANUAL_ACCEPTANCE.md, docs/SITES_MANUAL_TEST_HANDOFF.md and docs/SLICE7_REPORT.md first. Help me perform and record the manual checklist for Slices 5, 6 and 7. Keep test results Not tested until I report actual observations.

If using Sites, read docs/HOSTED_DEPLOYMENT.md first and inspect the existing Railway services and private Site gateway. Do not create another stack or replace it with a static preview. Verify actual login and document WebSockets. The hosted agent worker is disabled pending portable provider credentials; record agent checks as blocked until privately configured and tested.

Use synthetic data and existing real provider configuration with fake mode off. Never print keys or tokens. Preserve all auth, private-scope and proposal-approval checks. No new features, public deployment, new cloud resources, provider/model substitutions, PR merge or Slice 8 implementation. Record my results and stop on any failed starred item.
```
