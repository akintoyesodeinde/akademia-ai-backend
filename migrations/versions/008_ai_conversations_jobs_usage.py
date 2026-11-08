"""Migration 008 — AI conversations, messages, and usage

Revision ID: 008_ai_conversations_jobs_usage
Revises: 007_documents_processing
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "008_ai_conversations_jobs_usage"
down_revision: str | None = "007_documents_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "ai_conversations",
    "ai_messages",
    "ai_jobs",
    "ai_usage_records",
    "ai_generation_reviews",
)


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("complexity_level", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_ai_conversations_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_ai_conversations_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_ai_conversations_membership_tenant",
        ),
    )
    op.create_index("ix_ai_conversations_tenant_id", "ai_conversations", ["tenant_id"])
    op.create_index("ix_ai_conversations_course_id", "ai_conversations", ["course_id"])

    op.create_table(
        "ai_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("grounding_status", sa.String(32), nullable=False, server_default="grounded"),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default="tutor-rag-v1"),
        sa.Column(
            "model_id", sa.String(128), nullable=False, server_default="akademia-grounded-v1"
        ),
        sa.Column(
            "token_usage",
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id"],
            ondelete="CASCADE",
            name="fk_ai_messages_conversation_tenant",
        ),
    )
    op.create_index("ix_ai_messages_tenant_id", "ai_messages", ["tenant_id"])
    op.create_index("ix_ai_messages_conversation_id", "ai_messages", ["conversation_id"])

    op.create_table(
        "ai_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column(
            "input_params",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result_payload", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_ai_jobs_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_ai_jobs_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_ai_jobs_requester_tenant",
        ),
    )
    op.create_index("ix_ai_jobs_tenant_id", "ai_jobs", ["tenant_id"])

    op.create_table(
        "ai_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation_type", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="SET NULL",
            name="fk_ai_usage_membership_tenant",
        ),
    )
    op.create_index("ix_ai_usage_records_tenant_id", "ai_usage_records", ["tenant_id"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_key", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("prompt_key", "version", name="uq_prompt_versions_key_ver"),
    )

    op.create_table(
        "ai_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("retrieval_recall_at_5", sa.Float(), nullable=False),
        sa.Column("citation_authorization_rate", sa.Float(), nullable=False),
        sa.Column("groundedness_score", sa.Float(), nullable=False),
        sa.Column("answer_relevance_score", sa.Float(), nullable=False),
        sa.Column("unauthorized_leak_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("structured_validity_rate", sa.Float(), nullable=False),
        sa.Column(
            "metrics_detail",
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
    )

    op.create_table(
        "ai_generation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column(
            "source_references",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "validation_outcome",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "review_status", sa.String(32), nullable=False, server_default="pending_review"
        ),
        sa.Column("reviewer_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "ai_job_id"],
            ["ai_jobs.tenant_id", "ai_jobs.id"],
            ondelete="CASCADE",
            name="fk_ai_gen_reviews_job_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "question_id"],
            ["questions.tenant_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_ai_gen_reviews_question_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="SET NULL",
            name="fk_ai_gen_reviews_reviewer_tenant",
        ),
    )
    op.create_index("ix_ai_generation_reviews_tenant_id", "ai_generation_reviews", ["tenant_id"])

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE prompt_versions, ai_evaluations TO akademia_app, akademia_worker;"
    )
    op.execute("GRANT SELECT ON TABLE prompt_versions, ai_evaluations TO akademia_readonly;")

    for table in TENANT_TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)

    # Seed versioned prompts
    op.execute(
        """
        INSERT INTO prompt_versions (id, prompt_key, version, system_template, is_active)
        VALUES
            (
                gen_random_uuid(),
                'tutor_grounded_qa',
                'tutor-rag-v1',
                'You are the Akademia AI Course Tutor. Answer strictly using the authorized course passages provided. Cite chunk IDs and page numbers. If the course material does not support an answer, state clearly that the course materials do not cover this topic.',
                true
            ),
            (
                gen_random_uuid(),
                'practice_question_generator',
                'practice-gen-v1',
                'Generate practice questions strictly aligned with the target learning objective and authorized course passages. Output valid JSON matching the practice question schema.',
                true
            )
        ON CONFLICT (prompt_key, version) DO NOTHING;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION list_pending_ai_jobs_bootstrap(p_limit int DEFAULT 10)
        RETURNS TABLE (job_id uuid, tenant_id uuid)
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT j.id AS job_id, j.tenant_id AS tenant_id
            FROM ai_jobs j
            WHERE j.status IN ('queued', 'processing')
              AND j.attempt_count < 3
            ORDER BY j.created_at ASC
            LIMIT p_limit;
        $$;
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION list_pending_ai_jobs_bootstrap(int) TO akademia_worker, akademia_app;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS list_pending_ai_jobs_bootstrap(int);")
    for table in reversed(TENANT_TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
    op.drop_table("ai_evaluations")
    op.drop_table("prompt_versions")
