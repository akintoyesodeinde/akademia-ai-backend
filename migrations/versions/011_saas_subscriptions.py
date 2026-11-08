"""Migration 011 — SaaS subscriptions and entitlements

Revision ID: 011_saas_subscriptions
Revises: 010_learning_intelligence
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.db.rls import build_disable_rls_sql, build_enable_rls_sql
from sqlalchemy.dialects import postgresql

revision: str = "011_saas_subscriptions"
down_revision: str | None = "010_learning_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "tenant_subscriptions",
    "tenant_usage_records",
    "billing_events",
    "idempotency_records",
)


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("monthly_price_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_active_users", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("max_published_courses", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_ai_requests_per_month", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("max_storage_bytes", sa.BigInteger(), nullable=False, server_default="524288000"),
        sa.Column("max_monthly_tokens", sa.BigInteger(), nullable=False, server_default="500000"),
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
    )

    op.create_table(
        "plan_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("limit_value", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("plan_id", "feature_key", name="uq_plan_entitlements_feature"),
    )

    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "billing_provider", sa.String(64), nullable=False, server_default="invoiced_contract"
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
    )

    op.create_table(
        "tenant_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_month", sa.String(7), nullable=False),
        sa.Column("active_users_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_courses_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_requests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_bytes_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("monthly_tokens_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("estimated_ai_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
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
        sa.UniqueConstraint("tenant_id", "period_month", name="uq_tenant_usage_period"),
    )

    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "payload",
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
        sa.UniqueConstraint("tenant_id", "external_event_id", name="uq_billing_events_ext_id"),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("operation_scope", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
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
            "tenant_id", "idempotency_key", "operation_scope", name="uq_idempotency_key_scope"
        ),
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE subscription_plans, plan_entitlements TO akademia_app, akademia_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE subscription_plans, plan_entitlements TO akademia_readonly;"
    )

    for table in TENANT_TABLES:
        for stmt in build_enable_rls_sql(table):
            op.execute(stmt)

    # Seed standard SaaS commercial plans
    op.execute(
        """
        INSERT INTO subscription_plans (
            id, code, name, monthly_price_usd, max_active_users, max_published_courses,
            max_ai_requests_per_month, max_storage_bytes, max_monthly_tokens, is_active
        )
        VALUES
            (gen_random_uuid(), 'starter', 'Academic Starter', 0.0, 50, 10, 500, 524288000::bigint, 500000::bigint, true),
            (gen_random_uuid(), 'professional', 'Professional Institution', 299.0, 500, 100, 5000, 5242880000::bigint, 5000000::bigint, true),
            (gen_random_uuid(), 'institution_pro', 'Institution Pro', 299.0, 500, 100, 5000, 5242880000::bigint, 5000000::bigint, true),
            (gen_random_uuid(), 'enterprise', 'University & Corporate Enterprise', 999.0, 10000, 1000, 50000, 52428800000::bigint, 50000000::bigint, true)
        ON CONFLICT (code) DO NOTHING;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for stmt in build_disable_rls_sql(table):
            op.execute(stmt)
        op.drop_table(table)
    op.drop_table("plan_entitlements")
    op.drop_table("subscription_plans")
