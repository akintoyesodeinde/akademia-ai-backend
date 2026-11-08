from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.ai_tutor.schemas import (
    AIJobResponse,
    CreatePracticeJobRequest,
    CreateTutorConversationRequest,
    PracticeDraftReviewResponse,
    ReviewPracticeDraftRequest,
    SendTutorMessageRequest,
    TutorConversationResponse,
    TutorMessageResponse,
)
from app.modules.ai_tutor.service import AITutorService
from app.shared.rate_limit import rate_limiter

router = APIRouter(tags=["AI Tutor & Practice Generation"])


@router.post(
    "/courses/{course_id}/tutor/conversations",
    response_model=TutorConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tutor_conversation(
    course_id: UUID,
    req: CreateTutorConversationRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TutorConversationResponse:
    svc = AITutorService(session)
    return await svc.create_conversation(
        principal=principal, course_id=course_id, req=req
    )


@router.get(
    "/courses/{course_id}/tutor/conversations",
    response_model=list[TutorConversationResponse],
)
async def list_course_tutor_conversations(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[TutorConversationResponse]:
    svc = AITutorService(session)
    return await svc.list_course_conversations(principal, course_id)


@router.post(
    "/tutor/conversations/{conversation_id}/messages",
    response_model=TutorMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_tutor_message(
    conversation_id: UUID,
    req: SendTutorMessageRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TutorMessageResponse:
    settings = get_settings()
    rate_limiter.check(
        f"ai:tutor:{principal.user_id}", settings.rate_limit_ai_per_minute
    )
    svc = AITutorService(session)
    return await svc.send_message(
        principal=principal, conversation_id=conversation_id, req=req
    )


@router.get(
    "/tutor/conversations/{conversation_id}",
    response_model=TutorConversationResponse,
)
async def get_tutor_conversation(
    conversation_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TutorConversationResponse:
    svc = AITutorService(session)
    return await svc.get_conversation(principal, conversation_id)


@router.get(
    "/tutor/conversations/{conversation_id}/messages",
    response_model=list[TutorMessageResponse],
)
async def list_tutor_messages(
    conversation_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[TutorMessageResponse]:
    svc = AITutorService(session)
    return await svc.list_messages(principal, conversation_id)


@router.post(
    "/courses/{course_id}/practice-generation-jobs",
    response_model=AIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_practice_generation_job(
    course_id: UUID,
    req: CreatePracticeJobRequest,
    process_async: bool = Query(default=False),
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIJobResponse:
    settings = get_settings()
    rate_limiter.check(
        f"ai:practice:{principal.user_id}", settings.rate_limit_ai_per_minute
    )
    svc = AITutorService(session)
    return await svc.create_practice_generation_job(
        principal=principal,
        course_id=course_id,
        req=req,
        execute_immediately=not process_async,
    )


@router.get("/ai/jobs/{job_id}", response_model=AIJobResponse)
async def get_ai_job(
    job_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIJobResponse:
    svc = AITutorService(session)
    return await svc.get_ai_job(principal, job_id)


@router.post("/ai/jobs/{job_id}/cancel", response_model=AIJobResponse)
async def cancel_ai_job(
    job_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIJobResponse:
    svc = AITutorService(session)
    return await svc.cancel_ai_job(principal, job_id)


@router.get(
    "/courses/{course_id}/practice-drafts",
    response_model=list[PracticeDraftReviewResponse],
)
async def list_course_practice_drafts(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[PracticeDraftReviewResponse]:
    svc = AITutorService(session)
    return await svc.list_practice_drafts(principal, course_id)


@router.post(
    "/practice-drafts/{review_id}/decision",
    response_model=PracticeDraftReviewResponse,
)
async def review_practice_draft(
    review_id: UUID,
    req: ReviewPracticeDraftRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> PracticeDraftReviewResponse:
    svc = AITutorService(session)
    return await svc.review_practice_draft(
        principal=principal, review_id=review_id, req=req
    )
