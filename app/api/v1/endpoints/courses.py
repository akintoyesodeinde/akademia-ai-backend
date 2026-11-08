from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.db.session import get_db_session
from app.modules.courses.schemas import (
    CourseResponse,
    CourseVersionResponse,
    CreateCourseRequest,
    CreateLessonRequest,
    CreateObjectiveRequest,
    EnrollmentResponse,
    EnrollRequest,
    LessonResponse,
    ObjectiveResponse,
    UpdateCourseRequest,
    UpdateLessonRequest,
)
from app.modules.courses.service import CourseService

router = APIRouter(tags=["Courses & Enrollments"])


@router.get("/courses", response_model=list[CourseResponse])
async def list_courses(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[CourseResponse]:
    svc = CourseService(session)
    return await svc.list_courses(principal)


@router.post(
    "/courses",
    response_model=CourseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_course(
    req: CreateCourseRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CourseResponse:
    svc = CourseService(session)
    return await svc.create_course(principal=principal, req=req)


@router.get("/courses/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CourseResponse:
    svc = CourseService(session)
    return await svc.get_course(principal, course_id)


@router.patch("/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: UUID,
    req: UpdateCourseRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CourseResponse:
    svc = CourseService(session)
    return await svc.update_course(principal=principal, course_id=course_id, req=req)


@router.post("/courses/{course_id}/publish", response_model=CourseVersionResponse)
async def publish_course(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CourseVersionResponse:
    svc = CourseService(session)
    return await svc.publish_course(principal=principal, course_id=course_id)


@router.get("/courses/{course_id}/versions", response_model=list[CourseVersionResponse])
async def list_course_versions(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[CourseVersionResponse]:
    svc = CourseService(session)
    return await svc.list_course_versions(principal, course_id)


@router.get("/courses/{course_id}/objectives", response_model=list[ObjectiveResponse])
async def list_course_objectives(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[ObjectiveResponse]:
    svc = CourseService(session)
    return await svc.list_objectives(principal, course_id)


@router.post(
    "/courses/{course_id}/objectives",
    response_model=ObjectiveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_course_objective(
    course_id: UUID,
    req: CreateObjectiveRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ObjectiveResponse:
    svc = CourseService(session)
    return await svc.create_objective(
        principal=principal, course_id=course_id, req=req
    )


@router.get("/courses/{course_id}/lessons", response_model=list[LessonResponse])
async def list_course_lessons(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[LessonResponse]:
    svc = CourseService(session)
    return await svc.list_lessons(principal, course_id)


@router.post(
    "/courses/{course_id}/lessons",
    response_model=LessonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_course_lesson(
    course_id: UUID,
    req: CreateLessonRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> LessonResponse:
    svc = CourseService(session)
    return await svc.create_lesson(principal=principal, course_id=course_id, req=req)


@router.patch("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: UUID,
    req: UpdateLessonRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> LessonResponse:
    svc = CourseService(session)
    return await svc.update_lesson(principal=principal, lesson_id=lesson_id, req=req)


@router.post("/lessons/{lesson_id}/complete", response_model=EnrollmentResponse)
async def complete_lesson(
    lesson_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> EnrollmentResponse:
    svc = CourseService(session)
    return await svc.complete_lesson(principal=principal, lesson_id=lesson_id)


@router.post(
    "/courses/{course_id}/enrollments",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enroll_in_course(
    course_id: UUID,
    req: EnrollRequest | None = None,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> EnrollmentResponse:
    svc = CourseService(session)
    return await svc.enroll_learner(principal=principal, course_id=course_id, req=req)


@router.get("/learners/me/courses", response_model=list[EnrollmentResponse])
async def list_my_enrolled_courses(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[EnrollmentResponse]:
    svc = CourseService(session)
    return await svc.list_my_courses(principal)
