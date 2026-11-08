from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.db.session import get_db_session
from app.modules.assessments.schemas import (
    AssessmentResponse,
    AttemptDetailResponse,
    AttemptResponseView,
    CreateAssessmentRequest,
    GradingResultResponse,
    GradingReviewRequest,
    SaveAttemptResponseRequest,
)
from app.modules.assessments.service import AssessmentService

router = APIRouter(tags=["Assessments & Grading"])


@router.post(
    "/courses/{course_id}/assessments",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    course_id: UUID,
    req: CreateAssessmentRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentResponse:
    svc = AssessmentService(session)
    return await svc.create_assessment(
        principal=principal, course_id=course_id, req=req
    )


@router.get(
    "/courses/{course_id}/assessments",
    response_model=list[AssessmentResponse],
)
async def list_course_assessments(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[AssessmentResponse]:
    svc = AssessmentService(session)
    return await svc.list_course_assessments(principal, course_id)


@router.post(
    "/assessments/{assessment_id}/publish",
    response_model=AssessmentResponse,
)
async def publish_assessment(
    assessment_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentResponse:
    svc = AssessmentService(session)
    return await svc.publish_assessment(
        principal=principal, assessment_id=assessment_id
    )


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment(
    assessment_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AssessmentResponse:
    svc = AssessmentService(session)
    return await svc.get_assessment(principal, assessment_id)


@router.post(
    "/assessments/{assessment_id}/attempts",
    response_model=AttemptDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_assessment_attempt(
    assessment_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AttemptDetailResponse:
    svc = AssessmentService(session)
    return await svc.start_attempt(principal=principal, assessment_id=assessment_id)


@router.put(
    "/attempts/{attempt_id}/responses/{question_id}",
    response_model=AttemptResponseView,
)
async def save_attempt_response(
    attempt_id: UUID,
    question_id: UUID,
    req: SaveAttemptResponseRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AttemptResponseView:
    svc = AssessmentService(session)
    return await svc.save_response(
        principal=principal,
        attempt_id=attempt_id,
        question_id=question_id,
        req=req,
    )


@router.post("/attempts/{attempt_id}/submit", response_model=GradingResultResponse)
async def submit_attempt(
    attempt_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> GradingResultResponse:
    svc = AssessmentService(session)
    return await svc.submit_attempt(principal=principal, attempt_id=attempt_id)


@router.get("/attempts/{attempt_id}/results", response_model=GradingResultResponse)
async def get_attempt_results(
    attempt_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> GradingResultResponse:
    svc = AssessmentService(session)
    return await svc.get_attempt_results(principal=principal, attempt_id=attempt_id)


@router.post(
    "/grading-results/{result_id}/review",
    response_model=GradingResultResponse,
)
async def review_grading_result(
    result_id: UUID,
    req: GradingReviewRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> GradingResultResponse:
    svc = AssessmentService(session)
    return await svc.review_grading_result(
        principal=principal, result_id=result_id, req=req
    )
