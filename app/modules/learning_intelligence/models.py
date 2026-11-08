from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
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


class LearnerObjectiveMastery(Base, TenantOwnedMixin):
    __tablename__ = "learner_objective_mastery"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "learner_membership_id",
            "objective_id",
            name="uq_learner_objective_mastery_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_mastery_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_mastery_learner_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_mastery_objective_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    learner_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    objective_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mastery_status: Mapped[str] = mapped_column(
        String(32), default="developing", nullable=False
    )  # gap_detected, developing, mastered
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prior_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculation_version: Mapped[str] = mapped_column(
        String(64), default="rule-engine-v1", nullable=False
    )
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Recommendation(Base, TenantOwnedMixin):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_recommendations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_recommendations_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_recommendations_learner_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "objective_id"],
            ["learning_objectives.tenant_id", "learning_objectives.id"],
            ondelete="CASCADE",
            name="fk_recommendations_objective_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    learner_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    objective_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    recommendation_type: Mapped[str] = mapped_column(
        String(64), default="targeted_practice", nullable=False
    )  # targeted_practice, lesson_review, follow_up_assessment
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_version: Mapped[str] = mapped_column(
        String(64), default="rule-engine-v1", nullable=False
    )
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, completed, dismissed
    learner_feedback: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class RemediationPlan(Base, TenantOwnedMixin):
    __tablename__ = "remediation_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_remediation_plans_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_remediation_plans_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "learner_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_remediation_plans_learner_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    learner_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class RemediationPlanItem(Base, TenantOwnedMixin):
    __tablename__ = "remediation_plan_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "remediation_plan_id"],
            ["remediation_plans.tenant_id", "remediation_plans.id"],
            ondelete="CASCADE",
            name="fk_remediation_items_plan_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "recommendation_id"],
            ["recommendations.tenant_id", "recommendations.id"],
            ondelete="SET NULL",
            name="fk_remediation_items_rec_tenant",
        ),
    )

    remediation_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    recommendation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
