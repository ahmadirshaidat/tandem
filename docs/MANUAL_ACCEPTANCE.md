# Manual Acceptance: Slices 5, 6 and 7

**Status: pending owner testing. No manual acceptance has been recorded.**

Checklist prepared on 18 October 2026 (Asia/Amman). This date is not a test execution date. Automated CI, scripted live checks and browser automation do not fill this record. The human tester records actual observations below.

Items marked ★ are the minimum smoke test (estimated 12 minutes). The full checklist is estimated at 40 minutes, plus any provider rate-limit waits. Every item starts as **Not tested**.

## Setup (do once)

- Run the existing app with real provider keys in the private `.env`, fake provider mode **off** (`AGENT_FAKE_PROVIDER=false`), and synthetic data only. Keep keys out of chat, screenshots, logs and Git.
- Use four accounts in one workspace: **Owner/Admin**, **Editor**, **Viewer**, and an **outsider** who is excluded from the private channel and private document. Use two browsers (one private window) so two users are online at the same time.
- Wait 1–2 minutes between Agent requests. If rate-limited, record the blocker and wait as instructed by the provider; preserve the configured provider/model.
- On Windows, run `node infra/dev.mjs` and confirm database, backend and document-sync all become healthy.
- See [new-chat and Sites handoff](SITES_MANUAL_TEST_HANDOFF.md) before selecting a hosting/testing environment.

## Slice 5: proposals and approvals

| # | Test | Result |
| --- | --- | --- |
| 1 ★ | Ask `@Agent` to create a task. A proposal card appears and **no task exists** on the board before approval. | Not tested |
| 2 ★ | Edit one proposal field, then approve. The task matches the reviewed edit, the second user sees it, and Audit records it. | Not tested |
| 3 | Repeat step 1 in Arabic. Text is Arabic, direction is correct, and approval works. | Not tested |
| 4 | Reject a proposal. Nothing changes. | Not tested |
| 5 ★ | Ask to reassign a task (high risk). The Editor sees only an Admin can approve; Owner/Admin approves; Viewer cannot approve anything. | Not tested |
| 6 ★ | Click Approve twice quickly. Only one task is created. | Not tested |
| 7 | Go offline. Approval buttons are disabled. | Not tested |
| 8 | Open a 390 px window or phone. The review sheet is usable. | Not tested |

## Slice 6: search and memory

| # | Test | Result |
| --- | --- | --- |
| 9 | Search for a past bug in English and Arabic. Highlighted snippets and direction are correct. | Not tested |
| 10 ★ | As the outsider, search text found only in a private channel. No result or existence hint appears. | Not tested |
| 11 | As Owner, inspect Memory stats, re-index, include-private and forget preview. Cancel once, then confirm on a test source only. | Not tested |
| 12 | Ask about similar bugs. Source chips open items the user is allowed to see. | Not tested |

## Slice 7: documents

| # | Test | Result |
| --- | --- | --- |
| 13 ★ | Two users type in the same paragraph concurrently. Both screens end identical. | Not tested |
| 14 | One user edits offline while the other edits online. Reconnect preserves both changes. | Not tested |
| 15 ★ | Create a private document. The outsider sees no list/search result; its direct link denies access without revealing details. | Not tested |
| 16 ★ | Request an Agent Suggestion. Text stays unchanged until acceptance; after acceptance it changes and history records human approval and the Agent. | Not tested |
| 17 | Change the suggested sentence before accepting the old Suggestion. It becomes stale and applies nothing. | Not tested |
| 18 | Name a version, edit more and restore the older version. History remains complete and restore creates a new version. | Not tested |
| 19 | Write Arabic and mixed Arabic/English. Direction looks correct in editor, Suggestions and history. | Not tested |
| 20 | As Viewer, try typing. No edit is saved after reload. | Not tested |
| 21 | Use a document in a 390 px window or phone, including its offline banner. | Not tested |

The accepted MVP Suggestion limit is one text range within one XML text node. Cross-paragraph, heading and formatting-node rewrites are unsupported; record a request outside that scope separately rather than marking it as a supported capability.

## Record — tester to complete

Use **Pass**, **Fail** or **Not tested** for every numbered result. Keep this block and the tables consistent.

```text
Tester: Not recorded
Date: Not recorded
Device and browser(s): Not recorded
Operating system: Not recorded
Launcher or cloud: Not recorded
Provider and model: Not recorded
Fake mode off: Not verified
Synthetic data only: Not verified
Tested Git commit: Not recorded
Tested app URL (no tokens or credentials): Not recorded

Slice 5: 1 Not tested  2 Not tested  3 Not tested  4 Not tested
         5 Not tested  6 Not tested  7 Not tested  8 Not tested
Slice 6: 9 Not tested  10 Not tested  11 Not tested  12 Not tested
Slice 7: 13 Not tested  14 Not tested  15 Not tested  16 Not tested
         17 Not tested  18 Not tested  19 Not tested  20 Not tested  21 Not tested

Failures and notes (actual behavior, expected behavior, safe screenshot/evidence):
Not recorded

Windows launcher tested: Not tested (result: Not recorded)
Gemini fallback tested: Not tested (result: Not recorded)

Decision: do not merge — manual acceptance pending
```

If any starred item fails, **do not merge**. Send the failure and reproduction details to Codex to fix that issue first. Not tested is not Pass. Record any untested non-starred scenarios and the owner's explicit scope decision; the smoke checklist alone must not be presented as full acceptance.

Slice 8 remains gated by the recorded owner results and PR #4 merged into `v1` with green CI. Publishing a testing branch or preparing this checklist does not satisfy those conditions.
