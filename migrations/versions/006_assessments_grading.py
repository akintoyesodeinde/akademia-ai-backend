"""Migration 006 — Assessments and grading

Revision ID: 006_assessments_grading
Revises: 005_enrollments_events
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "006_assessments_grading"
down_revision: str | None = "005_enrollments_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "assessments",
    "assessment_versions",
    "questions",
    "assessment_items",
    "assessment_item_objectives",
    "assessment_attempts",
    "responses",
    "grading_results",
    "rubrics",
    "rubric_criteria",
    "rubric_scores",
    "grading_reviews",
)


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assessment_type", sa.String(32), nullable=False, server_default="diagnostic"),
        sa.Column("passing_score_percentage", sa.Float(), nullable=False, server_default="75.0"),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("current_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_version_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_assessments_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_assessments_course_tenant",
        ),
    )
    op.create_index("ix_assessments_tenant_id", "assessments", ["tenant_id"])
    op.create_index("ix_assessments_course_id", "assessments", ["course_id"])

    op.create_table(
        "assessment_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("passing_score_percentage", sa.Float(), nullable=False),
        sa.Column("total_points", sa.Float(), nullable=False),
        sa.Column("questions_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
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
            "tenant_id", "assessment_id", "version_number", name="uq_assessment_versions_num"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_assessment_versions_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_assessment_versions_assessment_tenant",
        ),
    )
    op.create_index("ix_assessment_versions_tenant_id", "assessment_versions", ["tenant_id"])

    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False, server_default="multiple_choice"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("correct_answer", sa.String(512), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("points", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("difficulty", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="instructor"),
        sa.Column("status", sa.String(32), nullable=False, server_default="approved"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_questions_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_questions_course_tenant",
        ),
    )
    op.create_index("ix_questions_tenant_id", "questions", ["tenant_id"])
    op.create_index("ix_questions_course_id", "questions", ["course_id"])

    op.create_table(
        "assessment_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("points_override", sa.Float(), nullable=True),
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
            "tenant_id", "assessment_id", "question_id", name="uq_assessment_items_pair"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_assessment_items_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_assessment_items_assessment_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "question_id"],
            ["questions.tenant_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_assessment_items_question_tenant",
        ),
    )
    op.create_index("ix_assessment_items_tenant_id", "assessment_items", ["tenant_id"])

    op.create_table(
        "assessment_item_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("objective_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "tenant_id", "question_id", "objective_id", name="uq_question_objectives_pair"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "question_id"],
            ["questions.tenant_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_item_objectives_question_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_item_objectives_objective_tenant",
        ),
    )
    op.create_index(
        "ix_assessment_item_objectives_tenant_id", "assessment_item_objectives", ["tenant_id"]
    )

    op.create_table(
        "assessment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learner_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_assessment_attempts_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_attempts_assessment_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_version_id"],
            ["assessment_versions.tenant_id", "assessment_versions.id"],
            ondelete="RESTRICT",
            name="fk_attempts_version_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "enrollment_id"],
            ["enrollments.tenant_id", "enrollments.id"],
            ondelete="CASCADE",
            name="fk_attempts_enrollment_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_attempts_learner_membership_tenant",
        ),
    )
    op.create_index("ix_assessment_attempts_tenant_id", "assessment_attempts", ["tenant_id"])
    op.create_index(
        "ix_assessment_attempts_learner_id", "assessment_attempts", ["learner_membership_id"]
    )

    op.create_table(
        "responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selected_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("awarded_points", sa.Float(), nullable=False, server_default="0.0"),
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
        sa.UniqueConstraint("tenant_id", "attempt_id", "question_id", name="uq_responses_attempt_q"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attempt_id"],
            ["assessment_attempts.tenant_id", "assessment_attempts.id"],
            ondelete="CASCADE",
            name="fk_responses_attempt_tenant",
        ),
    )
    op.create_index("ix_responses_tenant_id", "responses", ["tenant_id"])
    op.create_index("ix_responses_attempt_id", "responses", ["attempt_id"])

    op.create_table(
        "grading_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("earned_points", sa.Float(), nullable=False),
        sa.Column("total_points", sa.Float(), nullable=False),
        sa.Column("score_percentage", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("grading_method", sa.String(32), nullable=False, server_default="deterministic_v1"),
        sa.Column(
            "objective_breakdown",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "attempt_id", name="uq_grading_results_attempt"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_grading_results_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attempt_id"],
            ["assessment_attempts.tenant_id", "assessment_attempts.id"],
            ondelete="CASCADE",
            name="fk_grading_results_attempt_tenant",
        ),
    )
    op.create_index("ix_grading_results_tenant_id", "grading_results", ["tenant_id"])

    op.create_table(
        "rubrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_rubrics_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_rubrics_assessment_tenant",
        ),
    )

    op.create_table(
        "rubric_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rubric_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("max_points", sa.Float(), nullable=False, server_default="10.0"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_rubric_criteria_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rubric_id"],
            ["rubrics.tenant_id", "rubrics.id"],
            ondelete="CASCADE",
            name="fk_rubric_criteria_rubric_tenant",
        ),
    )

    op.create_table(
        "rubric_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grading_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("awarded_points", sa.Float(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
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
            ["tenant_id", "grading_result_id"],
            ["grading_results.tenant_id", "grading_results.id"],
            ondelete="CASCADE",
            name="fk_rubric_scores_result_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "criterion_id"],
            ["rubric_criteria.tenant_id", "rubric_criteria.id"],
            ondelete="CASCADE",
            name="fk_rubric_scores_criterion_tenant",
        ),
    )

    op.create_table(
        "grading_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grading_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_score_percentage", sa.Float(), nullable=False),
        sa.Column("adjusted_score_percentage", sa.Float(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
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
            ["tenant_id", "grading_result_id"],
            ["grading_results.tenant_id", "grading_results.id"],
            ondelete="CASCADE",
            name="fk_grading_reviews_result_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_grading_reviews_reviewer_tenant",
        ),
    )
    op.create_index("ix_grading_reviews_tenant_id", "grading_reviews", ["tenant_id"])

    for table in TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
