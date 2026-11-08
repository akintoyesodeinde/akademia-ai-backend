from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class AIGenerationReview(Base, TenantOwnedMixin):
    __tablename__ = "ai_generation_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "ai_job_id"],
            ["ai_jobs.tenant_id", "ai_jobs.id"],
            ondelete="CASCADE",
            name="fk_ai_gen_reviews_job_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "question_id"],
            ["questions.tenant_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_ai_gen_reviews_question_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reviewer_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="SET NULL",
            name="fk_ai_gen_reviews_reviewer_tenant",
        ),
    )

    ai_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    question_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    validation_outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(32), default="pending_review", nullable=False
    )  # pending_review, approved, rejected
    reviewer_membership_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
