from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.shared.schemas import APIModel


class ObjectiveMasteryResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    learner_membership_id: UUID
    objective_id: UUID
    objective_code: str
    objective_title: str
    mastery_threshold: int
    mastery_score: float
    mastery_status: str
    attempts_count: int
    incorrect_streak: int
    prior_score: float | None = None
    score_delta: float | None = None
    calculation_version: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    last_evaluated_at: datetime


class RecommendationResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    learner_membership_id: UUID
    objective_id: UUID
    objective_code: str = ""
    objective_title: str = ""
    recommendation_type: str
    title: str
    reason_explanation: str
    calculation_version: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    learner_feedback: str | None = None
    feedback_comment: str | None = None
    created_at: datetime


class RecommendationFeedbackRequest(BaseModel):
    feedback: str = Field(pattern=r"^(helpful|too_easy|too_hard|not_relevant)$")
    comment: str | None = Field(default=None, max_length=1000)


class LearnerProgressSummaryResponse(APIModel):
    learner_membership_id: UUID
    enrolled_courses_count: int
    average_completion_percentage: float
    average_assessment_score: float | None = None
    mastered_objectives_count: int
    gap_objectives_count: int
    active_recommendations_count: int
    course_progress: list[dict[str, Any]] = Field(default_factory=list)
    recent_attempts: list[dict[str, Any]] = Field(default_factory=list)


class CourseAnalyticsResponse(APIModel):
    course_id: UUID
    course_title: str
    enrolled_learners_count: int
    average_completion_percentage: float
    submitted_attempts_count: int
    average_assessment_score: float | None = None
    objective_analytics: list[dict[str, Any]] = Field(default_factory=list)
    learner_summaries: list[dict[str, Any]] = Field(default_factory=list)


class CohortProgressResponse(APIModel):
    cohort_id: UUID
    cohort_name: str
    cohort_code: str
    learners_count: int
    average_completion_percentage: float
    average_mastery_score: float
    members_progress: list[dict[str, Any]] = Field(default_factory=list)
