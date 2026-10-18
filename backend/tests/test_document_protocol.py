import json

import pytest

from app.agent import llm
from app.agent.tools import descriptors
from app.ai.providers import Completion


@pytest.mark.parametrize(
    "read,expected",
    [
        ("get_document", {"propose_suggest_edit"}),
        (
            "get_task",
            {
                "propose_update_task",
                "propose_reassign_task",
                "propose_change_priority",
                "propose_delete_task",
                "propose_add_comment",
            },
        ),
        ("list_projects", {"propose_create_tasks"}),
    ],
)
def test_proposal_schemas_require_their_own_target_reads(monkeypatch, read, expected):
    captured = {}

    def structured(provider, instructions, body, schema):
        captured.update(json.loads(body))
        return Completion('{"calls":[],"answer":"Authorized context read"}', 1, 1)

    monkeypatch.setattr(llm, "structured", structured)
    llm.WorkspaceLLM().turn(
        "groq",
        {
            "question": "Synthetic document question",
            "tools": descriptors(),
            "results": [{"tool": read, "status": "ok", "data": {}}],
        },
    )
    assert {
        t["name"] for t in captured["allowed_calls"] if t["name"].startswith("propose_")
    } == expected
