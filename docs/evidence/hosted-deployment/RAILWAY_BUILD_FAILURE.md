# Railway build failure and correction

18 October 2026. Project `58f9f37c-aa18-46e7-8e73-0ab6873ede54`, environment `manual-testing`. The owner applied the prepared deployment; it is no longer awaiting the earlier tool approval.

At source commit `a800337094f8966a03caf03c5d028e07e0fc6b9d`:

| Service | Deployment | Observed result |
| --- | --- | --- |
| PostgreSQL | `b3ed252e-d576-4098-ad94-3b03d3a31fb4` | SUCCESS, one running replica |
| Python API | `8c4c075d-0b97-4e5c-8c85-c64bfd79fbe8` | FAILED during BUILD_IMAGE validation |
| Document sync | `712a8b18-656b-4cf1-b8fd-7d5ebfb3f1ac` | FAILED during BUILD_IMAGE validation |

Both failed with the same safe error metadata:

```text
dockerfile invalid: flag '--mount=type=secret,id=proxy_ca' is missing a type=cache argument (other mount types are not supported)
```

The API error referenced lines 2 and 7; sync referenced line 4. Neither application reached startup, so this failure does not establish any problem with its database credentials, email key, migrations or model initialization. The development-only CA secret mount worked in local BuildKit, but Railway's builder rejects it.

The correction removes secret mounts from `infra/Dockerfile.hosted-backend` and `frontend/Dockerfile`, and supplies `sync/Dockerfile.hosted` for the hosted Node service. `compose.hosted.yaml` and Railway's sync Dockerfile setting select the new hosted file. The original development Dockerfiles keep their proxy certificate handling. `infra/cloud_build.py --hosted ...` adds temporary CA mounts only to the Dockerfile streamed to local Docker for verification; it never modifies the hosted source or copies session CA material into image layers.

Local and remote recovery results must be verified separately. A successful local image build does not establish a successful Railway deployment. Sites wiring, real email receipt, agent-provider configuration and owner acceptance remain separate pending checks.
