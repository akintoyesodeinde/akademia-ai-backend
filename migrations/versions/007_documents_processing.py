"""Migration 007 — Documents and content processing

Revision ID: 007_documents_processing
Revises: 006_assessments_grading
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "007_documents_processing"
down_revision: str | None = "006_assessments_grading"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "documents",
    "document_versions",
    "document_processing_jobs",
    "document_chunks",
)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("current_version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("uploaded_by_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_documents_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "uploaded_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_documents_uploader_tenant",
        ),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_course_id", "documents", ["course_id"])
    op.create_index("ix_documents_checksum", "documents", ["checksum_sha256"])

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("extraction_status", sa.String(32), nullable=False, server_default="pending"),
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
        sa.UniqueConstraint(
            "tenant_id", "document_id", "version_number", name="uq_document_versions_num"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_versions_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_document_versions_document_tenant",
        ),
    )
    op.create_index("ix_document_versions_tenant_id", "document_versions", ["tenant_id"])

    op.create_table(
        "document_processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_processing_jobs_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_doc_jobs_document_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_doc_jobs_version_tenant",
        ),
    )
    op.create_index(
        "ix_document_processing_jobs_tenant_id", "document_processing_jobs", ["tenant_id"]
    )
    op.create_index("ix_document_processing_jobs_status", "document_processing_jobs", ["status"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("section_title", sa.String(255), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "chunk_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "chunk_index",
            name="uq_document_chunks_ver_idx",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_chunks_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_document_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["document_versions.tenant_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_document_chunks_version_tenant",
        ),
    )
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index("ix_document_chunks_course_id", "document_chunks", ["course_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    for table in TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)

    # Narrow worker bootstrap function to locate queued/stale document jobs by (job_id, tenant_id)
    # so the worker can establish transaction-local `app.tenant_id` before executing under RLS.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION list_pending_document_jobs_bootstrap(p_limit int DEFAULT 10)
        RETURNS TABLE (job_id uuid, tenant_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT j.id AS job_id, j.tenant_id AS tenant_id
            FROM document_processing_jobs j
            WHERE j.status IN ('queued', 'processing')
              AND j.attempt_count < j.max_retries
            ORDER BY j.created_at ASC
            LIMIT p_limit;
        $$;
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION list_pending_document_jobs_bootstrap(int) TO akademia_worker, akademia_app;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_pending_document_jobs_bootstrap(int);")
    for table in reversed(TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
