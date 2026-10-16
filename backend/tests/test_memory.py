"""Memory boundary and lifecycle regressions; model stubs are never live evaluation."""

import pytest
from app.core.config import settings
from app.memory.embeddings import ModelUnavailable, model
from app.memory.models import MemorySource
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_channels import channel, path, send
from test_workspaces import workspace


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
