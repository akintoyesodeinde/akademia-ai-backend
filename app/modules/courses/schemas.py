from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.shared.schemas import APIModel


class CreateCourseRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    academic_integrity_policy: str = Field(
        default="strict_during_assessment",
        pattern=r"^(strict_during_assessment|guided_hints_allowed|open_book)$",
    )


class UpdateCourseRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    academic_integrity_policy: str | None = Field(
        default=None,
        pattern=r"^(strict_during_assessment|guided_hints_allowed|open_book)$",
    )


class CreateObjectiveRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    mastery_threshold: int = Field(default=75, ge=10, le=100)


class ObjectiveResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    code: str
    title: str
    description: str | None = None
    mastery_threshold: int
    created_at: datetime


class CreateLessonRequest(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content_markdown: str = Field(min_length=5)
    position: int = Field(default=1, ge=1)
    estimated_minutes: int = Field(default=15, ge=1, le=600)
    objective_ids: list[UUID] = Field(default_factory=list)


class UpdateLessonRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    content_markdown: str | None = Field(default=None, min_length=5)
    position: int | None = Field(default=None, ge=1)
    estimated_minutes: int | None = Field(default=None, ge=1, le=600)
    objective_ids: list[UUID] | None = None


class LessonResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    title: str
    content_markdown: str
    position: int
    estimated_minutes: int
    objective_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime


class CourseVersionResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    version_number: int
    title: str
    description: str | None = None
    snapshot_payload: dict[str, Any]
    published_by_membership_id: UUID
    published_at: datetime


class CourseResponse(APIModel):
    id: UUID
    tenant_id: UUID
    code: str
    title: str
    description: str | None = None
    status: str
    current_version_number: int
    published_version_id: UUID | None = None
    academic_integrity_policy: str
    created_by_membership_id: UUID
    objectives: list[ObjectiveResponse] = Field(default_factory=list)
    lessons_count: int = 0
    created_at: datetime
    updated_at: datetime


class EnrollRequest(BaseModel):
    membership_id: UUID | None = None
    cohort_id: UUID | None = None


class EnrollmentResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    course_title: str
    course_code: str
    course_version_id: UUID
    membership_id: UUID
    cohort_id: UUID | None = None
    status: str
    completion_percentage: float = 0.0
    lessons_completed_count: int = 0
    total_lessons_count: int = 0
    created_at: datetime
