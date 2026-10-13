# ADR 0003: Server-side provider trials

Status: accepted for the user's request to try Groq, Gemini and DeepSeek and prepare a future main key.

Keep every credential on the backend, represented by Pydantic SecretStr and supplied through private local configuration or secure cloud bindings. Never accept provider URLs or API keys from the trial screen. Use fixed destinations, explicit timeouts, bounded input/output, and no implicit SDK retries. Do not disable TLS verification. OpenAI's Python SDK handles Responses for optional OpenAI and compatible Chat Completions for Groq/DeepSeek; Google's Gen AI SDK handles Gemini. Codex is the app's development tool, separate from this runtime provider layer.

Expose workspace-scoped trial endpoints to Owners/Admins only. All calls check authentication, current workspace membership, role and CSRF before contacting a provider. Rate-limit each user/workspace and bound concurrent calls in the single backend process. Do not send workspace content, retrieved context or credentials in the prompt, or attach tools. Check membership again before returning a result.

Automatic mode starts with the configured primary and tries available alternatives on provider access, quota/billing, connectivity or service failures. An explicitly selected provider never falls back. Invalid requests stop automatic retries to avoid rebilling the same unsupported prompt. Persist append-only trial metadata through the API: workspace, actor, status, safe attempt categories, latency and token counts. Do not persist question/answer text, credentials or upstream error bodies.

This feature is an isolated trial, not the full Slice 4 shared agent or its complete Audit Log. Native mobile, agent tools, conversations, RAG, approvals, real-time collaboration and external public deployment remain separate work. Provider model IDs are configurable because model availability changes; discovery and real generation checks are reported separately.
