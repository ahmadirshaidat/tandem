"""Bounded, synthetic planning-turn model probes. Prints safe metadata only.

backend/.venv/bin/python infra/check_agent_models.py --output /tmp/agent-models.json
No tools are executed; this is not an end-to-end approval check.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent.llm import WorkspaceLLM
from app.agent.tools import REGISTRY, descriptors
from app.ai.capabilities import capability
from app.ai.providers import ProviderFailure, check_model, provider_key
from app.core.config import settings

CASES = [
    ("groq", "openai/gpt-oss-20b"),
    ("groq", "openai/gpt-oss-120b"),
    ("groq", "qwen/qwen3.8-27b"),
    ("gemini", "gemini-3.8-flash"),
    ("gemini", "gemini-3.5-flash"),
]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path)
parser.add_argument("--model", choices=[m for _, m in CASES])
args = parser.parse_args()
rows = []
for provider, model in CASES:
    if args.model and args.model != model:
        continue
    row = {
        "mode": "live",
        "probe": "planning_turn_only",
        "provider": provider,
        "model": model,
        "format": capability(provider, model).format,
    }
    original = getattr(settings, provider + "_model")
    start = time.perf_counter()
    try:
        setattr(settings, provider + "_model", model)
        if not provider_key(provider):
            row.update(status="skipped_no_key")
            continue
        row["model_discovery"] = check_model(provider)
        turn, completion = WorkspaceLLM().turn(
            provider,
            {
                "question": "Synthetic test: plan JWT authentication as two tasks. Read the available projects and tasks before proposing. Never execute changes.",
                "tools": descriptors(),
                "results": [],
            },
        )
        valid = bool(turn.calls) and all(c.name in REGISTRY for c in turn.calls)
        if valid:
            for call in turn.calls:
                REGISTRY[call.name].model_validate(call.arguments)
        row.update(
            status="passed" if valid else "unexpected_turn",
            protocol_valid=True,
            tool_names=[c.name if c.name in REGISTRY else "unregistered" for c in turn.calls],
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            attempts=completion.attempts,
            repaired=completion.repaired,
            safe_errors=completion.safe_errors,
            failed_attempt_token_usage="not_reported"
            if completion.safe_errors
            else "not_applicable",
        )
    except ProviderFailure as error:
        row.update(
            status="failed",
            category=error.category,
            http_status=error.status,
            attempts=error.attempts,
            input_tokens=error.input_tokens,
            output_tokens=error.output_tokens,
            safe_errors=error.safe_errors,
            failed_attempt_token_usage="not_reported",
        )
    except (ValueError, TypeError):
        row.update(
            status="failed",
            category="invalid_tool_arguments",
            input_tokens=None,
            output_tokens=None,
        )
    finally:
        setattr(settings, provider + "_model", original)
        row["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        rows.append(row)
        print(json.dumps(row), flush=True)
if args.output:
    args.output.write_text(json.dumps(rows, indent=2) + "\n")
raise SystemExit(0 if all(r["status"] == "passed" for r in rows) else 1)
