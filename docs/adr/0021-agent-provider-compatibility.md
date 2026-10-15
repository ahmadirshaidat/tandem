# ADR 0021: Model capabilities, validated wire protocol and bounded recovery

Accepted for agent compatibility; no Slice 6 or domain feature is added.

## Problem and evidence

The old agent used JSON-object mode with a dynamic `arguments` dictionary for every provider. Groq `openai/gpt-oss-20b` returned HTTP 400 `tool_use_failed` on planning. Gemini `gemini-3.8-flash` returned generation 504s despite a successful model lookup. Fake-provider tests do not establish compatibility with either model.

Use Groq's [official SDK parameter documentation](https://github.com/groq/groq-python/blob/main/src/groq/types/chat/completion_create_params.py) and the authenticated `/openai/v1/models` catalog. The SDK documents preferred `json_schema` output on supported models, `tool_choice=none`, and GPT-OSS low/medium/high reasoning. The current catalog advertises `tools`, `json_mode`, `structured_outputs` for GPT-OSS 20B/120B. Qwen 3.8 27B advertises tools/JSON mode but not schema-constrained output. Llama 3.3 70B and Qwen 3 32B were absent and were not guessed into the active catalog.

Google's [official SDK JSON-schema documentation](https://github.com/googleapis/python-genai/blob/main/README.md#json-response-schema) documents MIME JSON plus `response_json_schema`, including Pydantic schemas. Both requested Gemini model IDs passed model lookup. Schema generation was tested rather than inferred from lookup. Direct documentation sites were blocked by the environment's egress policy; the official GitHub sources and API catalog were accessible. The two documentation host additions are saved in the environment draft; no proxy bypass or TLS weakening was used. Evidence stores public source URLs/checksums, catalog features and real probe results.

## Capability table and model selection

The explicit table is in `backend/app/ai/capabilities.py`. No SDK native function execution is enabled.

| Provider/model | Wire output format | Native tool capability | Observed planning-turn probe |
|---|---|---|---|
| Groq `openai/gpt-oss-20b` | Strict JSON schema, low reasoning | Advertised by catalog | Passed; full-flow attempts later hit denied invented IDs, premature prose and rate limits |
| Groq `openai/gpt-oss-120b` | Strict JSON schema, low reasoning | Advertised by catalog | Passed; completed real English proposal/approval with first-read enforcement |
| Groq `qwen/qwen3.8-27b` | JSON object, reasoning none | Advertised by catalog | Passed; only a planning turn tested, not full approval |
| Gemini `gemini-3.8-flash` | MIME JSON plus JSON schema | Native tools not used/assumed | Failed after three bounded attempts: 504, 504, 503 |
| Gemini `gemini-3.5-flash` | MIME JSON plus JSON schema | Native tools not used/assumed | Passed after one 503 retry; real English and Arabic approvals completed |
| Existing DeepSeek/OpenAI configured models | Existing JSON modes | Native tools not used | No workspace-data live test in this work |
| Unlisted models | Conservative JSON-object compatibility | Unknown | No strict-output capability assumed |

Choose **Groq GPT-OSS 120B** and **Gemini 3.5 Flash** as configuration defaults. 120B has observed end-to-end completion; 20B's successful isolated turn is insufficient to approve its full workflow. These are account-specific observations, not a general model benchmark or a claim that 20B lacks structured-output support. Gemini 3.8 still fails generation under bounded recovery. No Gemini 2.5 live calls are made; agent transport rejects that family. Configuration remains overridable, so existing deployments explicitly pinning old IDs must update their settings and restart the backend.

Model defaults are shared with the existing provider configuration, including Try AI; the trial endpoint remains isolated and keeps its 512-token default and original retry/fallback behavior. Agent output has its own 2,048-token bound and 15-second per-attempt timeout (`AGENT_MAX_OUTPUT_TOKENS`, `AGENT_PROVIDER_TIMEOUT_SECONDS`). No dependency or migration is introduced.

## Wire format and server validation

Strict structured-output APIs need sealed object schemas. Dynamic tool arguments cannot be sealed to a fixed set of keys across the closed registry. The wire format therefore uses `calls: [{name, arguments_json}]` plus `answer`; arguments are a JSON-encoded string. Every object in the strict wire schema is sealed. The server decodes arguments into the existing internal `ToolRequest`/`AgentTurn`, then the unchanged registry's individual Pydantic schemas and authorization services validate every call.

The first turn must read context: nonempty calls, empty answer, and only read names in the response enum. Proposal descriptions become available after current project/task IDs have been read. Local validation enforces offered names too, including repaired or legacy responses; this does not replace the closed execution registry or expand permissions. It prevents an apparently valid prose plan from being mistaken for a stored proposal.

After all proposed calls pass server validation and their proposal records commit, the server posts the existing human-review explanation without another LLM request. A final model call can otherwise fail with a quota error after a valid proposal was already stored. The existing `finish` permission/fingerprint checks still run; no task/comment execution or approval is performed automatically.

Repair is deliberately limited to Markdown JSON fences and trailing commas outside quoted strings. Duplicate keys, non-finite values, forbidden fields, unknown/unoffered calls and truncated content are rejected. The server never evaluates code, invents missing fields or drops fields to make validation pass. Valid legacy JSON turns remain supported under the original strict Pydantic model.

## Bounded recovery and privacy

- `tool_use_failed` or `json_validate_failed`: one retry with a shorter fixed instruction. Failed text is never included in the retry prompt. If the second error includes a bounded `failed_generation`, it may be parsed transiently, but only a fully Pydantic-valid turn can be used. Invalid repairs fail closed.
- Gemini HTTP 5xx/504: at most two retries, with 0.5 and 1 second exponential delays, SDK retries disabled. Authentication, non-recoverable 4xx and 429 are not automatically retried. No key rotation, model hopping or network bypass is used to evade quotas.
- The worker's per-call allowance includes explicit retries and stays bounded by the existing run deadline. An in-flight SDK thread may finish after cancellation within its transport timeout, but cannot publish a late result or execute tools after the guard/deadline is lost.
- Safe errors retain only allowlisted category, HTTP status, attempt count, observed token counts and a fixed validation issue (`schema`, `json_syntax`, `unoffered_call`, `read_required`). Audit never stores failed generation text, prompts, responses or credentials.
- Token usage covers provider-reported successful generations. Failed HTTP attempts may have unreported usage; reports explicitly mark that uncertainty rather than inventing zero billed tokens.

## Verification and limits

Mocked regressions cover strict formats, retry caps/backoff, failure classification, repair validation, duplicate/non-finite/forbidden fields, secret redaction, first-read enforcement, offered calls and completing a stored proposal without a redundant provider request. Ordinary backend tests clear real injected keys; live scripts are separate.

Real planning probes, all four strict provider/language commands and the isolated structured-tool checker are recorded in `docs/SLICE4_LIVE_CHECK.md` and `docs/live-provider-results.json`. Model 3.8 failure and intermediate quota/protocol failures remain in the evidence even when later cases succeed. A small synthetic acceptance run does not establish production reliability; the product owner's manual UI acceptance remains separate.
