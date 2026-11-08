from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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


class Assessment(Base, TenantOwnedMixin):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assessments_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_assessments_course_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_type: Mapped[str] = mapped_column(
        String(32), default="diagnostic", nullable=False
    )  # diagnostic, formative, summative, practice, follow_up
    passing_score_percentage: Mapped[float] = mapped_column(Float, default=75.0, nullable=False)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False
    )  # draft, published, archived
    current_version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class AssessmentVersion(Base, TenantOwnedMixin):
    """Immutable snapshot of a published assessment and its exact questions and answer keys."""

    __tablename__ = "assessment_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "assessment_id", "version_number", name="uq_assessment_versions_num"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_assessment_versions_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_assessment_versions_assessment_tenant",
        ),
    )

    assessment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    passing_score_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    total_points: Mapped[float] = mapped_column(Float, nullable=False)
    questions_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Question(Base, TenantOwnedMixin):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_questions_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_questions_course_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    question_type: Mapped[str] = mapped_column(
        String(32), default="multiple_choice", nullable=False
    )  # multiple_choice, true_false, short_answer
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(512), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), default="instructor", nullable=False
    )  # instructor, ai_generated
    status: Mapped[str] = mapped_column(
        String(32), default="approved", nullable=False
    )  # draft, approved, rejected


class AssessmentItem(Base, TenantOwnedMixin):
    __tablename__ = "assessment_items"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "assessment_id", "question_id", name="uq_assessment_items_pair"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_assessment_items_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_assessment_items_assessment_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "question_id"],
            ["questions.tenant_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_assessment_items_question_tenant",
        ),
    )

    assessment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    question_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    points_override: Mapped[float | None] = mapped_column(Float, nullable=True)


class AssessmentItemObjective(Base, TenantOwnedMixin):
    __tablename__ = "assessment_item_objectives"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "question_id", "objective_id", name="uq_question_objectives_pair"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "question_id"],
            ["questions.tenant_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_item_objectives_question_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_item_objectives_objective_tenant",
        ),
    )

    question_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    objective_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


class AssessmentAttempt(Base, TenantOwnedMixin):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_assessment_attempts_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_attempts_assessment_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_version_id"],
            ["assessment_versions.tenant_id", "assessment_versions.id"],
            ondelete="RESTRICT",
            name="fk_attempts_version_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "enrollment_id"],
            ["enrollments.tenant_id", "enrollments.id"],
            ondelete="CASCADE",
            name="fk_attempts_enrollment_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_attempts_learner_membership_tenant",
        ),
    )

    assessment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    assessment_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    enrollment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    learner_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="in_progress", nullable=False
    )  # in_progress, submitted, graded
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttemptResponse(Base, TenantOwnedMixin):
    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "attempt_id", "question_id", name="uq_responses_attempt_q"),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id"],
            ["assessment_attempts.tenant_id", "assessment_attempts.id"],
            ondelete="CASCADE",
            name="fk_responses_attempt_tenant",
        ),
    )

    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    question_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    selected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    awarded_points: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GradingResult(Base, TenantOwnedMixin):
    __tablename__ = "grading_results"
    __table_args__ = (
        UniqueConstraint("tenant_id", "attempt_id", name="uq_grading_results_attempt"),
        UniqueConstraint("tenant_id", "id", name="uq_grading_results_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "attempt_id"],
            ["assessment_attempts.tenant_id", "assessment_attempts.id"],
            ondelete="CASCADE",
            name="fk_grading_results_attempt_tenant",
        ),
    )

    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    earned_points: Mapped[float] = mapped_column(Float, nullable=False)
    total_points: Mapped[float] = mapped_column(Float, nullable=False)
    score_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grading_method: Mapped[str] = mapped_column(
        String(32), default="deterministic_v1", nullable=False
    )
    objective_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Rubric(Base, TenantOwnedMixin):
    __tablename__ = "rubrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_rubrics_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessments.tenant_id", "assessments.id"],
            ondelete="CASCADE",
            name="fk_rubrics_assessment_tenant",
        ),
    )

    assessment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)


class RubricCriterion(Base, TenantOwnedMixin):
    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_rubric_criteria_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "rubric_id"],
            ["rubrics.tenant_id", "rubrics.id"],
            ondelete="CASCADE",
            name="fk_rubric_criteria_rubric_tenant",
        ),
    )

    rubric_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    max_points: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)


class RubricScore(Base, TenantOwnedMixin):
    __tablename__ = "rubric_scores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "grading_result_id"],
            ["grading_results.tenant_id", "grading_results.id"],
            ondelete="CASCADE",
            name="fk_rubric_scores_result_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "criterion_id"],
            ["rubric_criteria.tenant_id", "rubric_criteria.id"],
            ondelete="CASCADE",
            name="fk_rubric_scores_criterion_tenant",
        ),
    )

    grading_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    criterion_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    awarded_points: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class GradingReview(Base, TenantOwnedMixin):
    __tablename__ = "grading_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "grading_result_id"],
            ["grading_results.tenant_id", "grading_results.id"],
            ondelete="CASCADE",
            name="fk_grading_reviews_result_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewer_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_grading_reviews_reviewer_tenant",
        ),
    )

    grading_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    reviewer_membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    previous_score_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_score_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
