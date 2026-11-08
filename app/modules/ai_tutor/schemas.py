from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.ai.contracts import CitationReference
from app.shared.schemas import APIModel


class CreateTutorConversationRequest(BaseModel):
    title: str = Field(default="Course Study Session", min_length=2, max_length=255)
    complexity_level: str = Field(
        default="standard",
        pattern=r"^(foundational|standard|advanced)$",
    )


class SendTutorMessageRequest(BaseModel):
    content: str = Field(min_length=2, max_length=4000)


class TutorMessageResponse(APIModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    role: str
    content: str
    grounding_status: str
    citations: list[CitationReference] = Field(default_factory=list)
    prompt_version: str
    model_id: str
    token_usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TutorConversationResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    membership_id: UUID
    title: str
    complexity_level: str
    status: str
    messages: list[TutorMessageResponse] = Field(default_factory=list)
    created_at: datetime


class CreatePracticeJobRequest(BaseModel):
    objective_id: UUID
    difficulty: str = Field(default="medium", pattern=r"^(easy|medium|hard)$")
    question_count: int = Field(default=2, ge=1, le=5)


class AIJobResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    requested_by_membership_id: UUID
    job_type: str
    status: str
    input_params: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    attempt_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class PracticeDraftReviewResponse(APIModel):
    review_id: UUID
    ai_job_id: UUID
    question_id: UUID
    course_id: UUID
    prompt: str
    options: list[dict[str, Any]]
    correct_answer: str
    explanation: str | None = None
    difficulty: str
    question_status: str
    review_status: str
    prompt_version: str
    model_id: str
    source_references: list[dict[str, Any]]
    validation_outcome: dict[str, Any]
    reviewer_notes: str | None = None
    reviewed_at: datetime | None = None


class ReviewPracticeDraftRequest(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")
    reviewer_notes: str | None = Field(default=None, max_length=2000)
    prompt_override: str | None = None
    correct_answer_override: str | None = None
