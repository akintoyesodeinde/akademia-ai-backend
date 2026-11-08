"""Migration 003 — Tenant settings and institutional structure

Revision ID: 003_tenant_settings_structure
Revises: 002_roles_sessions_invitations
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "003_tenant_settings_structure"
down_revision: str | None = "002_roles_sessions_invitations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "tenant_settings",
    "tenant_domains",
    "cohorts",
    "cohort_memberships",
    "instructor_assignments",
)


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "academic_integrity_policy",
            sa.String(64),
            nullable=False,
            server_default="strict_during_assessment",
        ),
        sa.Column("ai_tutor_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "ai_practice_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("default_locale", sa.String(16), nullable=False, server_default="en-US"),
        sa.Column(
            "branding_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "feature_flags",
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
        sa.UniqueConstraint("tenant_id", name="uq_tenant_settings_tenant"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_settings_tenant_id"),
    )

    op.create_table(
        "tenant_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verification_token_hash", sa.String(128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("domain", name="uq_tenant_domains_domain"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_domains_tenant_id"),
    )

    op.create_table(
        "cohorts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "code", name="uq_cohorts_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cohorts_tenant_id"),
    )
    op.create_index("ix_cohorts_tenant_id", "cohorts", ["tenant_id"])

    op.create_table(
        "cohort_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_in_cohort", sa.String(32), nullable=False, server_default="learner"),
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
            "tenant_id", "cohort_id", "membership_id", name="uq_cohort_memberships_unique"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "cohort_id"],
            ["cohorts.tenant_id", "cohorts.id"],
            ondelete="CASCADE",
            name="fk_cohort_memberships_cohort_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_cohort_memberships_membership_tenant",
        ),
    )
    op.create_index("ix_cohort_memberships_tenant_id", "cohort_memberships", ["tenant_id"])

    op.create_table(
        "instructor_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_scope", sa.String(64), nullable=False, server_default="primary"),
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
            "tenant_id", "cohort_id", "membership_id", name="uq_instructor_assignments_cohort"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "cohort_id"],
            ["cohorts.tenant_id", "cohorts.id"],
            ondelete="CASCADE",
            name="fk_instructor_assignments_cohort_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_instructor_assignments_membership_tenant",
        ),
    )
    op.create_index("ix_instructor_assignments_tenant_id", "instructor_assignments", ["tenant_id"])

    for table in TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
