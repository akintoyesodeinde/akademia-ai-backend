from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.db.session import get_db_session
from app.modules.learning_intelligence.schemas import (
    CohortProgressResponse,
    CourseAnalyticsResponse,
    LearnerProgressSummaryResponse,
    ObjectiveMasteryResponse,
    RecommendationFeedbackRequest,
    RecommendationResponse,
)
from app.modules.learning_intelligence.service import LearningIntelligenceService

router = APIRouter(tags=["Learning Intelligence & Analytics"])


@router.get(
    "/learners/me/progress",
    response_model=LearnerProgressSummaryResponse,
)
async def get_my_progress(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> LearnerProgressSummaryResponse:
    svc = LearningIntelligenceService(session)
    return await svc.get_my_progress(principal)


@router.get(
    "/learners/me/mastery",
    response_model=list[ObjectiveMasteryResponse],
)
async def get_my_mastery(
    course_id: UUID | None = Query(default=None),
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[ObjectiveMasteryResponse]:
    svc = LearningIntelligenceService(session)
    return await svc.get_my_mastery(principal, course_id=course_id)


@router.get(
    "/learners/me/recommendations",
    response_model=list[RecommendationResponse],
)
async def get_my_recommendations(
    course_id: UUID | None = Query(default=None),
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[RecommendationResponse]:
    svc = LearningIntelligenceService(session)
    return await svc.get_my_recommendations(principal, course_id=course_id)


@router.post(
    "/recommendations/{recommendation_id}/feedback",
    response_model=RecommendationResponse,
)
async def submit_recommendation_feedback(
    recommendation_id: UUID,
    req: RecommendationFeedbackRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> RecommendationResponse:
    svc = LearningIntelligenceService(session)
    return await svc.submit_recommendation_feedback(
        principal=principal, recommendation_id=recommendation_id, req=req
    )


@router.get(
    "/courses/{course_id}/analytics",
    response_model=CourseAnalyticsResponse,
)
async def get_course_analytics(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CourseAnalyticsResponse:
    svc = LearningIntelligenceService(session)
    return await svc.get_course_analytics(principal, course_id)


@router.get(
    "/cohorts/{cohort_id}/progress",
    response_model=CohortProgressResponse,
)
async def get_cohort_progress(
    cohort_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CohortProgressResponse:
    svc = LearningIntelligenceService(session)
    return await svc.get_cohort_progress(principal, cohort_id)
