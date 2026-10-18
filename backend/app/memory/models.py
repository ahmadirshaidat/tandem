"""Source-linked memory; permissions always come from current domain tables."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import new_id


class MemorySettings(Base):
    __tablename__ = "memory_settings"
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    include_documents: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    include_private: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    retention_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    offer_resolution_summaries: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    resolution_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("retention_days IN (0,90,365)", name="ck_memory_retention"),)


class MemorySource(Base):
    """Coalescing durable queue, claimed by the existing Postgres worker."""

    __tablename__ = "memory_sources"
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(12), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str | None] = mapped_column(String(36))
    project_id: Mapped[str | None] = mapped_column(String(36))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    indexed_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(12), default="queued", server_default="queued")
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(24))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    lag_ms: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "channel_id"],
            ["channels.workspace_id", "channels.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "project_id"],
            ["projects.workspace_id", "projects.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(kind = 'channel' AND channel_id IS NOT NULL AND channel_id = source_id AND project_id IS NULL) OR (kind = 'project' AND project_id IS NOT NULL AND project_id = source_id AND channel_id IS NULL) OR (kind = 'document' AND channel_id IS NULL AND project_id IS NULL)",
            name="ck_memory_source_kind",
        ),
        CheckConstraint(
            "status IN ('queued','indexing','idle','failed') AND revision >= indexed_revision AND attempts >= 0",
            name="ck_memory_source_state",
        ),
        Index("ix_memory_queue", "status", "queued_at"),
    )


def source_fk():
    return ForeignKeyConstraint(
        ["workspace_id", "group_kind", "group_id"],
        ["memory_sources.workspace_id", "memory_sources.kind", "memory_sources.source_id"],
        ondelete="CASCADE",
    )


class MemoryRecord(Base):
    __tablename__ = "memory_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    group_kind: Mapped[str] = mapped_column(String(12))
    group_id: Mapped[str] = mapped_column(String(36))
    source_type: Mapped[str] = mapped_column(String(12))
    source_id: Mapped[str] = mapped_column(String(36))
    channel_id: Mapped[str | None] = mapped_column(String(36))
    project_id: Mapped[str | None] = mapped_column(String(36))
    document_id: Mapped[str | None] = mapped_column(String(36))
    task_id: Mapped[str | None] = mapped_column(String(36))
    message_id: Mapped[str | None] = mapped_column(String(36))
    chunk_number: Mapped[int] = mapped_column(Integer)
    record_key: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    chunk_text: Mapped[str] = mapped_column(Text)
    visibility_scope: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default="ready", server_default="ready")
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    search_vector: Mapped[object] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, memory_normalize(title || ' ' || chunk_text)) || to_tsvector('english'::regconfig, memory_normalize(title || ' ' || chunk_text))",
            persisted=True,
        ),
    )
    __table_args__ = (
        source_fk(),
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_memory_record_scope"),
        UniqueConstraint("workspace_id", "record_key", name="uq_memory_record_key"),
        ForeignKeyConstraint(
            ["workspace_id", "channel_id", "message_id"],
            ["messages.workspace_id", "messages.channel_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "project_id"],
            ["projects.workspace_id", "projects.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(source_type = 'message' AND message_id IS NOT NULL AND message_id = source_id AND channel_id IS NOT NULL AND task_id IS NULL) OR (source_type = 'task' AND task_id IS NOT NULL AND task_id = source_id AND project_id IS NOT NULL AND message_id IS NULL) OR (source_type = 'document' AND document_id IS NOT NULL AND document_id = source_id AND project_id IS NOT NULL AND message_id IS NULL AND task_id IS NULL)",
            name="ck_memory_record_source",
        ),
        CheckConstraint(
            "chunk_number >= 0 AND status = 'ready' AND visibility_scope IN ('channel','project','document')",
            name="ck_memory_record_state",
        ),
        Index("ix_memory_fts", "search_vector", postgresql_using="gin"),
    )


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    embedding_model: Mapped[str] = mapped_column(String(160), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    dimension: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list] = mapped_column(Vector(384))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "record_id"],
            ["memory_records.workspace_id", "memory_records.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("dimension = 384", name="ck_memory_dimension"),
        Index(
            "ix_memory_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )


class MemoryForget(Base):
    __tablename__ = "memory_forgets"
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    record_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_kind: Mapped[str] = mapped_column(String(12))
    group_id: Mapped[str] = mapped_column(String(36))
    forgotten_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (source_fk(),)


class ResolutionOffer(Base):
    __tablename__ = "memory_resolution_offers"
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "proposal_id"], ["proposals.workspace_id", "proposals.id"]
        ),
        CheckConstraint("task_version > 0", name="ck_resolution_version"),
    )
