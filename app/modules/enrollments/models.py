from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class Enrollment(Base, TenantOwnedMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "course_id", "membership_id", name="uq_enrollments_course_member"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_enrollments_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_enrollments_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "course_version_id"],
            ["course_versions.tenant_id", "course_versions.id"],
            ondelete="RESTRICT",
            name="fk_enrollments_course_version_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_enrollments_membership_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cohort_id"],
            ["cohorts.tenant_id", "cohorts.id"],
            ondelete="SET NULL",
            name="fk_enrollments_cohort_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    course_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    cohort_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, completed, withdrawn
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningEvent(Base, TenantOwnedMixin):
    __tablename__ = "learning_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "enrollment_id"],
            ["enrollments.tenant_id", "enrollments.id"],
            ondelete="CASCADE",
            name="fk_learning_events_enrollment_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "lesson_id"],
            ["lessons.tenant_id", "lessons.id"],
            ondelete="SET NULL",
            name="fk_learning_events_lesson_tenant",
        ),
    )

    enrollment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    lesson_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # lesson_viewed, lesson_completed, assessment_submitted
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ProgressSnapshot(Base, TenantOwnedMixin):
    __tablename__ = "progress_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "enrollment_id", name="uq_progress_snapshots_enrollment"),
        ForeignKeyConstraint(
            ["tenant_id", "enrollment_id"],
            ["enrollments.tenant_id", "enrollments.id"],
            ondelete="CASCADE",
            name="fk_progress_snapshots_enrollment_tenant",
        ),
    )

    enrollment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    lessons_completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_lessons_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latest_assessment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mastered_objectives_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_objectives_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
