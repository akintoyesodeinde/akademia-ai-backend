"""Migration 005 — Enrollment and learning events

Revision ID: 005_enrollments_events
Revises: 004_courses_versions
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "005_enrollments_events"
down_revision: str | None = "004_courses_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("enrollments", "learning_events", "progress_snapshots")


def upgrade() -> None:
    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
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
        sa.UniqueConstraint(
            "tenant_id", "course_id", "membership_id", name="uq_enrollments_course_member"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_enrollments_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_enrollments_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_version_id"],
            ["course_versions.tenant_id", "course_versions.id"],
            ondelete="RESTRICT",
            name="fk_enrollments_course_version_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_enrollments_membership_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "cohort_id"],
            ["cohorts.tenant_id", "cohorts.id"],
            ondelete="SET NULL",
            name="fk_enrollments_cohort_tenant",
        ),
    )
    op.create_index("ix_enrollments_tenant_id", "enrollments", ["tenant_id"])
    op.create_index("ix_enrollments_membership_id", "enrollments", ["membership_id"])

    op.create_table(
        "learning_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "event_metadata",
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
            ["tenant_id", "enrollment_id"],
            ["enrollments.tenant_id", "enrollments.id"],
            ondelete="CASCADE",
            name="fk_learning_events_enrollment_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lesson_id"],
            ["lessons.tenant_id", "lessons.id"],
            ondelete="SET NULL",
            name="fk_learning_events_lesson_tenant",
        ),
    )
    op.create_index("ix_learning_events_tenant_id", "learning_events", ["tenant_id"])
    op.create_index("ix_learning_events_enrollment_id", "learning_events", ["enrollment_id"])

    op.create_table(
        "progress_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lessons_completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_lessons_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latest_assessment_score", sa.Float(), nullable=True),
        sa.Column("mastered_objectives_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_objectives_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("tenant_id", "enrollment_id", name="uq_progress_snapshots_enrollment"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "enrollment_id"],
            ["enrollments.tenant_id", "enrollments.id"],
            ondelete="CASCADE",
            name="fk_progress_snapshots_enrollment_tenant",
        ),
    )
    op.create_index("ix_progress_snapshots_tenant_id", "progress_snapshots", ["tenant_id"])

    for table in TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
