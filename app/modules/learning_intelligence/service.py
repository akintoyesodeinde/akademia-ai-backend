from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import PrincipalContext, TenantRole
from app.modules.assessments.models import Assessment, AssessmentAttempt, GradingResult
from app.modules.courses.models import Course, LearningObjective
from app.modules.enrollments.models import Enrollment, ProgressSnapshot
from app.modules.identity.models import User
from app.modules.learning_intelligence.models import (
    LearnerObjectiveMastery,
    Recommendation,
    RemediationPlan,
    RemediationPlanItem,
)
from app.modules.learning_intelligence.schemas import (
    CohortProgressResponse,
    CourseAnalyticsResponse,
    LearnerProgressSummaryResponse,
    ObjectiveMasteryResponse,
    RecommendationFeedbackRequest,
    RecommendationResponse,
)
from app.modules.memberships.models import TenantMembership
from app.modules.tenants.models import Cohort, CohortMembership
from app.shared.errors import NotFoundError


class LearningIntelligenceService:
    CALCULATION_VERSION = "rule-engine-v1"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def evaluate_and_update_mastery(
        self,
        *,
        tenant_id: UUID,
        course_id: UUID,
        enrollment_id: UUID,
        learner_membership_id: UUID,
        attempt_id: UUID,
        grading_result_id: UUID,
        objective_breakdown: list[dict[str, Any]],
    ) -> list[LearnerObjectiveMastery]:
        now = datetime.now(UTC)
        updated_records: list[LearnerObjectiveMastery] = []

        for item in objective_breakdown:
            obj_id = UUID(str(item["objective_id"]))
            observed_score = float(item["score_percentage"])
            question_ids = item.get("question_ids", [])

            obj = (
                await self.session.execute(
                    select(LearningObjective).where(
                        LearningObjective.tenant_id == tenant_id,
                        LearningObjective.id == obj_id,
                    )
                )
            ).scalar_one_or_none()
            if obj is None:
                continue

            mastery = (
                await self.session.execute(
                    select(LearnerObjectiveMastery).where(
                        LearnerObjectiveMastery.tenant_id == tenant_id,
                        LearnerObjectiveMastery.learner_membership_id == learner_membership_id,
                        LearnerObjectiveMastery.objective_id == obj.id,
                    )
                )
            ).scalar_one_or_none()

            evidence_entry = {
                "attempt_id": str(attempt_id),
                "grading_result_id": str(grading_result_id),
                "question_ids": [str(qid) for qid in question_ids],
                "observed_score_percentage": observed_score,
                "evaluated_at": now.isoformat(),
            }

            if mastery is None:
                prior_score = None
                new_score = round(observed_score, 2)
                score_delta = None
                attempts_count = 1
                incorrect_streak = 1 if observed_score < obj.mastery_threshold else 0
                evidence_list = [evidence_entry]
                mastery = LearnerObjectiveMastery(
                    tenant_id=tenant_id,
                    course_id=course_id,
                    learner_membership_id=learner_membership_id,
                    objective_id=obj.id,
                    mastery_score=new_score,
                    mastery_status="developing",
                    attempts_count=attempts_count,
                    incorrect_streak=incorrect_streak,
                    prior_score=prior_score,
                    score_delta=score_delta,
                    calculation_version=self.CALCULATION_VERSION,
                    evidence_refs=evidence_list,
                    last_evaluated_at=now,
                )
                self.session.add(mastery)
            else:
                prior_score = mastery.mastery_score
                # Recency-weighted deterministic mastery rule (65% latest, 35% prior)
                new_score = round(0.65 * observed_score + 0.35 * prior_score, 2)
                # If the learner achieved >= threshold on latest follow-up and improved, honor mastery
                if observed_score >= obj.mastery_threshold and new_score < obj.mastery_threshold:
                    new_score = round(observed_score, 2)
                score_delta = round(new_score - prior_score, 2)
                mastery.prior_score = prior_score
                mastery.mastery_score = new_score
                mastery.score_delta = score_delta
                mastery.attempts_count += 1
                if observed_score < obj.mastery_threshold:
                    mastery.incorrect_streak += 1
                else:
                    mastery.incorrect_streak = 0
                mastery.calculation_version = self.CALCULATION_VERSION
                mastery.evidence_refs = [*list(mastery.evidence_refs or []), evidence_entry]
                mastery.last_evaluated_at = now

            if mastery.mastery_score >= obj.mastery_threshold:
                mastery.mastery_status = "mastered"
                # Mark active recommendations for this objective as completed
                active_recs = (
                    await self.session.execute(
                        select(Recommendation).where(
                            Recommendation.tenant_id == tenant_id,
                            Recommendation.learner_membership_id == learner_membership_id,
                            Recommendation.objective_id == obj.id,
                            Recommendation.status == "active",
                        )
                    )
                ).scalars().all()
                for rec in active_recs:
                    rec.status = "completed"
            elif mastery.mastery_score < obj.mastery_threshold:
                mastery.mastery_status = "gap_detected"
                # Create or update traceable recommendation
                existing_rec = (
                    await self.session.execute(
                        select(Recommendation).where(
                            Recommendation.tenant_id == tenant_id,
                            Recommendation.learner_membership_id == learner_membership_id,
                            Recommendation.objective_id == obj.id,
                            Recommendation.status == "active",
                        )
                    )
                ).scalar_one_or_none()
                reason = (
                    f"Objective '{obj.code}: {obj.title}' scored {observed_score:.1f}% "
                    f"(current mastery {mastery.mastery_score:.1f}% vs. required {obj.mastery_threshold}% threshold) "
                    f"across {mastery.attempts_count} attempt(s). Targeted practice and lesson review recommended."
                )
                if existing_rec is None:
                    new_rec = Recommendation(
                        tenant_id=tenant_id,
                        course_id=course_id,
                        learner_membership_id=learner_membership_id,
                        objective_id=obj.id,
                        recommendation_type="targeted_practice",
                        title=f"Remediate {obj.code}: {obj.title}",
                        reason_explanation=reason,
                        calculation_version=self.CALCULATION_VERSION,
                        evidence_refs=[evidence_entry],
                        status="active",
                    )
                    self.session.add(new_rec)
                    await self.session.flush()

                    plan = RemediationPlan(
                        tenant_id=tenant_id,
                        course_id=course_id,
                        learner_membership_id=learner_membership_id,
                        title=f"Remediation Plan for {obj.code}",
                        status="active",
                    )
                    self.session.add(plan)
                    await self.session.flush()
                    self.session.add(
                        RemediationPlanItem(
                            tenant_id=tenant_id,
                            remediation_plan_id=plan.id,
                            recommendation_id=new_rec.id,
                            action_type="practice_and_follow_up",
                            status="pending",
                        )
                    )
                else:
                    existing_rec.reason_explanation = reason
                    existing_rec.evidence_refs = [
                        *list(existing_rec.evidence_refs or []),
                        evidence_entry,
                    ]

            updated_records.append(mastery)

        await self.session.flush()

        # Update ProgressSnapshot mastered_objectives_count
        mastered_count = int(
            (
                await self.session.execute(
                    select(func.count(LearnerObjectiveMastery.id)).where(
                        LearnerObjectiveMastery.tenant_id == tenant_id,
                        LearnerObjectiveMastery.course_id == course_id,
                        LearnerObjectiveMastery.learner_membership_id == learner_membership_id,
                        LearnerObjectiveMastery.mastery_status == "mastered",
                    )
                )
            ).scalar_one()
            or 0
        )
        snap = (
            await self.session.execute(
                select(ProgressSnapshot).where(
                    ProgressSnapshot.tenant_id == tenant_id,
                    ProgressSnapshot.enrollment_id == enrollment_id,
                )
            )
        ).scalar_one_or_none()
        if snap is not None:
            snap.mastered_objectives_count = mastered_count
            await self.session.flush()

        return updated_records

    async def get_my_mastery(
        self, principal: PrincipalContext, course_id: UUID | None = None
    ) -> list[ObjectiveMasteryResponse]:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        stmt = (
            select(LearnerObjectiveMastery, LearningObjective)
            .join(
                LearningObjective,
                (LearningObjective.id == LearnerObjectiveMastery.objective_id)
                & (LearningObjective.tenant_id == LearnerObjectiveMastery.tenant_id),
            )
            .where(
                LearnerObjectiveMastery.tenant_id == tenant_id,
                LearnerObjectiveMastery.learner_membership_id == principal.membership_id,
            )
        )
        if course_id is not None:
            stmt = stmt.where(LearnerObjectiveMastery.course_id == course_id)
        stmt = stmt.order_by(LearningObjective.code.asc())
        rows = (await self.session.execute(stmt)).all()
        return [
            ObjectiveMasteryResponse(
                id=m.id,
                tenant_id=m.tenant_id,
                course_id=m.course_id,
                learner_membership_id=m.learner_membership_id,
                objective_id=m.objective_id,
                objective_code=obj.code,
                objective_title=obj.title,
                mastery_threshold=obj.mastery_threshold,
                mastery_score=m.mastery_score,
                mastery_status=m.mastery_status,
                attempts_count=m.attempts_count,
                incorrect_streak=m.incorrect_streak,
                prior_score=m.prior_score,
                score_delta=m.score_delta,
                calculation_version=m.calculation_version,
                evidence_refs=m.evidence_refs,
                last_evaluated_at=m.last_evaluated_at,
            )
            for m, obj in rows
        ]

    async def get_my_recommendations(
        self, principal: PrincipalContext, course_id: UUID | None = None
    ) -> list[RecommendationResponse]:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        stmt = (
            select(Recommendation, LearningObjective)
            .join(
                LearningObjective,
                (LearningObjective.id == Recommendation.objective_id)
                & (LearningObjective.tenant_id == Recommendation.tenant_id),
            )
            .where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.learner_membership_id == principal.membership_id,
            )
        )
        if course_id is not None:
            stmt = stmt.where(Recommendation.course_id == course_id)
        stmt = stmt.order_by(Recommendation.created_at.desc())
        rows = (await self.session.execute(stmt)).all()
        return [
            RecommendationResponse(
                id=r.id,
                tenant_id=r.tenant_id,
                course_id=r.course_id,
                learner_membership_id=r.learner_membership_id,
                objective_id=r.objective_id,
                objective_code=obj.code,
                objective_title=obj.title,
                recommendation_type=r.recommendation_type,
                title=r.title,
                reason_explanation=r.reason_explanation,
                calculation_version=r.calculation_version,
                evidence_refs=r.evidence_refs,
                status=r.status,
                learner_feedback=r.learner_feedback,
                feedback_comment=r.feedback_comment,
                created_at=r.created_at,
            )
            for r, obj in rows
        ]

    async def submit_recommendation_feedback(
        self,
        *,
        principal: PrincipalContext,
        recommendation_id: UUID,
        req: RecommendationFeedbackRequest,
    ) -> RecommendationResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        rec = (
            await self.session.execute(
                select(Recommendation).where(
                    Recommendation.tenant_id == tenant_id,
                    Recommendation.id == recommendation_id,
                    Recommendation.learner_membership_id == principal.membership_id,
                )
            )
        ).scalar_one_or_none()
        if rec is None:
            raise NotFoundError("Recommendation not found.")

        rec.learner_feedback = req.feedback
        rec.feedback_comment = req.comment
        await self.session.flush()

        obj = (
            await self.session.execute(
                select(LearningObjective).where(
                    LearningObjective.tenant_id == tenant_id,
                    LearningObjective.id == rec.objective_id,
                )
            )
        ).scalar_one()
        return RecommendationResponse(
            id=rec.id,
            tenant_id=rec.tenant_id,
            course_id=rec.course_id,
            learner_membership_id=rec.learner_membership_id,
            objective_id=rec.objective_id,
            objective_code=obj.code,
            objective_title=obj.title,
            recommendation_type=rec.recommendation_type,
            title=rec.title,
            reason_explanation=rec.reason_explanation,
            calculation_version=rec.calculation_version,
            evidence_refs=rec.evidence_refs,
            status=rec.status,
            learner_feedback=rec.learner_feedback,
            feedback_comment=rec.feedback_comment,
            created_at=rec.created_at,
        )

    async def get_my_progress(
        self, principal: PrincipalContext
    ) -> LearnerProgressSummaryResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        enr_rows = (
            await self.session.execute(
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
            )
        ).all()

        course_progress: list[dict[str, Any]] = []
        comp_values: list[float] = []
        for enr, crs, snap in enr_rows:
            comp = snap.completion_percentage if snap else 0.0
            comp_values.append(comp)
            course_progress.append(
                {
                    "enrollment_id": str(enr.id),
                    "course_id": str(crs.id),
                    "course_code": crs.code,
                    "course_title": crs.title,
                    "completion_percentage": comp,
                    "lessons_completed_count": snap.lessons_completed_count if snap else 0,
                    "total_lessons_count": snap.total_lessons_count if snap else 0,
                    "latest_assessment_score": snap.latest_assessment_score if snap else None,
                    "mastered_objectives_count": snap.mastered_objectives_count if snap else 0,
                    "total_objectives_count": snap.total_objectives_count if snap else 0,
                }
            )

        att_rows = (
            await self.session.execute(
                select(AssessmentAttempt, Assessment, GradingResult)
                .join(
                    Assessment,
                    (Assessment.id == AssessmentAttempt.assessment_id)
                    & (Assessment.tenant_id == AssessmentAttempt.tenant_id),
                )
                .join(
                    GradingResult,
                    (GradingResult.attempt_id == AssessmentAttempt.id)
                    & (GradingResult.tenant_id == AssessmentAttempt.tenant_id),
                )
                .where(
                    AssessmentAttempt.tenant_id == tenant_id,
                    AssessmentAttempt.learner_membership_id == principal.membership_id,
                )
                .order_by(AssessmentAttempt.submitted_at.desc())
            )
        ).all()

        scores = [gr.score_percentage for _, _, gr in att_rows]
        recent_attempts = [
            {
                "attempt_id": str(att.id),
                "assessment_id": str(asmt.id),
                "assessment_title": asmt.title,
                "assessment_type": asmt.assessment_type,
                "attempt_number": att.attempt_number,
                "score_percentage": gr.score_percentage,
                "passed": gr.passed,
                "submitted_at": att.submitted_at.isoformat() if att.submitted_at else None,
            }
            for att, asmt, gr in att_rows[:10]
        ]

        mastery_items = await self.get_my_mastery(principal)
        mastered_count = sum(1 for m in mastery_items if m.mastery_status == "mastered")
        gap_count = sum(1 for m in mastery_items if m.mastery_status == "gap_detected")
        recs = await self.get_my_recommendations(principal)
        active_recs = sum(1 for r in recs if r.status == "active")

        return LearnerProgressSummaryResponse(
            learner_membership_id=principal.membership_id,
            enrolled_courses_count=len(enr_rows),
            average_completion_percentage=(
                round(sum(comp_values) / len(comp_values), 2) if comp_values else 0.0
            ),
            average_assessment_score=(
                round(sum(scores) / len(scores), 2) if scores else None
            ),
            mastered_objectives_count=mastered_count,
            gap_objectives_count=gap_count,
            active_recommendations_count=active_recs,
            course_progress=course_progress,
            recent_attempts=recent_attempts,
        )

    async def get_course_analytics(
        self, principal: PrincipalContext, course_id: UUID
    ) -> CourseAnalyticsResponse:
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

        enr_rows = (
            await self.session.execute(
                select(Enrollment, ProgressSnapshot, TenantMembership, User)
                .outerjoin(
                    ProgressSnapshot,
                    (ProgressSnapshot.enrollment_id == Enrollment.id)
                    & (ProgressSnapshot.tenant_id == Enrollment.tenant_id),
                )
                .join(
                    TenantMembership,
                    (TenantMembership.id == Enrollment.membership_id)
                    & (TenantMembership.tenant_id == Enrollment.tenant_id),
                )
                .join(User, User.id == TenantMembership.user_id)
                .where(
                    Enrollment.tenant_id == tenant_id,
                    Enrollment.course_id == course_id,
                )
            )
        ).all()

        comp_vals = [snap.completion_percentage if snap else 0.0 for _, snap, _, _ in enr_rows]
        learner_summaries: list[dict[str, Any]] = []
        for enr, snap, mem, usr in enr_rows:
            learner_summaries.append(
                {
                    "membership_id": str(mem.id),
                    "learner_name": usr.full_name,
                    "learner_email": usr.email,
                    "enrollment_status": enr.status,
                    "completion_percentage": snap.completion_percentage if snap else 0.0,
                    "latest_assessment_score": snap.latest_assessment_score if snap else None,
                    "mastered_objectives_count": snap.mastered_objectives_count if snap else 0,
                }
            )

        att_rows = (
            await self.session.execute(
                select(GradingResult.score_percentage)
                .join(
                    AssessmentAttempt,
                    (AssessmentAttempt.id == GradingResult.attempt_id)
                    & (AssessmentAttempt.tenant_id == GradingResult.tenant_id),
                )
                .join(
                    Assessment,
                    (Assessment.id == AssessmentAttempt.assessment_id)
                    & (Assessment.tenant_id == AssessmentAttempt.tenant_id),
                )
                .where(
                    GradingResult.tenant_id == tenant_id,
                    Assessment.course_id == course_id,
                )
            )
        ).scalars().all()
        score_list = [float(s) for s in att_rows]

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
        obj_analytics: list[dict[str, Any]] = []
        for obj in objs:
            m_rows = list(
                (
                    await self.session.execute(
                        select(LearnerObjectiveMastery).where(
                            LearnerObjectiveMastery.tenant_id == tenant_id,
                            LearnerObjectiveMastery.objective_id == obj.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            avg_m = (
                round(sum(m.mastery_score for m in m_rows) / len(m_rows), 2)
                if m_rows
                else 0.0
            )
            gaps = sum(1 for m in m_rows if m.mastery_status == "gap_detected")
            mastered = sum(1 for m in m_rows if m.mastery_status == "mastered")
            obj_analytics.append(
                {
                    "objective_id": str(obj.id),
                    "code": obj.code,
                    "title": obj.title,
                    "average_mastery_score": avg_m,
                    "learners_evaluated": len(m_rows),
                    "mastered_count": mastered,
                    "gap_detected_count": gaps,
                }
            )

        return CourseAnalyticsResponse(
            course_id=course.id,
            course_title=course.title,
            enrolled_learners_count=len(enr_rows),
            average_completion_percentage=(
                round(sum(comp_vals) / len(comp_vals), 2) if comp_vals else 0.0
            ),
            submitted_attempts_count=len(score_list),
            average_assessment_score=(
                round(sum(score_list) / len(score_list), 2) if score_list else None
            ),
            objective_analytics=obj_analytics,
            learner_summaries=learner_summaries,
        )

    async def get_cohort_progress(
        self, principal: PrincipalContext, cohort_id: UUID
    ) -> CohortProgressResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )

        cohort = (
            await self.session.execute(
                select(Cohort).where(Cohort.tenant_id == tenant_id, Cohort.id == cohort_id)
            )
        ).scalar_one_or_none()
        if cohort is None:
            raise NotFoundError("Cohort not found.")

        cm_rows = (
            await self.session.execute(
                select(CohortMembership, TenantMembership, User)
                .join(
                    TenantMembership,
                    (TenantMembership.id == CohortMembership.membership_id)
                    & (TenantMembership.tenant_id == CohortMembership.tenant_id),
                )
                .join(User, User.id == TenantMembership.user_id)
                .where(
                    CohortMembership.tenant_id == tenant_id,
                    CohortMembership.cohort_id == cohort_id,
                )
            )
        ).all()

        members_progress: list[dict[str, Any]] = []
        all_comp: list[float] = []
        all_mastery: list[float] = []

        for cm, mem, usr in cm_rows:
            snaps = list(
                (
                    await self.session.execute(
                        select(ProgressSnapshot)
                        .join(
                            Enrollment,
                            (Enrollment.id == ProgressSnapshot.enrollment_id)
                            & (Enrollment.tenant_id == ProgressSnapshot.tenant_id),
                        )
                        .where(
                            Enrollment.tenant_id == tenant_id,
                            Enrollment.membership_id == mem.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            m_rows = list(
                (
                    await self.session.execute(
                        select(LearnerObjectiveMastery).where(
                            LearnerObjectiveMastery.tenant_id == tenant_id,
                            LearnerObjectiveMastery.learner_membership_id == mem.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            avg_c = (
                round(sum(s.completion_percentage for s in snaps) / len(snaps), 2)
                if snaps
                else 0.0
            )
            avg_m = (
                round(sum(m.mastery_score for m in m_rows) / len(m_rows), 2)
                if m_rows
                else 0.0
            )
            all_comp.append(avg_c)
            all_mastery.append(avg_m)
            members_progress.append(
                {
                    "membership_id": str(mem.id),
                    "full_name": usr.full_name,
                    "email": usr.email,
                    "role_in_cohort": cm.role_in_cohort,
                    "average_completion_percentage": avg_c,
                    "average_mastery_score": avg_m,
                }
            )

        return CohortProgressResponse(
            cohort_id=cohort.id,
            cohort_name=cohort.name,
            cohort_code=cohort.code,
            learners_count=len(cm_rows),
            average_completion_percentage=(
                round(sum(all_comp) / len(all_comp), 2) if all_comp else 0.0
            ),
            average_mastery_score=(
                round(sum(all_mastery) / len(all_mastery), 2) if all_mastery else 0.0
            ),
            members_progress=members_progress,
        )
