from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin, TimestampMixin


class SubscriptionPlan(Base, TimestampMixin):
    __tablename__ = "subscription_plans"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    monthly_price_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_active_users: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_published_courses: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_ai_requests_per_month: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    max_storage_bytes: Mapped[int] = mapped_column(
        BigInteger, default=500 * 1024 * 1024, nullable=False
    )
    max_monthly_tokens: Mapped[int] = mapped_column(BigInteger, default=500000, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlanEntitlement(Base, TimestampMixin):
    __tablename__ = "plan_entitlements"
    __table_args__ = (
        UniqueConstraint("plan_id", "feature_key", name="uq_plan_entitlements_feature"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TenantSubscription(Base, TenantOwnedMixin):
    __tablename__ = "tenant_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, past_due, cancelled
    billing_provider: Mapped[str] = mapped_column(
        String(64), default="invoiced_contract", nullable=False
    )
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantUsageRecord(Base, TenantOwnedMixin):
    __tablename__ = "tenant_usage_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "period_month", name="uq_tenant_usage_period"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    active_users_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_courses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_bytes_used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    monthly_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    estimated_ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class BillingEvent(Base, TenantOwnedMixin):
    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_event_id", name="uq_billing_events_ext_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class IdempotencyRecord(Base, TenantOwnedMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", "operation_scope", name="uq_idempotency_key_scope"
        ),
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    operation_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
