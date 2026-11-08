from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.shared.schemas import APIModel


class QuestionOptionInput(BaseModel):
    key: str = Field(min_length=1, max_length=16)
    text: str = Field(min_length=1, max_length=1000)


class CreateQuestionInput(BaseModel):
    question_type: str = Field(
        default="multiple_choice",
        pattern=r"^(multiple_choice|true_false|short_answer)$",
    )
    prompt: str = Field(min_length=5)
    options: list[QuestionOptionInput] = Field(default_factory=list)
    correct_answer: str = Field(min_length=1, max_length=512)
    explanation: str | None = None
    points: float = Field(default=10.0, gt=0.0, le=1000.0)
    difficulty: str = Field(default="medium", pattern=r"^(easy|medium|hard)$")
    objective_ids: list[UUID] = Field(default_factory=list)


class CreateAssessmentRequest(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    assessment_type: str = Field(
        default="diagnostic",
        pattern=r"^(diagnostic|formative|summative|practice|follow_up)$",
    )
    passing_score_percentage: float = Field(default=75.0, ge=1.0, le=100.0)
    time_limit_minutes: int | None = Field(default=30, ge=1, le=600)
    max_attempts: int = Field(default=5, ge=1, le=50)
    questions: list[CreateQuestionInput] = Field(default_factory=list)
    existing_question_ids: list[UUID] = Field(default_factory=list)


class QuestionViewResponse(APIModel):
    id: UUID
    question_type: str
    prompt: str
    options: list[dict[str, Any]]
    points: float
    difficulty: str
    objective_ids: list[UUID] = Field(default_factory=list)
    correct_answer: str | None = None
    explanation: str | None = None


class AssessmentResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    title: str
    description: str | None = None
    assessment_type: str
    passing_score_percentage: float
    time_limit_minutes: int | None = None
    max_attempts: int
    status: str
    current_version_number: int
    published_version_id: UUID | None = None
    questions: list[QuestionViewResponse] = Field(default_factory=list)
    created_at: datetime


class SaveAttemptResponseRequest(BaseModel):
    selected_answer: str = Field(min_length=1, max_length=2000)


class AttemptResponseView(APIModel):
    question_id: UUID
    selected_answer: str
    is_correct: bool | None = None
    awarded_points: float = 0.0


class AttemptDetailResponse(APIModel):
    id: UUID
    tenant_id: UUID
    assessment_id: UUID
    assessment_version_id: UUID
    enrollment_id: UUID
    learner_membership_id: UUID
    attempt_number: int
    status: str
    started_at: datetime
    submitted_at: datetime | None = None
    questions: list[QuestionViewResponse] = Field(default_factory=list)
    responses: list[AttemptResponseView] = Field(default_factory=list)


class GradingReviewRequest(BaseModel):
    adjusted_score_percentage: float = Field(ge=0.0, le=100.0)
    feedback: str = Field(min_length=5, max_length=4000)


class GradingReviewView(APIModel):
    id: UUID
    reviewer_membership_id: UUID
    previous_score_percentage: float
    adjusted_score_percentage: float
    feedback: str
    reviewed_at: datetime


class GradingResultResponse(APIModel):
    id: UUID
    tenant_id: UUID
    attempt_id: UUID
    assessment_id: UUID
    assessment_version_id: UUID
    earned_points: float
    total_points: float
    score_percentage: float
    passed: bool
    grading_method: str
    objective_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    responses: list[AttemptResponseView] = Field(default_factory=list)
    reviews: list[GradingReviewView] = Field(default_factory=list)
    graded_at: datetime
