from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import PrincipalContext, TenantRole
from app.modules.assessments.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentItem,
    AssessmentItemObjective,
    AssessmentVersion,
    AttemptResponse,
    GradingResult,
    GradingReview,
    Question,
)
from app.modules.assessments.schemas import (
    AssessmentResponse,
    AttemptDetailResponse,
    AttemptResponseView,
    CreateAssessmentRequest,
    GradingResultResponse,
    GradingReviewRequest,
    GradingReviewView,
    QuestionViewResponse,
    SaveAttemptResponseRequest,
)
from app.modules.audit.service import AuditService
from app.modules.courses.models import Course, LearningObjective
from app.modules.enrollments.models import Enrollment, LearningEvent, ProgressSnapshot
from app.modules.learning_intelligence.service import LearningIntelligenceService
from app.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationAppError,
)


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)
        self.intelligence = LearningIntelligenceService(session)

    async def _load_assessment_questions(
        self,
        tenant_id: UUID,
        assessment_id: UUID,
        include_answers: bool,
    ) -> list[QuestionViewResponse]:
        stmt = (
            select(AssessmentItem, Question)
            .join(
                Question,
                (Question.id == AssessmentItem.question_id)
                & (Question.tenant_id == AssessmentItem.tenant_id),
            )
            .where(
                AssessmentItem.tenant_id == tenant_id,
                AssessmentItem.assessment_id == assessment_id,
            )
            .order_by(AssessmentItem.position.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        views: list[QuestionViewResponse] = []
        for item, q in rows:
            obj_ids = list(
                (
                    await self.session.execute(
                        select(AssessmentItemObjective.objective_id).where(
                            AssessmentItemObjective.tenant_id == tenant_id,
                            AssessmentItemObjective.question_id == q.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            pts = item.points_override if item.points_override is not None else q.points
            views.append(
                QuestionViewResponse(
                    id=q.id,
                    question_type=q.question_type,
                    prompt=q.prompt,
                    options=q.options,
                    points=pts,
                    difficulty=q.difficulty,
                    objective_ids=obj_ids,
                    correct_answer=q.correct_answer if include_answers else None,
                    explanation=q.explanation if include_answers else None,
                )
            )
        return views

    async def create_assessment(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: CreateAssessmentRequest,
    ) -> AssessmentResponse:
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

        asmt = Assessment(
            tenant_id=tenant_id,
            course_id=course.id,
            title=req.title.strip(),
            description=req.description,
            assessment_type=req.assessment_type,
            passing_score_percentage=req.passing_score_percentage,
            time_limit_minutes=req.time_limit_minutes,
            max_attempts=req.max_attempts,
            status="draft",
            current_version_number=0,
        )
        self.session.add(asmt)
        await self.session.flush()

        pos = 1
        for q_in in req.questions:
            q = Question(
                tenant_id=tenant_id,
                course_id=course.id,
                question_type=q_in.question_type,
                prompt=q_in.prompt.strip(),
                options=[opt.model_dump() for opt in q_in.options],
                correct_answer=q_in.correct_answer.strip(),
                explanation=q_in.explanation,
                points=q_in.points,
                difficulty=q_in.difficulty,
                source_type="instructor",
                status="approved",
            )
            self.session.add(q)
            await self.session.flush()

            for oid in q_in.objective_ids:
                self.session.add(
                    AssessmentItemObjective(
                        tenant_id=tenant_id,
                        question_id=q.id,
                        objective_id=oid,
                    )
                )

            self.session.add(
                AssessmentItem(
                    tenant_id=tenant_id,
                    assessment_id=asmt.id,
                    question_id=q.id,
                    position=pos,
                    points_override=q_in.points,
                )
            )
            pos += 1

        for existing_qid in req.existing_question_ids:
            q_existing = (
                await self.session.execute(
                    select(Question).where(
                        Question.tenant_id == tenant_id,
                        Question.id == existing_qid,
                        Question.course_id == course.id,
                    )
                )
            ).scalar_one_or_none()
            if q_existing is None:
                raise NotFoundError(f"Question {existing_qid} not found in course.")
            if q_existing.status != "approved":
                raise ValidationAppError(
                    "Unapproved AI-generated draft questions cannot be attached to an assessment before instructor approval."
                )
            self.session.add(
                AssessmentItem(
                    tenant_id=tenant_id,
                    assessment_id=asmt.id,
                    question_id=q_existing.id,
                    position=pos,
                    points_override=q_existing.points,
                )
            )
            pos += 1

        await self.session.flush()
        questions = await self._load_assessment_questions(
            tenant_id, asmt.id, include_answers=True
        )
        return AssessmentResponse(
            id=asmt.id,
            tenant_id=asmt.tenant_id,
            course_id=asmt.course_id,
            title=asmt.title,
            description=asmt.description,
            assessment_type=asmt.assessment_type,
            passing_score_percentage=asmt.passing_score_percentage,
            time_limit_minutes=asmt.time_limit_minutes,
            max_attempts=asmt.max_attempts,
            status=asmt.status,
            current_version_number=asmt.current_version_number,
            published_version_id=asmt.published_version_id,
            questions=questions,
            created_at=asmt.created_at,
        )

    async def list_course_assessments(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[AssessmentResponse]:
        tenant_id = principal.require_tenant()
        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        stmt = select(Assessment).where(
            Assessment.tenant_id == tenant_id, Assessment.course_id == course_id
        )
        if not is_staff:
            stmt = stmt.where(Assessment.status == "published")
        stmt = stmt.order_by(Assessment.created_at.asc())
        items = list((await self.session.execute(stmt)).scalars().all())
        results: list[AssessmentResponse] = []
        for asmt in items:
            qs = await self._load_assessment_questions(
                tenant_id, asmt.id, include_answers=is_staff
            )
            results.append(
                AssessmentResponse(
                    id=asmt.id,
                    tenant_id=asmt.tenant_id,
                    course_id=asmt.course_id,
                    title=asmt.title,
                    description=asmt.description,
                    assessment_type=asmt.assessment_type,
                    passing_score_percentage=asmt.passing_score_percentage,
                    time_limit_minutes=asmt.time_limit_minutes,
                    max_attempts=asmt.max_attempts,
                    status=asmt.status,
                    current_version_number=asmt.current_version_number,
                    published_version_id=asmt.published_version_id,
                    questions=qs,
                    created_at=asmt.created_at,
                )
            )
        return results

    async def publish_assessment(
        self,
        *,
        principal: PrincipalContext,
        assessment_id: UUID,
    ) -> AssessmentResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )

        asmt = (
            await self.session.execute(
                select(Assessment).where(
                    Assessment.tenant_id == tenant_id, Assessment.id == assessment_id
                )
            )
        ).scalar_one_or_none()
        if asmt is None:
            raise NotFoundError("Assessment not found.")

        questions = await self._load_assessment_questions(
            tenant_id, asmt.id, include_answers=True
        )
        if not questions:
            raise ValidationAppError(
                "Cannot publish an assessment without at least one question."
            )

        total_points = round(sum(q.points for q in questions), 2)
        next_ver = asmt.current_version_number + 1
        snapshot = [q.model_dump(mode="json") for q in questions]

        version = AssessmentVersion(
            tenant_id=tenant_id,
            assessment_id=asmt.id,
            version_number=next_ver,
            passing_score_percentage=asmt.passing_score_percentage,
            total_points=total_points,
            questions_snapshot=snapshot,
            published_at=datetime.now(UTC),
        )
        self.session.add(version)
        await self.session.flush()

        asmt.status = "published"
        asmt.current_version_number = next_ver
        asmt.published_version_id = version.id

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="assessment.published",
            resource_type="assessment_version",
            resource_id=str(version.id),
            metadata_json={"assessment_id": str(asmt.id), "version_number": next_ver},
        )
        await self.session.flush()

        return AssessmentResponse(
            id=asmt.id,
            tenant_id=asmt.tenant_id,
            course_id=asmt.course_id,
            title=asmt.title,
            description=asmt.description,
            assessment_type=asmt.assessment_type,
            passing_score_percentage=asmt.passing_score_percentage,
            time_limit_minutes=asmt.time_limit_minutes,
            max_attempts=asmt.max_attempts,
            status=asmt.status,
            current_version_number=asmt.current_version_number,
            published_version_id=asmt.published_version_id,
            questions=questions,
            created_at=asmt.created_at,
        )

    async def get_assessment(
        self, principal: PrincipalContext, assessment_id: UUID
    ) -> AssessmentResponse:
        tenant_id = principal.require_tenant()
        asmt = (
            await self.session.execute(
                select(Assessment).where(
                    Assessment.tenant_id == tenant_id, Assessment.id == assessment_id
                )
            )
        ).scalar_one_or_none()
        if asmt is None:
            raise NotFoundError("Assessment not found.")

        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        if not is_staff and asmt.status != "published":
            raise AuthorizationError("Draft assessments are not accessible to learners.")

        if asmt.published_version_id and not is_staff:
            # Return questions from immutable published version without answer keys
            ver = (
                await self.session.execute(
                    select(AssessmentVersion).where(
                        AssessmentVersion.tenant_id == tenant_id,
                        AssessmentVersion.id == asmt.published_version_id,
                    )
                )
            ).scalar_one()
            questions = [
                QuestionViewResponse(
                    id=UUID(str(q["id"])),
                    question_type=q["question_type"],
                    prompt=q["prompt"],
                    options=q["options"],
                    points=float(q["points"]),
                    difficulty=q["difficulty"],
                    objective_ids=[UUID(str(oid)) for oid in q.get("objective_ids", [])],
                    correct_answer=None,
                    explanation=None,
                )
                for q in ver.questions_snapshot
            ]
        else:
            questions = await self._load_assessment_questions(
                tenant_id, asmt.id, include_answers=is_staff
            )

        return AssessmentResponse(
            id=asmt.id,
            tenant_id=asmt.tenant_id,
            course_id=asmt.course_id,
            title=asmt.title,
            description=asmt.description,
            assessment_type=asmt.assessment_type,
            passing_score_percentage=asmt.passing_score_percentage,
            time_limit_minutes=asmt.time_limit_minutes,
            max_attempts=asmt.max_attempts,
            status=asmt.status,
            current_version_number=asmt.current_version_number,
            published_version_id=asmt.published_version_id,
            questions=questions,
            created_at=asmt.created_at,
        )

    async def start_attempt(
        self,
        *,
        principal: PrincipalContext,
        assessment_id: UUID,
    ) -> AttemptDetailResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        asmt = (
            await self.session.execute(
                select(Assessment).where(
                    Assessment.tenant_id == tenant_id, Assessment.id == assessment_id
                )
            )
        ).scalar_one_or_none()
        if asmt is None:
            raise NotFoundError("Assessment not found.")
        if asmt.status != "published" or asmt.published_version_id is None:
            raise ValidationAppError("Assessment must be published before attempts can start.")

        enrollment = (
            await self.session.execute(
                select(Enrollment).where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.course_id == asmt.course_id,
                    Enrollment.membership_id == principal.membership_id,
                    Enrollment.status.in_(("active", "completed")),
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            raise AuthorizationError(
                "You must be enrolled in the course to start an assessment attempt."
            )

        existing_count = int(
            (
                await self.session.execute(
                    select(func.count(AssessmentAttempt.id)).where(
                        AssessmentAttempt.tenant_id == tenant_id,
                        AssessmentAttempt.assessment_id == asmt.id,
                        AssessmentAttempt.learner_membership_id == principal.membership_id,
                    )
                )
            ).scalar_one()
            or 0
        )
        if existing_count >= asmt.max_attempts:
            raise ConflictError(
                f"Maximum allowed attempts ({asmt.max_attempts}) reached for this assessment."
            )

        ver = (
            await self.session.execute(
                select(AssessmentVersion).where(
                    AssessmentVersion.tenant_id == tenant_id,
                    AssessmentVersion.id == asmt.published_version_id,
                )
            )
        ).scalar_one()

        attempt = AssessmentAttempt(
            tenant_id=tenant_id,
            assessment_id=asmt.id,
            assessment_version_id=ver.id,
            enrollment_id=enrollment.id,
            learner_membership_id=principal.membership_id,
            attempt_number=existing_count + 1,
            status="in_progress",
            started_at=datetime.now(UTC),
        )
        self.session.add(attempt)
        await self.session.flush()

        q_views = [
            QuestionViewResponse(
                id=UUID(str(q["id"])),
                question_type=q["question_type"],
                prompt=q["prompt"],
                options=q["options"],
                points=float(q["points"]),
                difficulty=q["difficulty"],
                objective_ids=[UUID(str(oid)) for oid in q.get("objective_ids", [])],
                correct_answer=None,
                explanation=None,
            )
            for q in ver.questions_snapshot
        ]
        return AttemptDetailResponse(
            id=attempt.id,
            tenant_id=attempt.tenant_id,
            assessment_id=attempt.assessment_id,
            assessment_version_id=attempt.assessment_version_id,
            enrollment_id=attempt.enrollment_id,
            learner_membership_id=attempt.learner_membership_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            questions=q_views,
            responses=[],
        )

    async def save_response(
        self,
        *,
        principal: PrincipalContext,
        attempt_id: UUID,
        question_id: UUID,
        req: SaveAttemptResponseRequest,
    ) -> AttemptResponseView:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        attempt = (
            await self.session.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.tenant_id == tenant_id,
                    AssessmentAttempt.id == attempt_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotFoundError("Assessment attempt not found.")
        if attempt.learner_membership_id != principal.membership_id:
            raise AuthorizationError("Cannot modify another learner's assessment attempt.")
        if attempt.status != "in_progress":
            raise ConflictError("Cannot modify responses on a submitted assessment attempt.")

        ver = (
            await self.session.execute(
                select(AssessmentVersion).where(
                    AssessmentVersion.tenant_id == tenant_id,
                    AssessmentVersion.id == attempt.assessment_version_id,
                )
            )
        ).scalar_one()

        valid_qids = {UUID(str(q["id"])) for q in ver.questions_snapshot}
        if question_id not in valid_qids:
            raise ValidationAppError("Question does not belong to this assessment version.")

        existing = (
            await self.session.execute(
                select(AttemptResponse).where(
                    AttemptResponse.tenant_id == tenant_id,
                    AttemptResponse.attempt_id == attempt.id,
                    AttemptResponse.question_id == question_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            existing = AttemptResponse(
                tenant_id=tenant_id,
                attempt_id=attempt.id,
                question_id=question_id,
                selected_answer=req.selected_answer.strip(),
            )
            self.session.add(existing)
        else:
            existing.selected_answer = req.selected_answer.strip()

        await self.session.flush()
        return AttemptResponseView(
            question_id=existing.question_id,
            selected_answer=existing.selected_answer,
            is_correct=existing.is_correct,
            awarded_points=existing.awarded_points,
        )

    async def submit_attempt(
        self,
        *,
        principal: PrincipalContext,
        attempt_id: UUID,
    ) -> GradingResultResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        attempt = (
            await self.session.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.tenant_id == tenant_id,
                    AssessmentAttempt.id == attempt_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotFoundError("Assessment attempt not found.")
        if attempt.learner_membership_id != principal.membership_id:
            raise AuthorizationError("Cannot submit another learner's assessment attempt.")

        # Idempotent submission: if already graded, return existing authoritative result
        if attempt.status == "graded":
            return await self.get_attempt_results(principal=principal, attempt_id=attempt.id)

        ver = (
            await self.session.execute(
                select(AssessmentVersion).where(
                    AssessmentVersion.tenant_id == tenant_id,
                    AssessmentVersion.id == attempt.assessment_version_id,
                )
            )
        ).scalar_one()
        asmt = (
            await self.session.execute(
                select(Assessment).where(
                    Assessment.tenant_id == tenant_id,
                    Assessment.id == attempt.assessment_id,
                )
            )
        ).scalar_one()

        saved_responses = list(
            (
                await self.session.execute(
                    select(AttemptResponse).where(
                        AttemptResponse.tenant_id == tenant_id,
                        AttemptResponse.attempt_id == attempt.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        resp_by_qid = {r.question_id: r for r in saved_responses}

        earned_points = 0.0
        total_points = 0.0
        obj_stats: dict[str, dict[str, Any]] = {}

        for q_snap in ver.questions_snapshot:
            qid = UUID(str(q_snap["id"]))
            q_pts = float(q_snap["points"])
            correct_ans = str(q_snap["correct_answer"]).strip().lower()
            total_points += q_pts

            resp = resp_by_qid.get(qid)
            is_correct = False
            awarded = 0.0
            if resp is not None:
                is_correct = resp.selected_answer.strip().lower() == correct_ans
                awarded = q_pts if is_correct else 0.0
                resp.is_correct = is_correct
                resp.awarded_points = awarded
            earned_points += awarded

            for oid_raw in q_snap.get("objective_ids", []):
                oid_str = str(oid_raw)
                if oid_str not in obj_stats:
                    obj_stats[oid_str] = {
                        "objective_id": oid_str,
                        "earned_points": 0.0,
                        "total_points": 0.0,
                        "question_ids": [],
                    }
                obj_stats[oid_str]["earned_points"] += awarded
                obj_stats[oid_str]["total_points"] += q_pts
                obj_stats[oid_str]["question_ids"].append(str(qid))

        score_pct = (
            round((earned_points / total_points) * 100.0, 2) if total_points > 0 else 0.0
        )
        passed = score_pct >= ver.passing_score_percentage

        objective_breakdown: list[dict[str, Any]] = []
        for oid_str, st in obj_stats.items():
            o_tot = st["total_points"]
            o_pct = round((st["earned_points"] / o_tot) * 100.0, 2) if o_tot > 0 else 0.0
            obj_rec = (
                await self.session.execute(
                    select(LearningObjective).where(
                        LearningObjective.tenant_id == tenant_id,
                        LearningObjective.id == UUID(oid_str),
                    )
                )
            ).scalar_one_or_none()
            objective_breakdown.append(
                {
                    "objective_id": oid_str,
                    "objective_code": obj_rec.code if obj_rec else "",
                    "objective_title": obj_rec.title if obj_rec else "",
                    "earned_points": st["earned_points"],
                    "total_points": o_tot,
                    "score_percentage": o_pct,
                    "question_ids": st["question_ids"],
                }
            )

        now = datetime.now(UTC)
        attempt.status = "graded"
        attempt.submitted_at = now

        grading = GradingResult(
            tenant_id=tenant_id,
            attempt_id=attempt.id,
            earned_points=round(earned_points, 2),
            total_points=round(total_points, 2),
            score_percentage=score_pct,
            passed=passed,
            grading_method="deterministic_v1",
            objective_breakdown=objective_breakdown,
            graded_at=now,
        )
        self.session.add(grading)
        await self.session.flush()

        # Record LearningEvent and update ProgressSnapshot
        self.session.add(
            LearningEvent(
                tenant_id=tenant_id,
                enrollment_id=attempt.enrollment_id,
                event_type="assessment_submitted",
                duration_seconds=0,
                event_metadata={
                    "assessment_id": str(asmt.id),
                    "attempt_id": str(attempt.id),
                    "score_percentage": score_pct,
                    "passed": passed,
                },
            )
        )
        snap = (
            await self.session.execute(
                select(ProgressSnapshot).where(
                    ProgressSnapshot.tenant_id == tenant_id,
                    ProgressSnapshot.enrollment_id == attempt.enrollment_id,
                )
            )
        ).scalar_one_or_none()
        if snap is not None:
            snap.latest_assessment_score = score_pct
            await self.session.flush()

        # Trigger explainable Learning Intelligence mastery & gap evaluation
        await self.intelligence.evaluate_and_update_mastery(
            tenant_id=tenant_id,
            course_id=asmt.course_id,
            enrollment_id=attempt.enrollment_id,
            learner_membership_id=attempt.learner_membership_id,
            attempt_id=attempt.id,
            grading_result_id=grading.id,
            objective_breakdown=objective_breakdown,
        )

        return await self.get_attempt_results(principal=principal, attempt_id=attempt.id)

    async def get_attempt_results(
        self,
        *,
        principal: PrincipalContext,
        attempt_id: UUID,
    ) -> GradingResultResponse:
        tenant_id = principal.require_tenant()
        attempt = (
            await self.session.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.tenant_id == tenant_id,
                    AssessmentAttempt.id == attempt_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise NotFoundError("Assessment attempt not found.")

        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        if not is_staff and attempt.learner_membership_id != principal.membership_id:
            raise AuthorizationError("Cannot view another learner's assessment results.")

        grading = (
            await self.session.execute(
                select(GradingResult).where(
                    GradingResult.tenant_id == tenant_id,
                    GradingResult.attempt_id == attempt.id,
                )
            )
        ).scalar_one_or_none()
        if grading is None:
            raise ValidationAppError("Attempt has not been submitted and graded yet.")

        resps = list(
            (
                await self.session.execute(
                    select(AttemptResponse).where(
                        AttemptResponse.tenant_id == tenant_id,
                        AttemptResponse.attempt_id == attempt.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        revs = list(
            (
                await self.session.execute(
                    select(GradingReview)
                    .where(
                        GradingReview.tenant_id == tenant_id,
                        GradingReview.grading_result_id == grading.id,
                    )
                    .order_by(GradingReview.reviewed_at.asc())
                )
            )
            .scalars()
            .all()
        )

        return GradingResultResponse(
            id=grading.id,
            tenant_id=grading.tenant_id,
            attempt_id=grading.attempt_id,
            assessment_id=attempt.assessment_id,
            assessment_version_id=attempt.assessment_version_id,
            earned_points=grading.earned_points,
            total_points=grading.total_points,
            score_percentage=grading.score_percentage,
            passed=grading.passed,
            grading_method=grading.grading_method,
            objective_breakdown=grading.objective_breakdown,
            responses=[
                AttemptResponseView(
                    question_id=r.question_id,
                    selected_answer=r.selected_answer,
                    is_correct=r.is_correct,
                    awarded_points=r.awarded_points,
                )
                for r in resps
            ],
            reviews=[
                GradingReviewView(
                    id=rv.id,
                    reviewer_membership_id=rv.reviewer_membership_id,
                    previous_score_percentage=rv.previous_score_percentage,
                    adjusted_score_percentage=rv.adjusted_score_percentage,
                    feedback=rv.feedback,
                    reviewed_at=rv.reviewed_at,
                )
                for rv in revs
            ],
            graded_at=grading.graded_at,
        )

    async def review_grading_result(
        self,
        *,
        principal: PrincipalContext,
        result_id: UUID,
        req: GradingReviewRequest,
    ) -> GradingResultResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        assert principal.membership_id is not None

        grading = (
            await self.session.execute(
                select(GradingResult).where(
                    GradingResult.tenant_id == tenant_id,
                    GradingResult.id == result_id,
                )
            )
        ).scalar_one_or_none()
        if grading is None:
            raise NotFoundError("Grading result not found.")

        attempt = (
            await self.session.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.tenant_id == tenant_id,
                    AssessmentAttempt.id == grading.attempt_id,
                )
            )
        ).scalar_one()
        ver = (
            await self.session.execute(
                select(AssessmentVersion).where(
                    AssessmentVersion.tenant_id == tenant_id,
                    AssessmentVersion.id == attempt.assessment_version_id,
                )
            )
        ).scalar_one()

        prev_score = grading.score_percentage
        grading.score_percentage = round(req.adjusted_score_percentage, 2)
        grading.passed = grading.score_percentage >= ver.passing_score_percentage
        grading.grading_method = "instructor_reviewed"

        review = GradingReview(
            tenant_id=tenant_id,
            grading_result_id=grading.id,
            reviewer_membership_id=principal.membership_id,
            previous_score_percentage=prev_score,
            adjusted_score_percentage=grading.score_percentage,
            feedback=req.feedback.strip(),
            reviewed_at=datetime.now(UTC),
        )
        self.session.add(review)

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="grading.reviewed",
            resource_type="grading_result",
            resource_id=str(grading.id),
            metadata_json={
                "previous_score_percentage": prev_score,
                "adjusted_score_percentage": grading.score_percentage,
            },
        )
        await self.session.flush()
        return await self.get_attempt_results(principal=principal, attempt_id=attempt.id)
