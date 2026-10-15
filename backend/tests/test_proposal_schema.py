from alembic import command
from alembic.config import Config
from sqlalchemy import text
from test_channels import channel, path, send
from test_workspaces import workspace

from app.proposals.models import Proposal, ProposalItem  # noqa: F401


def test_proposal_schema_and_upgrade_preserve_slice4(client_factory, db):
    owner, _ = client_factory("migration@example.com")
    wid = workspace(owner)["id"]
    cid = channel(owner, wid, private=True)["id"]
    original = send(owner, path(wid, cid), "رسالة محفوظة")
    db.close()
    config = Config("alembic.ini")
    command.downgrade(config, "e18d26760b88")
    command.upgrade(config, "head")
    assert owner.get(path(wid, cid) + "/messages").json()["messages"][0]["body"] == original["body"]
    constraints = set(
        db.scalars(
            text(
                "SELECT conname FROM pg_constraint WHERE conrelid IN ('proposals'::regclass,'proposal_items'::regclass)"
            )
        )
    )
    assert {
        "ck_proposal_kind",
        "ck_proposal_risk",
        "ck_proposal_state",
        "uq_proposal_tool_key",
        "uq_proposal_item",
    } <= constraints
