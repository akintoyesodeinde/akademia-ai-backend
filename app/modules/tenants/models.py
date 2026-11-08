from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    institution_type: Mapped[str] = mapped_column(
        String(64), default="university", nullable=False
    )  # school, university, training_provider, corporate
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, suspended, closed
    primary_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TenantSettings(Base, TenantOwnedMixin):
    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_settings_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_settings_tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    academic_integrity_policy: Mapped[str] = mapped_column(
        String(64), default="strict_during_assessment", nullable=False
    )
    ai_tutor_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_practice_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_locale: Mapped[str] = mapped_column(String(16), default="en-US", nullable=False)
    branding_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class TenantDomain(Base, TenantOwnedMixin):
    __tablename__ = "tenant_domains"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_tenant_domains_domain"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_domains_tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Cohort(Base, TenantOwnedMixin):
    __tablename__ = "cohorts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_cohorts_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_cohorts_tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class CohortMembership(Base, TenantOwnedMixin):
    __tablename__ = "cohort_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cohort_id", "membership_id", name="uq_cohort_memberships_unique"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cohort_id"],
            ["cohorts.tenant_id", "cohorts.id"],
            ondelete="CASCADE",
            name="fk_cohort_memberships_cohort_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_cohort_memberships_membership_tenant",
        ),
    )

    cohort_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role_in_cohort: Mapped[str] = mapped_column(String(32), default="learner", nullable=False)


class InstructorAssignment(Base, TenantOwnedMixin):
    __tablename__ = "instructor_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cohort_id", "membership_id", name="uq_instructor_assignments_cohort"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cohort_id"],
            ["cohorts.tenant_id", "cohorts.id"],
            ondelete="CASCADE",
            name="fk_instructor_assignments_cohort_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_instructor_assignments_membership_tenant",
        ),
    )

    cohort_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    assignment_scope: Mapped[str] = mapped_column(String(64), default="primary", nullable=False)
