# Current hosted release — 18 October 2026

The [existing private Tandem Site](https://tandem-workspace-preview.ahmad-majed.chatgpt.site)
is published with a Worker gateway to Railway. Its owner-only audience is unchanged.
The former static preview is no longer the deployed entry point.

## Exact deployment state

Railway project `58f9f37c-aa18-46e7-8e73-0ab6873ede54`, environment
`3ad12379-4643-441c-aea0-9868d6c863a9` (`manual-testing`). All four services
report ONLINE, one running replica, SUCCESS deployments, and zero current
warning/critical issues. No staged changes or pending work remained at verification.
Historical failure counts refer to the repaired Dockerfile failures.

| Service | Deployed source | Successful deployment |
| --- | --- | --- |
| db | pgvector/pgvector:pg17 | `b3ed252e-d576-4098-ad94-3b03d3a31fb4` |
| backend | `2971b3257242e21daeba7c0d79eff31404ce3457` | `7a3334f7-c132-48d8-8140-e7f6255978fd` |
| document-sync | `2971b3257242e21daeba7c0d79eff31404ce3457` | `462ba210-8b0d-4bc3-91aa-aec2a81d4b73` |
| frontend | `20dddf5b29b1b8f01c308b4f7fa7999c3b2d4e87` | `f08f9005-d41e-4e8d-9ea4-647280130494` |

Backend services remain pinned to the earlier successful source. The later commit
adds the frontend guard, Worker source/tests and documentation; it changes no
Python or document-sync runtime code. Only the guarded frontend has a public domain.
Database/API/sync have no public domains or TCP proxies. The two existing 500 MB
volumes remain attached to the database and API. No paid-plan upgrade was made;
Free/Trial credits only, $0 out-of-pocket authorization. Balance and longevity
are not exposed by the connected tools.

Sites:

- Project: `appgprj_6ad1060cb99c81919c7f5f00ce435bec`.
- Pushed source: `bfdf7c434d3a24632c072397fe0ce77ae1fe98d0` in its own Sites source repository.
- Saved version: `appgprj_6ad1060cb99c81919c7f5f00ce435bec~appgver_fab0ef67c344819199707e3fc40a08dc`.
- Deployment: `appgdep_6ad4e7351b008191bf092ed227af436e`, **succeeded**, 15:35:30 UTC.
- Runtime environment revision: 1. Upstream and gateway secret are stored privately.

The first archive was rejected before a version was saved because its entry point
lacked the required `dist/` prefix. The corrected archive contained
`.openai/hosting.json` and `dist/server/index.js`, built from the exact pushed
source above. The official source helper was unavailable in this execution
workspace; a local credential-isolated Git runner and the documented Worker ESM
artifact layout were used. Credentials passed through hidden stdin and child
process memory only. No credential was written to source, shell arguments or logs.

## Verification

- Railway reports every current service successful and healthy. API startup logs
  show application startup complete and Uvicorn running. Bootstrap requires E5
  validation/inference before startup; the hosted model revision was not read back.
- After publication, Railway HTTP logs show HTTP 200 for app pages and assets,
  including `/`, `/signup`, `/forgot-password`, fonts and Next chunks. This proves
  the deployed gateway reaches the guarded frontend. It does not prove a complete
  login or document-editing session.
- The native Sites operation confirms successful publication at the existing URL.
  Its audience remained owner-only. Browser handoff was queued successfully.
- Four Worker contract tests passed: Sites credential isolation, Tandem cookies,
  CSRF/RSC headers, WebSocket response preservation, fixed upstream routing,
  redirects and redacted failures.
- Guarded frontend image built; frontend lint passed. The isolated Docker stack
  passed actual HTTPS registration/login, secure cookies, unauthenticated denial,
  direct HTTP/WebSocket rejection, E5 active, API UID 10001, and a persisted WSS
  Yjs edit. [Safe metadata](local-gateway-stack.json). No mail/provider requests.
- [CI run 39140809420](https://github.com/ahmadirshaidat/tandem/actions/runs/39140809420)
  passed on exact application head `20dddf5b29b1b8f01c308b4f7fa7999c3b2d4e87`:
  backend 173 tests, bootstrap 15 tests, frontend checks, 11 browser tests,
  Node CRDT tests, four gateway tests and Windows launcher smoke.

## Still unverified or blocked

- **Agent runs are unavailable:** the hosted agent worker is disabled until
  portable real Groq/Gemini credentials are supplied privately. Fake mode is off;
  no provider/model substitution was made. Agent-dependent acceptance is blocked.
- **Real email receipt:** the supplied test Resend key and sender are configured
  privately, but no real reset email was sent/received. The trial sender can send
  only to its Resend account owner until a sender domain is verified.
- **Live authenticated API and WebSocket interactions:** the complete path passed
  locally; no authenticated browser login or co-editing session was performed on
  the hosted Site. Managed browser control was unavailable, so no screenshots or
  manual-browser pass are claimed. Live logged-out Sites denial and direct
  Railway bypass denial were not independently exercised over public TLS.
- Hosted model manifest/revision readback, restart persistence, volume backup and
  restore, resource capacity, trial credit lifetime and production operations.
- All owner manual acceptance for Slices 5–7. The checklist remains Not tested.
  PR #4 remains draft/unmerged; neither deployment nor CI approves that merge.

Code and this report are in [draft PR #5](https://github.com/ahmadirshaidat/tandem/pull/5).
The report commit may be newer than the pinned runtime commits; it changes docs only.
