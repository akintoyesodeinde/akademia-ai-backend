"""Migration 001 — Extensions, tenants, users, and memberships

Revision ID: 001_tenants_users_memberships
Revises: None
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "001_tenants_users_memberships"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("institution_type", sa.String(64), nullable=False, server_default="university"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("primary_contact_email", sa.String(255), nullable=True),
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
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("external_idp_subject", sa.String(255), nullable=True, unique=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("title", sa.String(128), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
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
            "tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_memberships_tenant_id"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE tenants, users TO akademia_app, akademia_worker;"
    )
    op.execute("GRANT SELECT ON TABLE tenants, users TO akademia_readonly;")

    for stmt in build_enable_rls_sql("tenant_memberships"):
        op.execute(stmt)

    # Narrow SECURITY DEFINER bootstrap function so a logged-in user can discover which
    # tenants they belong to before `app.tenant_id` is established, without weakening RLS.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_user_memberships_bootstrap(p_user_id uuid)
        RETURNS TABLE (
            membership_id uuid,
            tenant_id uuid,
            membership_status varchar,
            tenant_name varchar,
            tenant_slug varchar,
            tenant_status varchar
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT
                tm.id AS membership_id,
                tm.tenant_id AS tenant_id,
                tm.status AS membership_status,
                t.name AS tenant_name,
                t.slug AS tenant_slug,
                t.status AS tenant_status
            FROM tenant_memberships tm
            JOIN tenants t ON t.id = tm.tenant_id
            WHERE tm.user_id = p_user_id
              AND tm.status = 'active'
              AND t.status = 'active'
            ORDER BY tm.created_at ASC;
        $$;
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION get_user_memberships_bootstrap(uuid) TO akademia_app, akademia_worker;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_user_memberships_bootstrap(uuid);")
    for stmt in build_disable_rls_sql("tenant_memberships"):
        op.execute(stmt)
    op.drop_table("tenant_memberships")
    op.drop_table("users")
    op.drop_table("tenants")
