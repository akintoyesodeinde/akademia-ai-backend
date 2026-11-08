"""Migration 009 — Embeddings and retrieval indexes

Revision ID: 009_embeddings_pgvector
Revises: 008_ai_conversations_jobs_usage
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "009_embeddings_pgvector"
down_revision: str | None = "008_ai_conversations_jobs_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("embedding_model_id", sa.String(128), nullable=False),
        sa.Column("embedding_model_version", sa.String(64), nullable=False, server_default="v1"),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False, server_default="64"),
        sa.Column("indexing_status", sa.String(32), nullable=False, server_default="indexed"),
        sa.Column("embedding", Vector(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_embeddings_chunk"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_chunk_embeddings_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_chunk_embeddings_document_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["document_chunks.tenant_id", "document_chunks.id"],
            ondelete="CASCADE",
            name="fk_chunk_embeddings_chunk_tenant",
        ),
    )
    op.create_index(
        "ix_chunk_embeddings_tenant_course_model",
        "chunk_embeddings",
        ["tenant_id", "course_id", "embedding_model_id", "indexing_status"],
    )
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_vector_hnsw ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);"
    )

    for stmt in build_enable_rls_sql("chunk_embeddings"):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in build_disable_rls_sql("chunk_embeddings"):
        op.execute(stmt)
    op.drop_table("chunk_embeddings")
