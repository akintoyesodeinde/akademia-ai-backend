from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class Course(Base, TenantOwnedMixin):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_courses_tenant_code"),
        UniqueConstraint("tenant_id", "id", name="uq_courses_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_courses_creator_membership_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False
    )  # draft, published, archived
    current_version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    academic_integrity_policy: Mapped[str] = mapped_column(
        String(64), default="strict_during_assessment", nullable=False
    )
    created_by_membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class CourseVersion(Base, TenantOwnedMixin):
    """Immutable snapshot of a published course version (lessons, objectives, metadata)."""

    __tablename__ = "course_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "course_id", "version_number", name="uq_course_versions_num"),
        UniqueConstraint("tenant_id", "id", name="uq_course_versions_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_course_versions_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "published_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_course_versions_publisher_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_by_membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CourseModule(Base, TenantOwnedMixin):
    __tablename__ = "course_modules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_course_modules_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_course_modules_course_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Lesson(Base, TenantOwnedMixin):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_lessons_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_lessons_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "module_id"],
            ["course_modules.tenant_id", "course_modules.id"],
            ondelete="SET NULL",
            name="fk_lessons_module_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    module_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)


class LearningObjective(Base, TenantOwnedMixin):
    __tablename__ = "learning_objectives"
    __table_args__ = (
        UniqueConstraint("tenant_id", "course_id", "code", name="uq_learning_objectives_code"),
        UniqueConstraint("tenant_id", "id", name="uq_learning_objectives_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_learning_objectives_course_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mastery_threshold: Mapped[int] = mapped_column(Integer, default=75, nullable=False)


class LessonObjective(Base, TenantOwnedMixin):
    __tablename__ = "lesson_objectives"
    __table_args__ = (
        UniqueConstraint("tenant_id", "lesson_id", "objective_id", name="uq_lesson_objectives_pair"),
        ForeignKeyConstraint(
            ["tenant_id", "lesson_id"],
            ["lessons.tenant_id", "lessons.id"],
            ondelete="CASCADE",
            name="fk_lesson_objectives_lesson_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_lesson_objectives_objective_tenant",
        ),
    )

    lesson_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    objective_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


class CourseInstructorAssignment(Base, TenantOwnedMixin):
    __tablename__ = "course_instructor_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "course_id", "membership_id", name="uq_course_instructors_pair"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_course_instructors_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_course_instructors_membership_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role_in_course: Mapped[str] = mapped_column(String(32), default="lead", nullable=False)
