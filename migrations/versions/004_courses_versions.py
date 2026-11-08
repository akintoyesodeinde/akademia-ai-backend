"""Migration 004 — Courses and immutable published versions

Revision ID: 004_courses_versions
Revises: 003_tenant_settings_structure
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "004_courses_versions"
down_revision: str | None = "003_tenant_settings_structure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "courses",
    "course_versions",
    "course_modules",
    "lessons",
    "learning_objectives",
    "lesson_objectives",
    "course_instructor_assignments",
)


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("current_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "academic_integrity_policy",
            sa.String(64),
            nullable=False,
            server_default="strict_during_assessment",
        ),
        sa.Column("created_by_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_courses_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_courses_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_courses_creator_membership_tenant",
        ),
    )
    op.create_index("ix_courses_tenant_id", "courses", ["tenant_id"])

    op.create_table(
        "course_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("snapshot_payload", postgresql.JSONB(), nullable=False),
        sa.Column("published_by_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "course_id", "version_number", name="uq_course_versions_num"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_course_versions_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_course_versions_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "published_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_course_versions_publisher_tenant",
        ),
    )
    op.create_index("ix_course_versions_tenant_id", "course_versions", ["tenant_id"])
    op.create_index("ix_course_versions_course_id", "course_versions", ["course_id"])

    op.create_table(
        "course_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_course_modules_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_course_modules_course_tenant",
        ),
    )
    op.create_index("ix_course_modules_tenant_id", "course_modules", ["tenant_id"])

    op.create_table(
        "lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="15"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_lessons_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_lessons_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "module_id"],
            ["course_modules.tenant_id", "course_modules.id"],
            ondelete="SET NULL",
            name="fk_lessons_module_tenant",
        ),
    )
    op.create_index("ix_lessons_tenant_id", "lessons", ["tenant_id"])
    op.create_index("ix_lessons_course_id", "lessons", ["course_id"])

    op.create_table(
        "learning_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mastery_threshold", sa.Integer(), nullable=False, server_default="75"),
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
        sa.UniqueConstraint("tenant_id", "course_id", "code", name="uq_learning_objectives_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_learning_objectives_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_learning_objectives_course_tenant",
        ),
    )
    op.create_index("ix_learning_objectives_tenant_id", "learning_objectives", ["tenant_id"])
    op.create_index("ix_learning_objectives_course_id", "learning_objectives", ["course_id"])

    op.create_table(
        "lesson_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "lesson_id", "objective_id", name="uq_lesson_objectives_pair"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lesson_id"],
            ["lessons.tenant_id", "lessons.id"],
            ondelete="CASCADE",
            name="fk_lesson_objectives_lesson_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_lesson_objectives_objective_tenant",
        ),
    )
    op.create_index("ix_lesson_objectives_tenant_id", "lesson_objectives", ["tenant_id"])

    op.create_table(
        "course_instructor_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_in_course", sa.String(32), nullable=False, server_default="lead"),
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
            "tenant_id", "course_id", "membership_id", name="uq_course_instructors_pair"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_course_instructors_course_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_course_instructors_membership_tenant",
        ),
    )
    op.create_index(
        "ix_course_instructor_assignments_tenant_id", "course_instructor_assignments", ["tenant_id"]
    )

    for table in TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
