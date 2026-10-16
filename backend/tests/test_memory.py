"""Memory boundary and lifecycle regressions; model stubs are never live evaluation."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_channels import channel, path, send
from test_workspaces import workspace

from app.core.config import settings
from app.memory.embeddings import ModelUnavailable, model
from app.memory.models import MemorySource


def test_memory_source_queue_is_transactional_and_edits_invalidate_revision(client_factory, db):
    owner, _ = client_factory("memory-owner@example.com")
    wid = workspace(owner)["id"]
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    source = db.get(MemorySource, (wid, "channel", cid))
    before = source.revision
    message = send(owner, path(wid, cid), "Synthetic memory queue test")
    db.expire_all()
    assert db.get(MemorySource, (wid, "channel", cid)).revision > before
    assert db.get(MemorySource, (wid, "channel", cid)).status == "queued"
    assert (
        owner.patch(
            path(wid, cid) + f"/messages/{message['id']}", json={"body": "Edited queue test"}
        ).status_code
        == 200
    )
    db.expire_all()
    assert db.get(MemorySource, (wid, "channel", cid)).indexed_revision == 0


def test_memory_sources_cannot_reference_another_workspace(client_factory, db):
    first, _ = client_factory("memory-first@example.com")
    second, _ = client_factory("memory-second@example.com")
    wid = workspace(first)["id"]
    other = workspace(second)["id"]
    cid = channel(second, other)["id"]
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(MemorySource(workspace_id=wid, kind="channel", source_id=cid, channel_id=cid))
        db.flush()


def test_memory_schema_has_vector_hnsw_and_arabic_normalization(db):
    assert db.scalar(text("SELECT memory_normalize('إختبَار آ أ ى ١')")) == "اختبار ا ا ي 1"
    assert (
        db.scalar(
            text(
                "SELECT count(*) FROM pg_indexes WHERE indexname IN ('ix_memory_hnsw','ix_memory_fts')"
            )
        )
        == 2
    )
    assert db.scalars(select(MemorySource)).all() == []


def test_missing_local_model_fails_closed_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "memory_model_path", tmp_path / "missing")
    with pytest.raises(ModelUnavailable):
        model()


class MockEmbedding:
    identity = ("synthetic-test-only", "1")

    def encode(self, texts, *, query=False):
        return [[1.0] + [0.0] * 383 for _ in texts]


def drain():
    from app.memory.indexing import process_one

    for _ in range(30):
        if not process_one(embedder=MockEmbedding(), raise_errors=True):
            return
    raise AssertionError("Index queue did not drain")


def test_hybrid_filters_private_sources_inside_sql_and_revocation_is_immediate(client_factory, db):
    from test_workspaces import add_member

    from app.channels.models import ChannelMember
    from app.memory.indexing import configuration
    from app.memory.retrieval import SearchInput, search

    owner, uid = client_factory("retrieval-owner@example.com")
    uid = uid["id"]
    wid = workspace(owner)["id"]
    viewer, other_uid = add_member(
        owner, client_factory, wid, "retrieval-viewer@example.com", "viewer"
    )
    other_uid = other_uid["user_id"]
    private = channel(owner, wid, private=True)
    send(owner, path(wid, private["id"]), "Secret connection timeout solution")
    general = owner.get(f"/api/workspaces/{wid}/channels").json()[0]
    send(owner, path(wid, general["id"]), "Public connection timeout solution")
    configuration(db, wid).include_private = True
    db.commit()
    drain()
    for mode in ["full_text", "vector", "hybrid"]:
        result = search(
            db,
            wid,
            other_uid,
            SearchInput(query="connection timeout", mode=mode),
            embedder=MockEmbedding(),
        )
        assert result["items"] and all(i["channel_id"] != private["id"] for i in result["items"])
        assert "total" not in result and "skipped" not in result
        assert any(
            i["channel_id"] == private["id"]
            for i in search(
                db,
                wid,
                uid,
                SearchInput(query="connection timeout", mode=mode),
                embedder=MockEmbedding(),
            )["items"]
        )
    cm = db.scalar(
        select(ChannelMember).where(
            ChannelMember.channel_id == private["id"], ChannelMember.user_id == uid
        )
    )
    db.delete(cm)
    db.commit()
    assert all(
        i["channel_id"] != private["id"]
        for i in search(
            db, wid, uid, SearchInput(query="connection timeout"), embedder=MockEmbedding()
        )["items"]
    )


def test_edits_hide_old_chunks_before_reindex_and_rebuild_is_idempotent(client_factory, db):
    from app.memory.models import MemoryRecord
    from app.memory.retrieval import SearchInput, search

    owner, uid = client_factory("edit-memory@example.com")
    uid = uid["id"]
    wid = workspace(owner)["id"]
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    m = send(owner, path(wid, cid), "Original zebra timeout")
    drain()
    records = list(db.scalars(select(MemoryRecord)))
    assert records
    record_id = records[0].id
    from app.memory.indexing import touch

    touch(db, wid, "channel", cid)
    db.commit()
    drain()
    assert db.scalar(select(MemoryRecord.id)) == record_id
    assert (
        owner.patch(
            path(wid, cid) + f"/messages/{m['id']}", json={"body": "Replacement penguin failure"}
        ).status_code
        == 200
    )
    assert search(db, wid, uid, SearchInput(query="zebra"), embedder=MockEmbedding())["items"] == []
    drain()
    assert search(
        db, wid, uid, SearchInput(query="penguin", mode="full_text"), embedder=MockEmbedding()
    )["items"]
    assert not search(
        db, wid, uid, SearchInput(query="zebra", mode="full_text"), embedder=MockEmbedding()
    )["items"]


def test_private_default_and_degraded_search_with_arabic_normalization(
    client_factory, db, monkeypatch, tmp_path
):
    from app.memory.models import MemoryRecord
    from app.memory.retrieval import SearchInput, search

    owner, uid = client_factory("arabic-memory@example.com")
    uid = uid["id"]
    wid = workspace(owner)["id"]
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    private = channel(owner, wid, private=True)
    send(owner, path(wid, private["id"]), "Private secret")
    send(owner, path(wid, cid), "إصلاح مُشكلة الإتصال بالخادم")
    drain()
    assert not db.scalar(select(MemoryRecord.id).where(MemoryRecord.channel_id == private["id"]))
    monkeypatch.setattr(settings, "memory_model_path", tmp_path / "missing")
    result = search(db, wid, uid, SearchInput(query="اصلاح مشكلة الاتصال"))
    assert result["degraded"] and result["items"]


def test_admin_settings_and_forget_preserve_domain_data_and_audit(client_factory, db):
    from test_workspaces import add_member

    from app.agent.models import AuditEvent
    from app.channels.models import Message
    from app.memory.models import MemoryRecord

    owner, who = client_factory("forget-owner@example.com")
    wid = workspace(owner)["id"]
    viewer, _ = add_member(owner, client_factory, wid, "forget-viewer@example.com", "viewer")
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    original = send(owner, path(wid, cid), "Forget derived memory only")
    drain()
    endpoint = f"/api/workspaces/{wid}/memory"
    assert viewer.get(endpoint + "/settings").status_code == 403
    assert viewer.post(endpoint + "/reindex", json={}).status_code == 403
    rid = db.scalar(select(MemoryRecord.id))
    selection = {"record_ids": [rid]}
    preview = owner.post(endpoint + "/forget-preview", json=selection)
    assert preview.status_code == 200, preview.text
    assert preview.json()["count"] == 1
    assert owner.post(endpoint + "/forget", json=selection).status_code == 409
    applied = owner.post(
        endpoint + "/forget", json={**selection, "preview_token": preview.json()["preview_token"]}
    )
    assert applied.status_code == 200 and applied.json()["forgotten"] == 1
    assert db.get(Message, original["id"]).body == "Forget derived memory only"
    assert owner.post(endpoint + "/reindex", json={}).status_code == 202
    drain()
    assert not db.scalar(select(MemoryRecord.id))
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "memory.forgotten"))
    assert viewer.post(endpoint + "/forget-preview", json=selection).status_code == 403


def test_search_pagination_source_fetch_and_cross_workspace_are_authorized(
    client_factory, db, monkeypatch
):
    from test_tasks import project, task

    from app.memory import retrieval

    monkeypatch.setattr(retrieval, "model", lambda: MockEmbedding())
    owner, who = client_factory("paging-owner@example.com")
    other, _ = client_factory("paging-other@example.com")
    wid = workspace(owner)["id"]
    pid = project(owner, wid)["id"]
    for n in range(3):
        task(owner, wid, pid, title=f"Connection timeout case {n}", type="bug")
    drain()
    endpoint = f"/api/workspaces/{wid}/search"
    first = owner.get(endpoint, params={"query": "connection timeout", "limit": 1})
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 1 and first.json()["next_cursor"]
    second = owner.get(
        endpoint,
        params={"query": "connection timeout", "limit": 1, "cursor": first.json()["next_cursor"]},
    )
    assert (
        second.status_code == 200
        and second.json()["items"][0]["id"] != first.json()["items"][0]["id"]
    )
    assert other.get(endpoint, params={"query": "connection"}).status_code == 404
    rid = first.json()["items"][0]["id"]
    assert owner.get(f"/api/workspaces/{wid}/memory/records/{rid}").status_code == 200
    assert other.get(f"/api/workspaces/{wid}/memory/records/{rid}").status_code == 404
    assert (
        owner.get(
            endpoint, params={"query": "different", "cursor": first.json()["next_cursor"]}
        ).status_code
        == 400
    )


def test_private_setting_off_removes_vectors_and_source_forget_never_deletes_tasks(
    client_factory, db
):
    from test_tasks import project, task

    from app.memory.indexing import configuration
    from app.memory.models import MemoryRecord
    from app.tasks.models import Task

    owner, _ = client_factory("toggle-owner@example.com")
    wid = workspace(owner)["id"]
    private = channel(owner, wid, private=True)
    send(owner, path(wid, private["id"]), "Private indexed text")
    configuration(db, wid).include_private = True
    db.commit()
    pid = project(owner, wid)["id"]
    original = task(owner, wid, pid, title="Task remains after forgetting")
    drain()
    base = f"/api/workspaces/{wid}/memory"
    response = owner.put(
        base + "/settings",
        json={"include_private": False, "retention_days": 0, "offer_resolution_summaries": False},
    )
    assert response.status_code == 200, response.text
    assert not db.scalar(select(MemoryRecord.id).where(MemoryRecord.channel_id == private["id"]))
    drain()
    selection = {"source_kind": "project", "source_id": pid}
    preview = owner.post(base + "/forget-preview", json=selection).json()
    assert preview["count"] == 1
    assert (
        owner.post(
            base + "/forget", json={**selection, "preview_token": preview["preview_token"]}
        ).status_code
        == 200
    )
    drain()
    assert not db.scalar(select(MemoryRecord.id).where(MemoryRecord.project_id == pid))
    assert db.get(Task, original["id"]).deleted_at is None


def test_resolution_summary_is_disabled_then_only_proposes_once_per_completion(client_factory, db):
    from test_agent import setup_agent
    from test_tasks import project, task, task_path

    from app.channels.models import Channel
    from app.proposals.models import Proposal
    from app.tasks.models import TaskComment

    owner, wid, cid = setup_agent(client_factory)
    pid = project(owner, wid)["id"]
    ch = db.get(Channel, cid)
    ch.project_id = pid
    db.commit()
    bug = task(
        owner,
        wid,
        pid,
        title="Retry loop failure",
        type="bug",
        description="Reported fix: stop retrying revoked tokens",
    )
    response = owner.patch(task_path(wid, bug["id"]), json={"version": 1, "status": "done"})
    assert response.status_code == 200, response.text
    drain()
    assert not db.scalar(select(Proposal.id))
    endpoint = f"/api/workspaces/{wid}/memory/settings"
    assert (
        owner.put(
            endpoint,
            json={
                "include_private": False,
                "retention_days": 0,
                "offer_resolution_summaries": True,
            },
        ).status_code
        == 200
    )
    latest = response.json()
    reopened = owner.patch(
        task_path(wid, bug["id"]), json={"version": latest["version"], "status": "in_progress"}
    ).json()
    assert (
        owner.patch(
            task_path(wid, bug["id"]), json={"version": reopened["version"], "status": "done"}
        ).status_code
        == 200
    )
    drain()
    proposals = list(db.scalars(select(Proposal)))
    assert (
        len(proposals) == 1
        and proposals[0].kind == "add_comment"
        and proposals[0].status == "proposed"
    )
    assert not db.scalar(select(TaskComment.id))
    from app.memory.indexing import touch

    touch(db, wid, "project", pid)
    db.commit()
    drain()
    assert len(list(db.scalars(select(Proposal)))) == 1


def test_retention_and_model_version_reindex(client_factory, db, monkeypatch):
    from datetime import timedelta

    from app.channels.models import Message
    from app.core.security import now
    from app.memory import indexing
    from app.memory.models import MemoryEmbedding, MemoryRecord

    owner, _ = client_factory("version-owner@example.com")
    wid = workspace(owner)["id"]
    cid = owner.get(f"/api/workspaces/{wid}/channels").json()[0]["id"]
    message = send(owner, path(wid, cid), "Model version migration")
    drain()

    class NextModel(MockEmbedding):
        identity = ("synthetic-test-only", "2")

    monkeypatch.setattr(indexing, "model", lambda: NextModel())
    indexing.maintenance(db)
    db.commit()
    while indexing.process_one(embedder=NextModel()):
        pass
    assert db.scalar(select(MemoryEmbedding.record_id).where(MemoryEmbedding.model_version == "2"))
    db.get(Message, message["id"]).created_at = now() - timedelta(days=100)
    indexing.configuration(db, wid).retention_days = 90
    db.commit()
    drain()
    assert not db.scalar(select(MemoryRecord.id))


def test_agent_memory_tools_do_not_cross_audiences_or_workspaces(client_factory, db):
    from test_agent import Scripted, run_latest, setup_agent

    from app.agent.llm import AgentTurn, ToolRequest

    owner, wid, cid = setup_agent(client_factory)
    private = channel(owner, wid, private=True)
    send(owner, path(wid, private["id"]), "Very private zebra evidence")
    from app.memory.indexing import configuration

    configuration(db, wid).include_private = True
    db.commit()
    drain()
    send(owner, path(wid, cid), "@Agent search memory zebra")
    scripted = Scripted(
        [
            AgentTurn(calls=[ToolRequest(name="search_memory", arguments={"query": "zebra"})]),
            AgentTurn(answer="No permitted evidence"),
        ]
    )
    run = run_latest(db, scripted)
    assert run.status == "completed"
    assert scripted.payloads[-1]["results"][0]["data"]["items"] == []
    assert "Very private" not in str(scripted.payloads)
