"""Migration 002 — Roles, permissions, sessions, and invitations

Revision ID: 002_roles_sessions_invitations
Revises: 001_tenants_users_memberships
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.core.authorization import ROLE_PERMISSION_MAP, PermissionCode, TenantRole
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "002_roles_sessions_invitations"
down_revision: str | None = "001_tenants_users_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
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
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.String(512), nullable=True),
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
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
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
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),
    )

    op.create_table(
        "membership_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
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
            "tenant_id", "membership_id", "role_id", name="uq_membership_roles_unique"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_membership_roles_membership_tenant",
        ),
    )
    op.create_index("ix_membership_roles_tenant_id", "membership_roles", ["tenant_id"])
    op.create_index("ix_membership_roles_membership_id", "membership_roles", ["membership_id"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "active_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("csrf_token_hash", sa.String(128), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_refresh_token_hash", "sessions", ["refresh_token_hash"])

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("invited_by_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_invitations_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "invited_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="SET NULL",
            name="fk_invitations_inviter_tenant",
        ),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE roles, permissions, role_permissions, sessions, password_reset_tokens, email_verification_tokens TO akademia_app, akademia_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE roles, permissions, role_permissions, sessions, password_reset_tokens, email_verification_tokens TO akademia_readonly;"
    )

    for table in ("membership_roles", "invitations"):
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)

    # Seed baseline RBAC roles & permissions
    for perm in PermissionCode:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, description) VALUES (gen_random_uuid(), :code, :desc) ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=perm.value, desc=f"Permission {perm.value}")
        )

    role_descriptions = {
        TenantRole.OWNER.value: "Institution Owner with full administrative, commercial, and academic authority",
        TenantRole.ADMIN.value: "Tenant Administrator managing users, cohorts, courses, and compliance",
        TenantRole.INSTRUCTOR.value: "Instructor authoring courses, assessments, documents, and reviewing learner mastery",
        TenantRole.LEARNER.value: "Learner enrolling in courses, taking assessments, and using grounded AI tutoring",
    }
    for role_code, desc in role_descriptions.items():
        op.execute(
            sa.text(
                "INSERT INTO roles (id, code, name, description) VALUES (gen_random_uuid(), :code, :name, :desc) ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=role_code, name=role_code.capitalize(), desc=desc)
        )
        for perm_code in ROLE_PERMISSION_MAP.get(role_code, set()):
            op.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (id, role_id, permission_id)
                    SELECT gen_random_uuid(), r.id, p.id
                    FROM roles r, permissions p
                    WHERE r.code = :rcode AND p.code = :pcode
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                    """
                ).bindparams(rcode=role_code, pcode=perm_code)
            )

    # Narrow SECURITY DEFINER bootstrap function to resolve an invitation's tenant_id from token_hash
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_invitation_tenant_bootstrap(p_token_hash text)
        RETURNS uuid
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT i.tenant_id
            FROM invitations i
            WHERE i.token_hash = p_token_hash
              AND i.status = 'pending'
            LIMIT 1;
        $$;
        """
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION resolve_invitation_tenant_bootstrap(text) TO akademia_app, akademia_worker;"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_invitation_tenant_bootstrap(text);")
    for table in ("invitations", "membership_roles"):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
    op.drop_table("email_verification_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("invitations")
    op.drop_table("sessions")
    op.drop_table("membership_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
