from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import PrincipalContext, TenantRole
from app.modules.audit.service import AuditService
from app.modules.courses.models import (
    Course,
    CourseInstructorAssignment,
    CourseVersion,
    LearningObjective,
    Lesson,
    LessonObjective,
)
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
from app.modules.enrollments.models import Enrollment, LearningEvent, ProgressSnapshot
from app.modules.subscriptions.service import SubscriptionService
from app.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationAppError,
)


class CourseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)
        self.subscriptions = SubscriptionService(session)

    async def _build_course_response(self, course: Course) -> CourseResponse:
        objs = list(
            (
                await self.session.execute(
                    select(LearningObjective)
                    .where(
                        LearningObjective.tenant_id == course.tenant_id,
                        LearningObjective.course_id == course.id,
                    )
                    .order_by(LearningObjective.code.asc())
                )
            )
            .scalars()
            .all()
        )
        lessons_count = int(
            (
                await self.session.execute(
                    select(func.count(Lesson.id)).where(
                        Lesson.tenant_id == course.tenant_id,
                        Lesson.course_id == course.id,
                    )
                )
            ).scalar_one()
            or 0
        )
        return CourseResponse(
            id=course.id,
            tenant_id=course.tenant_id,
            code=course.code,
            title=course.title,
            description=course.description,
            status=course.status,
            current_version_number=course.current_version_number,
            published_version_id=course.published_version_id,
            academic_integrity_policy=course.academic_integrity_policy,
            created_by_membership_id=course.created_by_membership_id,
            objectives=[
                ObjectiveResponse(
                    id=o.id,
                    tenant_id=o.tenant_id,
                    course_id=o.course_id,
                    code=o.code,
                    title=o.title,
                    description=o.description,
                    mastery_threshold=o.mastery_threshold,
                    created_at=o.created_at,
                )
                for o in objs
            ],
            lessons_count=lessons_count,
            created_at=course.created_at,
            updated_at=course.updated_at,
        )

    async def create_course(
        self,
        *,
        principal: PrincipalContext,
        req: CreateCourseRequest,
    ) -> CourseResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        assert principal.membership_id is not None

        code = req.code.strip().upper()
        existing = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.code == code)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Course with code '{code}' already exists in this tenant.")

        course = Course(
            tenant_id=tenant_id,
            code=code,
            title=req.title.strip(),
            description=req.description,
            status="draft",
            current_version_number=0,
            academic_integrity_policy=req.academic_integrity_policy,
            created_by_membership_id=principal.membership_id,
        )
        self.session.add(course)
        await self.session.flush()

        self.session.add(
            CourseInstructorAssignment(
                tenant_id=tenant_id,
                course_id=course.id,
                membership_id=principal.membership_id,
                role_in_course="lead",
            )
        )
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="course.created",
            resource_type="course",
            resource_id=str(course.id),
            metadata_json={"code": course.code, "title": course.title},
        )
        await self.session.flush()
        return await self._build_course_response(course)

    async def list_courses(self, principal: PrincipalContext) -> list[CourseResponse]:
        tenant_id = principal.require_tenant()
        stmt = select(Course).where(Course.tenant_id == tenant_id)
        if not principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        ):
            stmt = stmt.where(Course.status == "published")
        stmt = stmt.order_by(Course.created_at.desc())
        courses = list((await self.session.execute(stmt)).scalars().all())
        return [await self._build_course_response(c) for c in courses]

    async def get_course(
        self, principal: PrincipalContext, course_id: UUID
    ) -> CourseResponse:
        tenant_id = principal.require_tenant()
        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")
        if course.status != "published" and not principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        ):
            raise AuthorizationError("Draft courses are not visible to learners.")
        return await self._build_course_response(course)

    async def update_course(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: UpdateCourseRequest,
    ) -> CourseResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")

        if req.title is not None:
            course.title = req.title.strip()
        if req.description is not None:
            course.description = req.description
        if req.academic_integrity_policy is not None:
            course.academic_integrity_policy = req.academic_integrity_policy

        await self.session.flush()
        return await self._build_course_response(course)

    async def create_objective(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: CreateObjectiveRequest,
    ) -> ObjectiveResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")

        obj = LearningObjective(
            tenant_id=tenant_id,
            course_id=course.id,
            code=req.code.strip().upper(),
            title=req.title.strip(),
            description=req.description,
            mastery_threshold=req.mastery_threshold,
        )
        self.session.add(obj)
        await self.session.flush()
        return ObjectiveResponse(
            id=obj.id,
            tenant_id=obj.tenant_id,
            course_id=obj.course_id,
            code=obj.code,
            title=obj.title,
            description=obj.description,
            mastery_threshold=obj.mastery_threshold,
            created_at=obj.created_at,
        )

    async def list_objectives(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[ObjectiveResponse]:
        tenant_id = principal.require_tenant()
        objs = list(
            (
                await self.session.execute(
                    select(LearningObjective)
                    .where(
                        LearningObjective.tenant_id == tenant_id,
                        LearningObjective.course_id == course_id,
                    )
                    .order_by(LearningObjective.code.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            ObjectiveResponse(
                id=o.id,
                tenant_id=o.tenant_id,
                course_id=o.course_id,
                code=o.code,
                title=o.title,
                description=o.description,
                mastery_threshold=o.mastery_threshold,
                created_at=o.created_at,
            )
            for o in objs
        ]

    async def create_lesson(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: CreateLessonRequest,
    ) -> LessonResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")

        lesson = Lesson(
            tenant_id=tenant_id,
            course_id=course.id,
            title=req.title.strip(),
            content_markdown=req.content_markdown,
            position=req.position,
            estimated_minutes=req.estimated_minutes,
        )
        self.session.add(lesson)
        await self.session.flush()

        for oid in req.objective_ids:
            self.session.add(
                LessonObjective(
                    tenant_id=tenant_id,
                    lesson_id=lesson.id,
                    objective_id=oid,
                )
            )
        await self.session.flush()

        return LessonResponse(
            id=lesson.id,
            tenant_id=lesson.tenant_id,
            course_id=lesson.course_id,
            title=lesson.title,
            content_markdown=lesson.content_markdown,
            position=lesson.position,
            estimated_minutes=lesson.estimated_minutes,
            objective_ids=req.objective_ids,
            created_at=lesson.created_at,
        )

    async def update_lesson(
        self,
        *,
        principal: PrincipalContext,
        lesson_id: UUID,
        req: UpdateLessonRequest,
    ) -> LessonResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        lesson = (
            await self.session.execute(
                select(Lesson).where(Lesson.tenant_id == tenant_id, Lesson.id == lesson_id)
            )
        ).scalar_one_or_none()
        if lesson is None:
            raise NotFoundError("Lesson not found.")

        if req.title is not None:
            lesson.title = req.title.strip()
        if req.content_markdown is not None:
            lesson.content_markdown = req.content_markdown
        if req.position is not None:
            lesson.position = req.position
        if req.estimated_minutes is not None:
            lesson.estimated_minutes = req.estimated_minutes

        if req.objective_ids is not None:
            old_links = (
                await self.session.execute(
                    select(LessonObjective).where(
                        LessonObjective.tenant_id == tenant_id,
                        LessonObjective.lesson_id == lesson.id,
                    )
                )
            ).scalars().all()
            for lnk in old_links:
                await self.session.delete(lnk)
            await self.session.flush()
            for oid in req.objective_ids:
                self.session.add(
                    LessonObjective(
                        tenant_id=tenant_id,
                        lesson_id=lesson.id,
                        objective_id=oid,
                    )
                )
        await self.session.flush()

        obj_ids = list(
            (
                await self.session.execute(
                    select(LessonObjective.objective_id).where(
                        LessonObjective.tenant_id == tenant_id,
                        LessonObjective.lesson_id == lesson.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return LessonResponse(
            id=lesson.id,
            tenant_id=lesson.tenant_id,
            course_id=lesson.course_id,
            title=lesson.title,
            content_markdown=lesson.content_markdown,
            position=lesson.position,
            estimated_minutes=lesson.estimated_minutes,
            objective_ids=obj_ids,
            created_at=lesson.created_at,
        )

    async def list_lessons(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[LessonResponse]:
        tenant_id = principal.require_tenant()
        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")

        if not principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        ):
            # Verify learner is enrolled in this course
            enr = (
                await self.session.execute(
                    select(Enrollment).where(
                        Enrollment.tenant_id == tenant_id,
                        Enrollment.course_id == course_id,
                        Enrollment.membership_id == principal.membership_id,
                        Enrollment.status.in_(("active", "completed")),
                    )
                )
            ).scalar_one_or_none()
            if enr is None:
                raise AuthorizationError(
                    "Learners must be enrolled in a course before viewing its lessons."
                )

        lessons = list(
            (
                await self.session.execute(
                    select(Lesson)
                    .where(Lesson.tenant_id == tenant_id, Lesson.course_id == course_id)
                    .order_by(Lesson.position.asc(), Lesson.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        results: list[LessonResponse] = []
        for lsn in lessons:
            obj_ids = list(
                (
                    await self.session.execute(
                        select(LessonObjective.objective_id).where(
                            LessonObjective.tenant_id == tenant_id,
                            LessonObjective.lesson_id == lsn.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            results.append(
                LessonResponse(
                    id=lsn.id,
                    tenant_id=lsn.tenant_id,
                    course_id=lsn.course_id,
                    title=lsn.title,
                    content_markdown=lsn.content_markdown,
                    position=lsn.position,
                    estimated_minutes=lsn.estimated_minutes,
                    objective_ids=obj_ids,
                    created_at=lsn.created_at,
                )
            )
        return results

    async def publish_course(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
    ) -> CourseVersionResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        assert principal.membership_id is not None

        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")

        if course.status != "published":
            await self.subscriptions.check_and_increment_course_publish_quota(tenant_id)

        lessons = await self.list_lessons(principal, course_id)
        objectives = await self.list_objectives(principal, course_id)

        next_version = course.current_version_number + 1
        snapshot = {
            "course_code": course.code,
            "title": course.title,
            "description": course.description,
            "academic_integrity_policy": course.academic_integrity_policy,
            "objectives": [o.model_dump(mode="json") for o in objectives],
            "lessons": [lesson_item.model_dump(mode="json") for lesson_item in lessons],
        }
        now = datetime.now(UTC)
        version = CourseVersion(
            tenant_id=tenant_id,
            course_id=course.id,
            version_number=next_version,
            title=course.title,
            description=course.description,
            snapshot_payload=snapshot,
            published_by_membership_id=principal.membership_id,
            published_at=now,
        )
        self.session.add(version)
        await self.session.flush()

        course.status = "published"
        course.current_version_number = next_version
        course.published_version_id = version.id

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="course.published",
            resource_type="course_version",
            resource_id=str(version.id),
            metadata_json={"course_id": str(course.id), "version_number": next_version},
        )
        await self.session.flush()
        return CourseVersionResponse(
            id=version.id,
            tenant_id=version.tenant_id,
            course_id=version.course_id,
            version_number=version.version_number,
            title=version.title,
            description=version.description,
            snapshot_payload=version.snapshot_payload,
            published_by_membership_id=version.published_by_membership_id,
            published_at=version.published_at,
        )

    async def list_course_versions(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[CourseVersionResponse]:
        tenant_id = principal.require_tenant()
        versions = list(
            (
                await self.session.execute(
                    select(CourseVersion)
                    .where(
                        CourseVersion.tenant_id == tenant_id,
                        CourseVersion.course_id == course_id,
                    )
                    .order_by(CourseVersion.version_number.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            CourseVersionResponse(
                id=v.id,
                tenant_id=v.tenant_id,
                course_id=v.course_id,
                version_number=v.version_number,
                title=v.title,
                description=v.description,
                snapshot_payload=v.snapshot_payload,
                published_by_membership_id=v.published_by_membership_id,
                published_at=v.published_at,
            )
            for v in versions
        ]

    async def enroll_learner(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: EnrollRequest | None = None,
    ) -> EnrollmentResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        target_membership_id = (
            req.membership_id if (req and req.membership_id) else principal.membership_id
        )
        if target_membership_id != principal.membership_id:
            principal.require_any_role(
                TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
            )

        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")
        if course.status != "published" or course.published_version_id is None:
            raise ValidationAppError("Cannot enroll in a course that has not been published.")

        existing = (
            await self.session.execute(
                select(Enrollment).where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.course_id == course.id,
                    Enrollment.membership_id == target_membership_id,
                )
            )
        ).scalar_one_or_none()

        total_lessons = int(
            (
                await self.session.execute(
                    select(func.count(Lesson.id)).where(
                        Lesson.tenant_id == tenant_id,
                        Lesson.course_id == course.id,
                    )
                )
            ).scalar_one()
            or 0
        )
        total_objs = int(
            (
                await self.session.execute(
                    select(func.count(LearningObjective.id)).where(
                        LearningObjective.tenant_id == tenant_id,
                        LearningObjective.course_id == course.id,
                    )
                )
            ).scalar_one()
            or 0
        )

        snap: ProgressSnapshot | None
        if existing is None:
            existing = Enrollment(
                tenant_id=tenant_id,
                course_id=course.id,
                course_version_id=course.published_version_id,
                membership_id=target_membership_id,
                cohort_id=req.cohort_id if req else None,
                status="active",
            )
            self.session.add(existing)
            await self.session.flush()

            snap = ProgressSnapshot(
                tenant_id=tenant_id,
                enrollment_id=existing.id,
                lessons_completed_count=0,
                total_lessons_count=total_lessons,
                completion_percentage=0.0,
                mastered_objectives_count=0,
                total_objectives_count=total_objs,
            )
            self.session.add(snap)
            await self.session.flush()
        else:
            snap = (
                await self.session.execute(
                    select(ProgressSnapshot).where(
                        ProgressSnapshot.tenant_id == tenant_id,
                        ProgressSnapshot.enrollment_id == existing.id,
                    )
                )
            ).scalar_one_or_none()

        return EnrollmentResponse(
            id=existing.id,
            tenant_id=existing.tenant_id,
            course_id=existing.course_id,
            course_title=course.title,
            course_code=course.code,
            course_version_id=existing.course_version_id,
            membership_id=existing.membership_id,
            cohort_id=existing.cohort_id,
            status=existing.status,
            completion_percentage=snap.completion_percentage if snap else 0.0,
            lessons_completed_count=snap.lessons_completed_count if snap else 0,
            total_lessons_count=snap.total_lessons_count if snap else total_lessons,
            created_at=existing.created_at,
        )

    async def list_my_courses(self, principal: PrincipalContext) -> list[EnrollmentResponse]:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        stmt = (
            select(Enrollment, Course, ProgressSnapshot)
            .join(
                Course,
                (Course.id == Enrollment.course_id)
                & (Course.tenant_id == Enrollment.tenant_id),
            )
            .outerjoin(
                ProgressSnapshot,
                (ProgressSnapshot.enrollment_id == Enrollment.id)
                & (ProgressSnapshot.tenant_id == Enrollment.tenant_id),
            )
            .where(
                Enrollment.tenant_id == tenant_id,
                Enrollment.membership_id == principal.membership_id,
            )
            .order_by(Enrollment.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            EnrollmentResponse(
                id=enr.id,
                tenant_id=enr.tenant_id,
                course_id=enr.course_id,
                course_title=crs.title,
                course_code=crs.code,
                course_version_id=enr.course_version_id,
                membership_id=enr.membership_id,
                cohort_id=enr.cohort_id,
                status=enr.status,
                completion_percentage=snap.completion_percentage if snap else 0.0,
                lessons_completed_count=snap.lessons_completed_count if snap else 0,
                total_lessons_count=snap.total_lessons_count if snap else 0,
                created_at=enr.created_at,
            )
            for enr, crs, snap in rows
        ]

    async def complete_lesson(
        self,
        *,
        principal: PrincipalContext,
        lesson_id: UUID,
        duration_seconds: int = 300,
    ) -> EnrollmentResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        lesson = (
            await self.session.execute(
                select(Lesson).where(Lesson.tenant_id == tenant_id, Lesson.id == lesson_id)
            )
        ).scalar_one_or_none()
        if lesson is None:
            raise NotFoundError("Lesson not found.")

        enrollment = (
            await self.session.execute(
                select(Enrollment).where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.course_id == lesson.course_id,
                    Enrollment.membership_id == principal.membership_id,
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise AuthorizationError("Learner is not enrolled in this course.")

        event = LearningEvent(
            tenant_id=tenant_id,
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            event_type="lesson_completed",
            duration_seconds=max(0, duration_seconds),
            event_metadata={"lesson_title": lesson.title},
        )
        self.session.add(event)
        await self.session.flush()

        completed_distinct = int(
            (
                await self.session.execute(
                    select(func.count(func.distinct(LearningEvent.lesson_id))).where(
                        LearningEvent.tenant_id == tenant_id,
                        LearningEvent.enrollment_id == enrollment.id,
                        LearningEvent.event_type == "lesson_completed",
                    )
                )
            ).scalar_one()
            or 0
        )
        total_lessons = int(
            (
                await self.session.execute(
                    select(func.count(Lesson.id)).where(
                        Lesson.tenant_id == tenant_id,
                        Lesson.course_id == lesson.course_id,
                    )
                )
            ).scalar_one()
            or 0
        )
        pct = (
            round(min(100.0, (completed_distinct / total_lessons) * 100.0), 2)
            if total_lessons > 0
            else 100.0
        )

        snap = (
            await self.session.execute(
                select(ProgressSnapshot).where(
                    ProgressSnapshot.tenant_id == tenant_id,
                    ProgressSnapshot.enrollment_id == enrollment.id,
                )
            )
        ).scalar_one_or_none()
        if snap is None:
            snap = ProgressSnapshot(
                tenant_id=tenant_id,
                enrollment_id=enrollment.id,
                lessons_completed_count=completed_distinct,
                total_lessons_count=total_lessons,
                completion_percentage=pct,
            )
            self.session.add(snap)
        else:
            snap.lessons_completed_count = completed_distinct
            snap.total_lessons_count = total_lessons
            snap.completion_percentage = pct

        await self.session.flush()
        course = (
            await self.session.execute(
                select(Course).where(
                    Course.tenant_id == tenant_id, Course.id == lesson.course_id
                )
            )
        ).scalar_one()
        return EnrollmentResponse(
            id=enrollment.id,
            tenant_id=enrollment.tenant_id,
            course_id=enrollment.course_id,
            course_title=course.title,
            course_code=course.code,
            course_version_id=enrollment.course_version_id,
            membership_id=enrollment.membership_id,
            cohort_id=enrollment.cohort_id,
            status=enrollment.status,
            completion_percentage=snap.completion_percentage,
            lessons_completed_count=snap.lessons_completed_count,
            total_lessons_count=snap.total_lessons_count,
            created_at=enrollment.created_at,
        )
