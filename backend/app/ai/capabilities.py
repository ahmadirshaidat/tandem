"""Explicit agent wire capabilities; no native function execution is enabled.

Sources and live catalog evidence are recorded in ADR 0021. Unknown models use
the existing JSON mode conservatively, never an assumed strict schema feature.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    format: str = "json_object"
    native_tools: bool | None = None
    reasoning_effort: str | None = None


MODEL_CAPABILITIES = {
    ("groq", "openai/gpt-oss-20b"): Capability("json_schema", True, "low"),
    ("groq", "openai/gpt-oss-120b"): Capability("json_schema", True, "low"),
    # Groq's current catalog advertises tools/json_mode, NOT structured_outputs.
    ("groq", "qwen/qwen3.8-27b"): Capability("json_object", True, "none"),
    ("gemini", "gemini-3.8-flash"): Capability("gemini_json_schema"),
    ("gemini", "gemini-3.5-flash"): Capability("gemini_json_schema"),
    ("openai", "gpt-5.5"): Capability("responses_json_object"),
    ("deepseek", "deepseek-flash"): Capability("json_object"),
}


def capability(provider, model):
    return MODEL_CAPABILITIES.get((provider, model), Capability())
