from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

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

from app.db.base import Base, TenantOwnedMixin, TimestampMixin


class AIConversation(Base, TenantOwnedMixin):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_conversations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_ai_conversations_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_ai_conversations_membership_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    complexity_level: Mapped[str] = mapped_column(
        String(32), default="standard", nullable=False
    )  # foundational, standard, advanced
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class AIMessage(Base, TenantOwnedMixin):
    __tablename__ = "ai_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["ai_conversations.tenant_id", "ai_conversations.id"],
            ondelete="CASCADE",
            name="fk_ai_messages_conversation_tenant",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    grounding_status: Mapped[str] = mapped_column(
        String(32), default="grounded", nullable=False
    )  # grounded, insufficient_course_material, integrity_restricted, user_query
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String(64), default="tutor-rag-v1", nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(128), default="akademia-grounded-v1", nullable=False)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class AIJob(Base, TenantOwnedMixin):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_jobs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "course_id"],
            ["courses.tenant_id", "courses.id"],
            ondelete="CASCADE",
            name="fk_ai_jobs_course_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requested_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_ai_jobs_requester_tenant",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    requested_by_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # practice_generation, document_embedding
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False
    )  # queued, processing, completed, failed, cancelled
    input_params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIUsageRecord(Base, TenantOwnedMixin):
    __tablename__ = "ai_usage_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="SET NULL",
            name="fk_ai_usage_membership_tenant",
        ),
    )

    membership_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    operation_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # tutor_chat, practice_generation, document_embedding
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PromptVersion(Base, TimestampMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_key", "version", name="uq_prompt_versions_key_ver"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    system_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AIEvaluationRecord(Base, TimestampMixin):
    __tablename__ = "ai_evaluations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_recall_at_5: Mapped[float] = mapped_column(Float, nullable=False)
    citation_authorization_rate: Mapped[float] = mapped_column(Float, nullable=False)
    groundedness_score: Mapped[float] = mapped_column(Float, nullable=False)
    answer_relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    unauthorized_leak_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    structured_validity_rate: Mapped[float] = mapped_column(Float, nullable=False)
    metrics_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
