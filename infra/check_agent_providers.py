"""OPTIONAL synthetic live checks, no workspace content. Run from backend:
.venv/bin/python ../infra/check_agent_providers.py
Never prints provider text, keys, or upstream exception bodies.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent.llm import WorkspaceLLM
from app.agent.tools import descriptors
from app.ai.providers import ProviderFailure, check_model, provider_key, provider_model

failed = False
for name in ["groq", "gemini"]:
    if not provider_key(name):
        print(json.dumps({"provider": name, "status": "skipped_no_key"}))
        continue
    status = check_model(name)
    start = time.perf_counter()
    try:
        turn, completion = WorkspaceLLM().turn(
            name,
            {
                "question": "Synthetic test only: request get_channel_context, without arguments.",
                "tools": descriptors(),
                "results": [],
            },
        )
        valid = bool(turn.calls) and all(c.name == "get_channel_context" for c in turn.calls)
        print(
            json.dumps(
                {
                    "provider": name,
                    "model": provider_model(name),
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    "model_discovery": status,
                    "structured_tool_request": valid,
                    "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens,
                    "attempts": completion.attempts,
                    "repaired": completion.repaired,
                    "safe_errors": completion.safe_errors,
                }
            )
        )
        failed |= not valid
    except ProviderFailure as e:
        print(
            json.dumps(
                {
                    "provider": name,
                    "model": provider_model(name),
                    "model_discovery": status,
                    "status": e.category,
                    "http_status": e.status,
                    "attempts": e.attempts,
                    "safe_errors": e.safe_errors,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                }
            )
        )
        failed = True
raise SystemExit(1 if failed else 0)
