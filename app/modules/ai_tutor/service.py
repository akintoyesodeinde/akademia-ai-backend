from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import CitationReference
from app.ai.registry import get_embedding_model, get_language_model
from app.ai.retrieval.service import PgVectorCourseRetriever
from app.ai.safety.guardrails import validate_generated_practice_question
from app.core.authorization import PrincipalContext, TenantRole
from app.modules.ai_practice.models import AIGenerationReview
from app.modules.ai_tutor.models import AIConversation, AIJob, AIMessage
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
from app.modules.assessments.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentItemObjective,
    Question,
)
from app.modules.audit.service import AuditService
from app.modules.courses.models import Course, LearningObjective
from app.modules.enrollments.models import Enrollment
from app.modules.subscriptions.service import SubscriptionService
from app.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationAppError,
)


class AITutorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionService(session)
        self.audit = AuditService(session)

    async def _verify_course_access(
        self, principal: PrincipalContext, course_id: UUID
    ) -> Course:
        tenant_id = principal.require_tenant()
        course = (
            await self.session.execute(
                select(Course).where(Course.tenant_id == tenant_id, Course.id == course_id)
            )
        ).scalar_one_or_none()
        if course is None:
            raise NotFoundError("Course not found.")

        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        if not is_staff:
            enr = (
                await self.session.execute(
                    select(Enrollment).where(
                        Enrollment.tenant_id == tenant_id,
                        Enrollment.course_id == course.id,
                        Enrollment.membership_id == principal.membership_id,
                        Enrollment.status.in_(("active", "completed")),
                    )
                )
            ).scalar_one_or_none()
            if enr is None:
                raise AuthorizationError(
                    "You must be enrolled in this course to use the AI tutor."
                )
        return course

    async def create_conversation(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: CreateTutorConversationRequest,
    ) -> TutorConversationResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None
        course = await self._verify_course_access(principal, course_id)

        conv = AIConversation(
            tenant_id=tenant_id,
            course_id=course.id,
            membership_id=principal.membership_id,
            title=req.title.strip(),
            complexity_level=req.complexity_level,
            status="active",
        )
        self.session.add(conv)
        await self.session.flush()
        return TutorConversationResponse(
            id=conv.id,
            tenant_id=conv.tenant_id,
            course_id=conv.course_id,
            membership_id=conv.membership_id,
            title=conv.title,
            complexity_level=conv.complexity_level,
            status=conv.status,
            messages=[],
            created_at=conv.created_at,
        )

    async def list_course_conversations(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[TutorConversationResponse]:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None
        await self._verify_course_access(principal, course_id)

        rows = list(
            (
                await self.session.execute(
                    select(AIConversation)
                    .where(
                        AIConversation.tenant_id == tenant_id,
                        AIConversation.course_id == course_id,
                        AIConversation.membership_id == principal.membership_id,
                    )
                    .order_by(AIConversation.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            TutorConversationResponse(
                id=c.id,
                tenant_id=c.tenant_id,
                course_id=c.course_id,
                membership_id=c.membership_id,
                title=c.title,
                complexity_level=c.complexity_level,
                status=c.status,
                messages=[],
                created_at=c.created_at,
            )
            for c in rows
        ]

    async def get_conversation(
        self, principal: PrincipalContext, conversation_id: UUID
    ) -> TutorConversationResponse:
        tenant_id = principal.require_tenant()
        conv = (
            await self.session.execute(
                select(AIConversation).where(
                    AIConversation.tenant_id == tenant_id,
                    AIConversation.id == conversation_id,
                )
            )
        ).scalar_one_or_none()
        if conv is None:
            raise NotFoundError("Tutor conversation not found.")

        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        if not is_staff and conv.membership_id != principal.membership_id:
            raise AuthorizationError("Cannot access another learner's AI tutor conversation.")

        msgs = await self.list_messages(principal, conversation_id)
        return TutorConversationResponse(
            id=conv.id,
            tenant_id=conv.tenant_id,
            course_id=conv.course_id,
            membership_id=conv.membership_id,
            title=conv.title,
            complexity_level=conv.complexity_level,
            status=conv.status,
            messages=msgs,
            created_at=conv.created_at,
        )

    async def list_messages(
        self, principal: PrincipalContext, conversation_id: UUID
    ) -> list[TutorMessageResponse]:
        tenant_id = principal.require_tenant()
        conv = (
            await self.session.execute(
                select(AIConversation).where(
                    AIConversation.tenant_id == tenant_id,
                    AIConversation.id == conversation_id,
                )
            )
        ).scalar_one_or_none()
        if conv is None:
            raise NotFoundError("Tutor conversation not found.")

        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        if not is_staff and conv.membership_id != principal.membership_id:
            raise AuthorizationError("Cannot access another learner's AI tutor messages.")

        rows = list(
            (
                await self.session.execute(
                    select(AIMessage)
                    .where(
                        AIMessage.tenant_id == tenant_id,
                        AIMessage.conversation_id == conv.id,
                    )
                    .order_by(AIMessage.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            TutorMessageResponse(
                id=m.id,
                tenant_id=m.tenant_id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                grounding_status=m.grounding_status,
                citations=[CitationReference(**c) for c in (m.citations or [])],
                prompt_version=m.prompt_version,
                model_id=m.model_id,
                token_usage=m.token_usage,
                created_at=m.created_at,
            )
            for m in rows
        ]

    async def send_message(
        self,
        *,
        principal: PrincipalContext,
        conversation_id: UUID,
        req: SendTutorMessageRequest,
    ) -> TutorMessageResponse:
        tenant_id = principal.require_tenant()
        assert principal.membership_id is not None

        conv = (
            await self.session.execute(
                select(AIConversation).where(
                    AIConversation.tenant_id == tenant_id,
                    AIConversation.id == conversation_id,
                )
            )
        ).scalar_one_or_none()
        if conv is None:
            raise NotFoundError("Tutor conversation not found.")
        if conv.membership_id != principal.membership_id:
            raise AuthorizationError("Cannot post messages to another learner's conversation.")

        course = await self._verify_course_access(principal, conv.course_id)
        await self.subscriptions.check_ai_quota(tenant_id)

        # Save user message
        user_msg = AIMessage(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="user",
            content=req.content.strip(),
            grounding_status="user_query",
            citations=[],
            prompt_version="tutor-rag-v1",
            model_id="user",
            token_usage={"input_tokens": len(req.content.split())},
        )
        self.session.add(user_msg)
        await self.session.flush()

        # Academic integrity policy enforcement when an assessment attempt is currently in progress
        if course.academic_integrity_policy == "strict_during_assessment":
            active_attempt_count = int(
                (
                    await self.session.execute(
                        select(func.count(AssessmentAttempt.id))
                        .join(
                            Assessment,
                            (Assessment.id == AssessmentAttempt.assessment_id)
                            & (Assessment.tenant_id == AssessmentAttempt.tenant_id),
                        )
                        .where(
                            AssessmentAttempt.tenant_id == tenant_id,
                            Assessment.course_id == course.id,
                            AssessmentAttempt.learner_membership_id == principal.membership_id,
                            AssessmentAttempt.status == "in_progress",
                        )
                    )
                ).scalar_one()
                or 0
            )
            if active_attempt_count > 0:
                restricted_msg = AIMessage(
                    tenant_id=tenant_id,
                    conversation_id=conv.id,
                    role="assistant",
                    content=(
                        "Academic Integrity Policy Notice: You currently have an active graded "
                        "assessment attempt in progress for this course. Direct AI tutoring "
                        "answers are paused until you submit your assessment attempt."
                    ),
                    grounding_status="integrity_restricted",
                    citations=[],
                    prompt_version="tutor-rag-v1",
                    model_id="policy-guard",
                    token_usage={"input_tokens": 0, "output_tokens": 0},
                )
                self.session.add(restricted_msg)
                await self.session.flush()
                return TutorMessageResponse(
                    id=restricted_msg.id,
                    tenant_id=restricted_msg.tenant_id,
                    conversation_id=restricted_msg.conversation_id,
                    role=restricted_msg.role,
                    content=restricted_msg.content,
                    grounding_status=restricted_msg.grounding_status,
                    citations=[],
                    prompt_version=restricted_msg.prompt_version,
                    model_id=restricted_msg.model_id,
                    token_usage=restricted_msg.token_usage,
                    created_at=restricted_msg.created_at,
                )

        # Authorized pre-filtered retrieval
        embedding_model = get_embedding_model()
        retriever = PgVectorCourseRetriever(self.session, embedding_model)
        passages = await retriever.retrieve_authorized_passages(
            tenant_id=tenant_id,
            course_id=course.id,
            query=req.content,
            top_k=5,
        )

        llm = get_language_model()
        generation = await llm.generate_grounded_tutor_response(
            question=req.content,
            passages=passages,
            complexity_level=conv.complexity_level,
            prompt_version="tutor-rag-v1",
        )

        await self.subscriptions.record_ai_usage(
            tenant_id=tenant_id,
            membership_id=principal.membership_id,
            operation_type="tutor_chat",
            provider_name=llm.provider_name,
            model_id=generation.model_id,
            prompt_version=generation.prompt_version,
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
            latency_ms=generation.latency_ms,
        )

        citations_json = [c.model_dump(mode="json") for c in generation.citations]
        assistant_msg = AIMessage(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            role="assistant",
            content=generation.answer_text,
            grounding_status=generation.grounding_status,
            citations=citations_json,
            prompt_version=generation.prompt_version,
            model_id=generation.model_id,
            token_usage={
                "input_tokens": generation.input_tokens,
                "output_tokens": generation.output_tokens,
                "latency_ms": generation.latency_ms,
            },
        )
        self.session.add(assistant_msg)
        await self.session.flush()

        return TutorMessageResponse(
            id=assistant_msg.id,
            tenant_id=assistant_msg.tenant_id,
            conversation_id=assistant_msg.conversation_id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            grounding_status=assistant_msg.grounding_status,
            citations=generation.citations,
            prompt_version=assistant_msg.prompt_version,
            model_id=assistant_msg.model_id,
            token_usage=assistant_msg.token_usage,
            created_at=assistant_msg.created_at,
        )

    async def create_practice_generation_job(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        req: CreatePracticeJobRequest,
        execute_immediately: bool = True,
    ) -> AIJobResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        assert principal.membership_id is not None

        course = await self._verify_course_access(principal, course_id)
        await self.subscriptions.check_ai_quota(tenant_id)

        obj = (
            await self.session.execute(
                select(LearningObjective).where(
                    LearningObjective.tenant_id == tenant_id,
                    LearningObjective.id == req.objective_id,
                    LearningObjective.course_id == course.id,
                )
            )
        ).scalar_one_or_none()
        if obj is None:
            raise NotFoundError("Learning objective not found in this course.")

        job = AIJob(
            tenant_id=tenant_id,
            course_id=course.id,
            requested_by_membership_id=principal.membership_id,
            job_type="practice_generation",
            status="queued",
            input_params={
                "objective_id": str(obj.id),
                "objective_code": obj.code,
                "objective_title": obj.title,
                "difficulty": req.difficulty,
                "question_count": req.question_count,
            },
            attempt_count=0,
        )
        self.session.add(job)
        await self.session.flush()

        if execute_immediately:
            await self.execute_practice_generation_job(tenant_id=tenant_id, job_id=job.id)

        return await self.get_ai_job(principal=principal, job_id=job.id)

    async def execute_practice_generation_job(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> AIJob:
        job = (
            await self.session.execute(
                select(AIJob).where(AIJob.tenant_id == tenant_id, AIJob.id == job_id)
            )
        ).scalar_one_or_none()
        if job is None:
            raise NotFoundError("AI job not found.")
        if job.status in ("completed", "cancelled"):
            return job

        now = datetime.now(UTC)
        job.status = "processing"
        job.attempt_count += 1
        job.started_at = now
        await self.session.flush()

        try:
            params = job.input_params
            obj_id = UUID(str(params["objective_id"]))
            obj_code = str(params["objective_code"])
            obj_title = str(params["objective_title"])
            difficulty = str(params.get("difficulty", "medium"))
            q_count = int(params.get("question_count", 2))

            embedding_model = get_embedding_model()
            retriever = PgVectorCourseRetriever(self.session, embedding_model)
            passages = await retriever.retrieve_authorized_passages(
                tenant_id=tenant_id,
                course_id=job.course_id,
                query=f"{obj_code} {obj_title}",
                top_k=5,
            )
            if not passages:
                raise ValidationAppError(
                    "No processed course document chunks available to ground practice question generation."
                )

            llm = get_language_model()
            drafts, in_tok, out_tok, latency_ms = await llm.generate_practice_questions(
                objective_code=obj_code,
                objective_title=obj_title,
                difficulty=difficulty,
                question_count=q_count,
                passages=passages,
                prompt_version="practice-gen-v1",
            )

            existing_prompts_rows = (
                await self.session.execute(
                    select(Question.prompt).where(
                        Question.tenant_id == tenant_id,
                        Question.course_id == job.course_id,
                    )
                )
            ).scalars().all()
            existing_prompts = {p.strip().lower() for p in existing_prompts_rows}

            created_question_ids: list[str] = []
            created_review_ids: list[str] = []

            for draft in drafts:
                validation_outcome = validate_generated_practice_question(
                    draft, passages, existing_prompts
                )
                existing_prompts.add(draft.prompt.strip().lower())

                # Persist as draft requiring explicit instructor approval before publication
                q_rec = Question(
                    tenant_id=tenant_id,
                    course_id=job.course_id,
                    question_type=draft.question_type,
                    prompt=draft.prompt,
                    options=[opt.model_dump() for opt in draft.options],
                    correct_answer=draft.correct_answer,
                    explanation=draft.explanation,
                    points=10.0,
                    difficulty=draft.difficulty,
                    source_type="ai_generated",
                    status="draft",
                )
                self.session.add(q_rec)
                await self.session.flush()

                self.session.add(
                    AssessmentItemObjective(
                        tenant_id=tenant_id,
                        question_id=q_rec.id,
                        objective_id=obj_id,
                    )
                )

                source_refs = [
                    {
                        "chunk_id": str(p.chunk_id),
                        "document_id": str(p.document_id),
                        "document_title": p.document_title,
                        "page_number": p.page_number,
                        "excerpt": p.content_text[:200],
                    }
                    for p in passages
                    if p.chunk_id in set(draft.cited_chunk_ids)
                ]

                rev_rec = AIGenerationReview(
                    tenant_id=tenant_id,
                    ai_job_id=job.id,
                    question_id=q_rec.id,
                    prompt_version="practice-gen-v1",
                    model_id=llm.model_id,
                    source_references=source_refs,
                    validation_outcome=validation_outcome,
                    review_status="pending_review",
                )
                self.session.add(rev_rec)
                await self.session.flush()

                created_question_ids.append(str(q_rec.id))
                created_review_ids.append(str(rev_rec.id))

            await self.subscriptions.record_ai_usage(
                tenant_id=tenant_id,
                membership_id=job.requested_by_membership_id,
                operation_type="practice_generation",
                provider_name=llm.provider_name,
                model_id=llm.model_id,
                prompt_version="practice-gen-v1",
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=latency_ms,
            )

            job.status = "completed"
            job.result_payload = {
                "generated_question_ids": created_question_ids,
                "review_ids": created_review_ids,
                "count": len(created_question_ids),
            }
            job.completed_at = datetime.now(UTC)
            await self.session.flush()
            return job
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            await self.session.flush()
            return job

    async def get_ai_job(
        self, principal: PrincipalContext, job_id: UUID
    ) -> AIJobResponse:
        tenant_id = principal.require_tenant()
        job = (
            await self.session.execute(
                select(AIJob).where(AIJob.tenant_id == tenant_id, AIJob.id == job_id)
            )
        ).scalar_one_or_none()
        if job is None:
            raise NotFoundError("AI job not found.")
        return AIJobResponse(
            id=job.id,
            tenant_id=job.tenant_id,
            course_id=job.course_id,
            requested_by_membership_id=job.requested_by_membership_id,
            job_type=job.job_type,
            status=job.status,
            input_params=job.input_params,
            result_payload=job.result_payload,
            error_message=job.error_message,
            attempt_count=job.attempt_count,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
        )

    async def cancel_ai_job(
        self, principal: PrincipalContext, job_id: UUID
    ) -> AIJobResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        job = (
            await self.session.execute(
                select(AIJob).where(AIJob.tenant_id == tenant_id, AIJob.id == job_id)
            )
        ).scalar_one_or_none()
        if job is None:
            raise NotFoundError("AI job not found.")
        if job.status == "completed":
            raise ConflictError("Completed AI job cannot be cancelled.")
        job.status = "cancelled"
        job.completed_at = datetime.now(UTC)
        await self.session.flush()
        return await self.get_ai_job(principal=principal, job_id=job.id)

    async def list_practice_drafts(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[PracticeDraftReviewResponse]:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        stmt = (
            select(AIGenerationReview, Question)
            .join(
                Question,
                (Question.id == AIGenerationReview.question_id)
                & (Question.tenant_id == AIGenerationReview.tenant_id),
            )
            .where(
                AIGenerationReview.tenant_id == tenant_id,
                Question.course_id == course_id,
            )
            .order_by(AIGenerationReview.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            PracticeDraftReviewResponse(
                review_id=rev.id,
                ai_job_id=rev.ai_job_id,
                question_id=q.id,
                course_id=q.course_id,
                prompt=q.prompt,
                options=q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                difficulty=q.difficulty,
                question_status=q.status,
                review_status=rev.review_status,
                prompt_version=rev.prompt_version,
                model_id=rev.model_id,
                source_references=rev.source_references,
                validation_outcome=rev.validation_outcome,
                reviewer_notes=rev.reviewer_notes,
                reviewed_at=rev.reviewed_at,
            )
            for rev, q in rows
        ]

    async def review_practice_draft(
        self,
        *,
        principal: PrincipalContext,
        review_id: UUID,
        req: ReviewPracticeDraftRequest,
    ) -> PracticeDraftReviewResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        assert principal.membership_id is not None

        row = (
            await self.session.execute(
                select(AIGenerationReview, Question)
                .join(
                    Question,
                    (Question.id == AIGenerationReview.question_id)
                    & (Question.tenant_id == AIGenerationReview.tenant_id),
                )
                .where(
                    AIGenerationReview.tenant_id == tenant_id,
                    AIGenerationReview.id == review_id,
                )
            )
        ).first()
        if row is None:
            raise NotFoundError("Practice generation review record not found.")

        rev, q = row
        if req.prompt_override:
            q.prompt = req.prompt_override.strip()
        if req.correct_answer_override:
            q.correct_answer = req.correct_answer_override.strip()

        rev.review_status = req.decision
        rev.reviewer_membership_id = principal.membership_id
        rev.reviewer_notes = req.reviewer_notes
        rev.reviewed_at = datetime.now(UTC)
        q.status = "approved" if req.decision == "approved" else "rejected"

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action=f"ai_practice_draft.{req.decision}",
            resource_type="question",
            resource_id=str(q.id),
            metadata_json={"review_id": str(rev.id), "decision": req.decision},
        )
        await self.session.flush()

        return PracticeDraftReviewResponse(
            review_id=rev.id,
            ai_job_id=rev.ai_job_id,
            question_id=q.id,
            course_id=q.course_id,
            prompt=q.prompt,
            options=q.options,
            correct_answer=q.correct_answer,
            explanation=q.explanation,
            difficulty=q.difficulty,
            question_status=q.status,
            review_status=rev.review_status,
            prompt_version=rev.prompt_version,
            model_id=rev.model_id,
            source_references=rev.source_references,
            validation_outcome=rev.validation_outcome,
            reviewer_notes=rev.reviewer_notes,
            reviewed_at=rev.reviewed_at,
        )
