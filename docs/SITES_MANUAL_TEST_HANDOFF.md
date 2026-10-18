# Tandem manual-test handoff for a new chat

Prepared 18 October 2026 (Asia/Amman). Goal: help the product owner manually test and record Slices 5, 6 and 7. No new features, Slice 8 implementation, public deployment or new cloud resources are authorized by this handoff.

## Repository and acceptance state

- Existing project: <https://github.com/ahmadirshaidat/tandem>.
- Latest reviewed application code before the checklist: `876c6ae`.
- Full evidence: [Slice 7 report](SLICE7_REPORT.md), [CI investigation](slice7-ci-investigation.json), [document-open measurements](slice7-document-open-profile.json).
- Record owner observations in [MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md). All results initially say Not tested; nobody has recorded a manual pass.
- PR #3 is merged into `v1`. PR #4 contains Slice 7, targets `v1`, and remains draft/unmerged until owner acceptance. The requested `main` branch is a testing snapshot of the latest Slice 7 code plus this pending checklist. It is not the canonical `v1` acceptance branch; inspect remote refs and record the tested commit.
- Follow [README](../README.md) and the existing [ADRs](adr/). Preserve the application's architecture and safety rules.

## What Sites can and cannot establish

The Sites runtime guidance states that hosted server code executes in Cloudflare Workers (128 MB per isolate, HTTP-based external connections, no raw TCP). This repository currently runs a Next frontend, Python/FastAPI backend, PostgreSQL/pgvector and a separate Node/Yjs document-sync service through Docker Compose. It has not been ported to the Sites runtime.

Sites alone does not start that Docker/Python/PostgreSQL/Node stack. A working Sites-hosted page without the existing backend and authenticated document WebSockets does not establish manual acceptance for this app. Before starting checks, establish that the original backend, database, local E5 embeddings and document-sync service are actually running and reachable from the chosen browser. Adapting hosting/proxies requires a separate reviewed plan; retain session cookies, CSRF, exact Origin checks, HTTP APIs and WebSocket authorization. Do not silently replace persistence, authentication, providers or collaboration behavior with browser-only substitutes.

The existing supported route for full-stack testing is the local launcher with Docker Desktop, or an existing compatible cloud execution environment as documented in README. A new chat must verify its own runtime; localhost and provider credentials from a prior chat do not automatically carry over. If the new environment cannot run or connect the required services, explain the concrete gap and use the supported launcher route for acceptance.

## Owner test procedure

1. Select the existing Tandem repository and the latest testing revision; record the exact commit, browser URL, device and OS.
2. Read MANUAL_ACCEPTANCE.md. Use synthetic data, real configured provider keys kept server-side, and `AGENT_FAKE_PROVIDER=false`.
3. Start the existing full stack. On Windows: `node infra/dev.mjs`. Wait for database/backend/document-sync health and confirm a real authorized co-editing connection, not just a rendered page.
4. Use the four accounts and two browser sessions from the checklist. Verify E5 is active; record degradation if it is not.
5. Run the starred smoke checks, then the remaining scenarios. Allow 1–2 minutes between Agent requests. Provider quota failures are blockers to record, not a reason to change providers/models.
6. The human tester records observed Pass/Fail/Not tested outcomes, tester identity and time. Automated checks may provide supporting evidence but cannot be relabeled owner testing.
7. Stop merge approval on a failed starred item. Fix the reported issue first and retain the failure evidence.
8. Record the explicit owner decision. Do not merge PR #4 or start Slice 8 based on blank fields, successful CI, a successful Sites deployment or this handoff alone.

## Copy into the new chat

```text
Continue the existing Tandem project at ahmadirshaidat/tandem. Inspect the branches and use the main branch prepared as the manual-testing snapshot. Do not rebuild the product as a new app.

Read README.md, docs/MANUAL_ACCEPTANCE.md, docs/SITES_MANUAL_TEST_HANDOFF.md and docs/SLICE7_REPORT.md first. Help me perform and record the manual checklist for Slices 5, 6 and 7. Keep test results Not tested until I report actual observations.

If using Sites, first verify how the existing Python API, PostgreSQL/pgvector/E5 and Node/Yjs WebSocket service will run and connect. Sites' Worker runtime does not directly run this Docker stack. If the runtime cannot support the existing full app, identify the gap and guide me through the supported local/cloud launcher instead. A static or mocked preview is not acceptance evidence.

Use synthetic data and existing real provider configuration with fake mode off. Never print keys or tokens. Preserve all auth, private-scope and proposal-approval checks. No new features, public deployment, new cloud resources, provider/model substitutions, PR merge or Slice 8 implementation. Record my results and stop on any failed starred item.
```
