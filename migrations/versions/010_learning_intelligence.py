"""Migration 010 — Learning intelligence

Revision ID: 010_learning_intelligence
Revises: 009_embeddings_pgvector
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "010_learning_intelligence"
down_revision: str | None = "009_embeddings_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "learner_objective_mastery",
    "recommendations",
    "remediation_plans",
    "remediation_plan_items",
)


def upgrade() -> None:
    op.create_table(
        "learner_objective_mastery",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learner_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("objective_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mastery_status", sa.String(32), nullable=False, server_default="developing"),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incorrect_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prior_score", sa.Float(), nullable=True),
        sa.Column("score_delta", sa.Float(), nullable=True),
        sa.Column(
            "calculation_version", sa.String(64), nullable=False, server_default="rule-engine-v1"
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
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
            "learner_membership_id",
            "objective_id",
            name="uq_learner_objective_mastery_pair",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_mastery_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_mastery_learner_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_mastery_objective_tenant",
        ),
    )
    op.create_index(
        "ix_learner_objective_mastery_tenant_id", "learner_objective_mastery", ["tenant_id"]
    )
    op.create_index(
        "ix_learner_objective_mastery_learner_id",
        "learner_objective_mastery",
        ["learner_membership_id"],
    )

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learner_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("objective_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recommendation_type",
            sa.String(64),
            nullable=False,
            server_default="targeted_practice",
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason_explanation", sa.Text(), nullable=False),
        sa.Column(
            "calculation_version", sa.String(64), nullable=False, server_default="rule-engine-v1"
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("learner_feedback", sa.String(64), nullable=True),
        sa.Column("feedback_comment", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_recommendations_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_recommendations_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_recommendations_learner_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_recommendations_objective_tenant",
        ),
    )
    op.create_index("ix_recommendations_tenant_id", "recommendations", ["tenant_id"])
    op.create_index("ix_recommendations_learner_id", "recommendations", ["learner_membership_id"])

    op.create_table(
        "remediation_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learner_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_remediation_plans_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_remediation_plans_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_remediation_plans_learner_tenant",
        ),
    )

    op.create_table(
        "remediation_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remediation_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
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
            ["tenant_id", "remediation_plan_id"],
            ["remediation_plans.tenant_id", "remediation_plans.id"],
            ondelete="CASCADE",
            name="fk_remediation_items_plan_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "recommendation_id"],
            ["recommendations.tenant_id", "recommendations.id"],
            ondelete="SET NULL",
            name="fk_remediation_items_rec_tenant",
        ),
    )

    for table in TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
