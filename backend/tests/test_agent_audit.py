import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.agent.audit import audit


def test_audit_immutable(db, client_factory):
    client, _ = client_factory("audit@example.com")
    wid = client.post("/api/workspaces", json={"name": "Audit"}).json()["id"]
    audit(db, wid, "system", None, "test", "workspace", wid)
    db.commit()
    for statement in [
        "UPDATE audit_events SET action='changed'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ]:
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(text(statement))
