from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class Document(Base, TenantOwnedMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_documents_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "uploaded_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_documents_uploader_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending, processing, ready, failed, quarantined, deleted
    current_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_by_membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentVersion(Base, TenantOwnedMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_id", "version_number", name="uq_document_versions_num"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_document_versions_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_document_versions_document_tenant",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    extraction_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending, processing, completed, failed


class DocumentProcessingJob(Base, TenantOwnedMixin):
    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_document_processing_jobs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_doc_jobs_document_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_doc_jobs_version_tenant",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False
    )  # queued, processing, completed, failed
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentChunk(Base, TenantOwnedMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "chunk_index",
            name="uq_document_chunks_ver_idx",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_document_chunks_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_document_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_version_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ChunkEmbedding(Base, TenantOwnedMixin):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_embeddings_chunk"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_chunk_embeddings_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_chunk_embeddings_document_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["document_chunks.tenant_id", "document_chunks.id"],
            ondelete="CASCADE",
            name="fk_chunk_embeddings_chunk_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    chunk_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    embedding_model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(
        String(64), default="v1", nullable=False
    )
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    indexing_status: Mapped[str] = mapped_column(
        String(32), default="indexed", nullable=False
    )  # indexed, stale, failed
    embedding: Mapped[list[float]] = mapped_column(Vector(64), nullable=False)
