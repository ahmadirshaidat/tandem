"""OPTIONAL synthetic live checks, no workspace content. Run from backend:
.venv/bin/python ../infra/check_agent_providers.py
Never prints provider text, keys, or upstream exception bodies.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent.llm import WorkspaceLLM
from app.agent.tools import descriptors
from app.ai.providers import ProviderFailure, check_model, provider_key

failed = False
for name in ["groq", "gemini"]:
    if not provider_key(name):
        print(json.dumps({"provider": name, "status": "skipped_no_key"}))
        continue
    status = check_model(name)
    try:
        turn, completion = WorkspaceLLM().turn(
            name,
            {
                "question": "Synthetic test only: request get_channel_context, without arguments.",
                "tools": descriptors(),
                "results": [],
            },
        )
        valid = bool(turn.calls) and all(
            c.name == "get_channel_context" for c in turn.calls
        )
        print(
            json.dumps(
                {
                    "provider": name,
                    "model_discovery": status,
                    "structured_tool_request": valid,
                    "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens,
                }
            )
        )
        failed |= not valid
    except ProviderFailure as e:
        print(
            json.dumps(
                {"provider": name, "model_discovery": status, "status": e.category}
            )
        )
        failed = True
raise SystemExit(1 if failed else 0)
