import base64
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agent.tools import REGISTRY, execute
from app.documents import service as svc
from app.documents.models import Document, DocumentVersion
from app.memory.indexing import process_one
from app.memory.retrieval import SearchInput, search
from app.proposals.schemas import Decision
from app.proposals.service import create_proposal, decide


def setup_document(client_factory, private=False):
    owner, user = client_factory("doc-" + uuid.uuid4().hex + "@example.com")
    wid = owner.post("/api/workspaces", json={"name": "Documents"}).json()["id"]
    pid = owner.post(
        f"/api/workspaces/{wid}/projects", json={"name": "Platform", "key": "DOC"}
    ).json()["id"]
    d = owner.post(
        f"/api/workspaces/{wid}/documents",
        json={"project_id": pid, "title": "Specification", "is_private": private},
    )
    assert d.status_code == 201, d.text
    return owner, user, wid, d.json()["id"]


def test_document_roles_private_scope_versions_and_markdown(client_factory, db):
    owner, user, wid, did = setup_document(client_factory, True)
    outsider, other = client_factory("other-doc@example.com")
    other_workspace = outsider.post("/api/workspaces", json={"name": "Other scope"}).json()["id"]
    assert outsider.get(f"/api/workspaces/{other_workspace}/documents/{did}").status_code == 404
    from app.core.models import Membership

    db.add(Membership(workspace_id=wid, user_id=other["id"], role="viewer"))
    db.commit()
    root = f"/api/workspaces/{wid}/documents"
    assert outsider.get(root).json() == {"documents": []}
    for path in ["", "/state", "/versions", "/backlinks", "/suggestions", "/export"]:
        assert outsider.get(root + "/" + did + path).status_code == 404
    assert owner.put(root + "/" + did + "/members/" + other["id"]).status_code == 200
    assert outsider.get(root + "/" + did).status_code == 200
    assert outsider.post(root + "/" + did + "/sync", json={"update": "AAA="}).status_code == 403
    v = owner.post(root + "/" + did + "/versions", json={"name": "Reviewed draft"}).json()
    original = db.get(Document, did).state
    changed = svc.transform(original, action="anchor", expected_text="Describe the problem.")
    from datetime import timedelta

    db.get(Document, did).snapshot_at = svc.now() - timedelta(minutes=3)
    db.commit()
    replacement = svc.transform(
        original,
        action="apply",
        expected_text="Describe the problem.",
        replacement="A clear problem.",
        from_anchor=changed["from_anchor"],
        to_anchor=changed["to_anchor"],
    )
    assert (
        owner.post(root + "/" + did + "/sync", json={"update": replacement["state"]}).status_code
        == 200
    )
    assert "A clear problem." in owner.get(root + "/" + did).json()["text"]
    count = len(owner.get(root + "/" + did + "/versions").json()["versions"])
    assert owner.post(root + "/" + did + "/versions/" + v["id"] + "/restore").status_code == 200
    assert "Describe the problem." in owner.get(root + "/" + did + "/export").text
    assert len(owner.get(root + "/" + did + "/versions").json()["versions"]) > count
    assert owner.delete(root + "/" + did + "/members/" + other["id"]).status_code == 204
    assert outsider.get(root + "/" + did + "/state").status_code == 404


def test_document_suggestion_approval_integrity_staleness_and_registry(client_factory, db):
    from app.agent.models import AgentRun

    owner, user, wid, did = setup_document(client_factory)
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    message = owner.post(
        f"/api/workspaces/{wid}/channels/{cid}/messages",
        json={"body": "Synthetic suggestion", "client_message_id": uuid.uuid4().hex},
    ).json()
    run = AgentRun(
        workspace_id=wid,
        channel_id=cid,
        trigger_message_id=message["id"],
        requester_id=user["id"],
        status="running",
        request_id=uuid.uuid4().hex,
    )
    db.add(run)
    db.flush()
    from app.agent.service import configuration

    configuration(db, wid).enabled = True
    db.flush()
    assert execute(db, run, "get_document", {"document_id": did})["status"] == "ok"
    configuration(db, wid).enabled = False
    assert execute(db, run, "get_document", {"document_id": did})["status"] == "denied"
    configuration(db, wid).enabled = True
    assert not (
        {"edit_document", "write_document", "apply_document_update", "restore_document"}
        & set(REGISTRY)
    )
    assert {"get_document", "retrieve_documents", "propose_suggest_edit"} <= set(REGISTRY)
    p = create_proposal(
        db,
        run,
        "suggest_edit",
        {
            "document_id": did,
            "expected_text": "Describe the problem.",
            "replacement": "Describe it clearly.",
            "reason": "Clarity",
        },
    )
    db.commit()
    d = db.get(Document, did)
    before = d.state
    assert d.state == before and "Describe it clearly." not in d.plain_text
    decision = Decision(
        version=p.version, payload_hash=p.payload_hash, idempotency_key="approve-once"
    )
    decide(db, p, user["id"], decision, "approve", uuid.uuid4().hex)
    db.commit()
    assert p.status == "completed"
    assert "Describe it clearly." in db.get(Document, did).plain_text
    state = db.get(Document, did).state
    decide(db, p, user["id"], decision, "approve", uuid.uuid4().hex)
    db.commit()
    assert db.get(Document, did).state == state
    assert (
        db.scalar(select(DocumentVersion).where(DocumentVersion.proposal_id == p.id)).actor_type
        == "agent_approved"
    )
    stale = create_proposal(
        db,
        run,
        "suggest_edit",
        {
            "document_id": did,
            "expected_text": "Describe it clearly.",
            "replacement": "Another edit.",
            "reason": "Clarity",
        },
    )
    value = svc.transform(
        state,
        action="apply",
        expected_text="Describe it clearly.",
        replacement="Human changed this.",
        from_anchor=stale.payload["from_anchor"],
        to_anchor=stale.payload["to_anchor"],
    )
    svc.persist(db, d, user["id"], base64.b64decode(value["state"]))
    db.flush()
    decide(
        db,
        stale,
        user["id"],
        Decision(version=stale.version, payload_hash=stale.payload_hash, idempotency_key="stale"),
        "approve",
        uuid.uuid4().hex,
    )
    assert stale.status == "stale" and "Human changed this." in d.plain_text
    tampered = create_proposal(
        db,
        run,
        "suggest_edit",
        {
            "document_id": did,
            "expected_text": "Human changed this.",
            "replacement": "Tamper target",
            "reason": "Clarity",
        },
    )
    tampered.payload = {**tampered.payload, "replacement": "Tampered"}
    with pytest.raises(HTTPException):
        decide(
            db,
            tampered,
            user["id"],
            Decision(
                version=tampered.version,
                payload_hash=tampered.payload_hash,
                idempotency_key="tamper",
            ),
            "approve",
            uuid.uuid4().hex,
        )


def test_document_memory_toggle_deletion_and_malformed_updates(client_factory, db):
    owner, user, wid, did = setup_document(client_factory)
    while process_one():
        pass
    result = search(
        db,
        wid,
        user["id"],
        SearchInput(query="Specification", source_type="document", mode="full_text"),
    )
    assert any(x["source_id"] == did for x in result["items"])
    root = f"/api/workspaces/{wid}"
    assert (
        owner.post(
            root + "/documents/" + did + "/sync",
            json={"update": base64.b64encode(b"not-yjs").decode()},
        ).status_code
        == 422
    )
    assert (
        owner.post(
            root + "/documents/" + did + "/sync",
            json={"update": base64.b64encode(b"x" * 66000).decode()},
        ).status_code
        == 413
    )
    assert (
        owner.put(
            root + "/memory/settings",
            json={
                "include_documents": False,
                "include_private": False,
                "retention_days": 0,
                "offer_resolution_summaries": False,
            },
        ).status_code
        == 200
    )
    assert not search(
        db, wid, user["id"], SearchInput(query="Specification", source_type="document")
    )["items"]
    assert owner.delete(root + "/documents/" + did).status_code == 204
    assert owner.get(root + "/documents/" + did).status_code == 404
