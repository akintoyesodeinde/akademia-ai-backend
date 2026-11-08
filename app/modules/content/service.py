import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.registry import get_content_extractor, get_embedding_model
from app.core.authorization import PrincipalContext, TenantRole
from app.modules.audit.service import AuditService
from app.modules.content.models import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentProcessingJob,
    DocumentVersion,
)
from app.modules.content.schemas import DocumentJobView, DocumentResponse
from app.modules.courses.models import Course
from app.modules.enrollments.models import Enrollment
from app.modules.subscriptions.service import SubscriptionService
from app.shared.errors import AuthorizationError, NotFoundError
from app.shared.storage import PrivateObjectStorage


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        storage: PrivateObjectStorage | None = None,
    ) -> None:
        self.session = session
        self.storage = storage or PrivateObjectStorage()
        self.audit = AuditService(session)
        self.subscriptions = SubscriptionService(session)

    async def _to_response(self, doc: Document) -> DocumentResponse:
        chunks_count = int(
            (
                await self.session.execute(
                    select(func.count(DocumentChunk.id)).where(
                        DocumentChunk.tenant_id == doc.tenant_id,
                        DocumentChunk.document_id == doc.id,
                    )
                )
            ).scalar_one()
            or 0
        )
        latest_job = (
            await self.session.execute(
                select(DocumentProcessingJob)
                .where(
                    DocumentProcessingJob.tenant_id == doc.tenant_id,
                    DocumentProcessingJob.document_id == doc.id,
                )
                .order_by(DocumentProcessingJob.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        job_view = (
            DocumentJobView(
                id=latest_job.id,
                status=latest_job.status,
                attempt_count=latest_job.attempt_count,
                max_retries=latest_job.max_retries,
                error_message=latest_job.error_message,
                started_at=latest_job.started_at,
                completed_at=latest_job.completed_at,
            )
            if latest_job
            else None
        )

        return DocumentResponse(
            id=doc.id,
            tenant_id=doc.tenant_id,
            course_id=doc.course_id,
            title=doc.title,
            filename=doc.filename,
            content_type=doc.content_type,
            status=doc.status,
            current_version_number=doc.current_version_number,
            checksum_sha256=doc.checksum_sha256,
            size_bytes=doc.size_bytes,
            uploaded_by_membership_id=doc.uploaded_by_membership_id,
            failure_reason=doc.failure_reason,
            chunks_count=chunks_count,
            latest_job=job_view,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def upload_course_document(
        self,
        *,
        principal: PrincipalContext,
        course_id: UUID,
        title: str,
        filename: str,
        content_type: str,
        content_bytes: bytes,
        process_immediately: bool = False,
    ) -> DocumentResponse:
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

        await self.subscriptions.check_and_increment_storage_quota(
            tenant_id, len(content_bytes)
        )

        doc_id = uuid4()
        storage_key, checksum, size_bytes = self.storage.validate_and_store(
            tenant_id=tenant_id,
            course_id=course.id,
            document_id=doc_id,
            version_number=1,
            filename=filename,
            content_type=content_type,
            content_bytes=content_bytes,
        )

        # Check duplicate checksum in same course (if an active ready document exists with same title, bump version)
        existing_doc = (
            await self.session.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.course_id == course.id,
                    Document.title == title.strip(),
                    Document.status != "deleted",
                )
            )
        ).scalar_one_or_none()

        if existing_doc is not None:
            next_ver = existing_doc.current_version_number + 1
            storage_key, checksum, size_bytes = self.storage.validate_and_store(
                tenant_id=tenant_id,
                course_id=course.id,
                document_id=existing_doc.id,
                version_number=next_ver,
                filename=filename,
                content_type=content_type,
                content_bytes=content_bytes,
            )
            existing_doc.current_version_number = next_ver
            existing_doc.checksum_sha256 = checksum
            existing_doc.size_bytes = size_bytes
            existing_doc.storage_key = storage_key
            existing_doc.filename = filename
            existing_doc.content_type = content_type
            existing_doc.status = "pending"
            existing_doc.failure_reason = None
            doc = existing_doc
        else:
            doc = Document(
                id=doc_id,
                tenant_id=tenant_id,
                course_id=course.id,
                title=title.strip(),
                filename=filename,
                content_type=content_type.split(";")[0].strip().lower(),
                status="pending",
                current_version_number=1,
                checksum_sha256=checksum,
                size_bytes=size_bytes,
                storage_key=storage_key,
                uploaded_by_membership_id=principal.membership_id,
            )
            self.session.add(doc)
            await self.session.flush()

        doc_ver = DocumentVersion(
            tenant_id=tenant_id,
            document_id=doc.id,
            version_number=doc.current_version_number,
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            storage_key=storage_key,
            extraction_status="pending",
        )
        self.session.add(doc_ver)
        await self.session.flush()

        job = DocumentProcessingJob(
            tenant_id=tenant_id,
            document_id=doc.id,
            document_version_id=doc_ver.id,
            status="queued",
            attempt_count=0,
            max_retries=3,
        )
        self.session.add(job)
        await self.session.flush()

        if process_immediately:
            await self.process_document_job(tenant_id=tenant_id, job_id=job.id)

        return await self._to_response(doc)

    async def process_document_job(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        simulate_interruption: bool = False,
    ) -> DocumentProcessingJob:
        """Idempotent worker execution for a document ingestion job inside a verified tenant context."""
        job = (
            await self.session.execute(
                select(DocumentProcessingJob).where(
                    DocumentProcessingJob.tenant_id == tenant_id,
                    DocumentProcessingJob.id == job_id,
                )
            )
        ).scalar_one_or_none()
        if job is None:
            raise NotFoundError("Document processing job not found.")

        if job.status == "completed":
            return job

        doc = (
            await self.session.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.id == job.document_id,
                )
            )
        ).scalar_one()
        doc_ver = (
            await self.session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.tenant_id == tenant_id,
                    DocumentVersion.id == job.document_version_id,
                )
            )
        ).scalar_one()

        now = datetime.now(UTC)
        job.status = "processing"
        job.attempt_count += 1
        job.started_at = now
        doc.status = "processing"
        doc_ver.extraction_status = "processing"
        await self.session.flush()

        if simulate_interruption:
            raise RuntimeError("Simulated worker interruption during document processing.")

        start_t = time.perf_counter()
        try:
            raw_bytes = self.storage.read_bytes(doc_ver.storage_key)
            extractor = get_content_extractor()
            chunk_payloads = extractor.extract_and_chunk(
                content_bytes=raw_bytes,
                content_type=doc.content_type,
                filename=doc.filename,
            )

            # Idempotently clear any partial chunks/embeddings for this document before inserting new version chunks
            await self.session.execute(
                delete(ChunkEmbedding).where(
                    ChunkEmbedding.tenant_id == tenant_id,
                    ChunkEmbedding.document_id == doc.id,
                )
            )
            await self.session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.document_id == doc.id,
                )
            )
            await self.session.flush()

            embedding_model = get_embedding_model()
            embed_res = await embedding_model.embed_texts(
                [cp.content_text for cp in chunk_payloads]
            )

            for cp, vec in zip(chunk_payloads, embed_res.vectors, strict=True):
                chunk_rec = DocumentChunk(
                    tenant_id=tenant_id,
                    course_id=doc.course_id,
                    document_id=doc.id,
                    document_version_id=doc_ver.id,
                    chunk_index=cp.chunk_index,
                    page_number=cp.page_number,
                    section_title=cp.section_title,
                    content_text=cp.content_text,
                    token_count=cp.token_count,
                    chunk_metadata={"version_number": doc_ver.version_number},
                )
                self.session.add(chunk_rec)
                await self.session.flush()

                emb_rec = ChunkEmbedding(
                    tenant_id=tenant_id,
                    course_id=doc.course_id,
                    document_id=doc.id,
                    chunk_id=chunk_rec.id,
                    document_version_number=doc_ver.version_number,
                    embedding_model_id=embed_res.model_id,
                    embedding_model_version=embed_res.model_version,
                    embedding_dimension=embed_res.dimension,
                    indexing_status="indexed",
                    embedding=vec,
                )
                self.session.add(emb_rec)

            latency_ms = max(1, int((time.perf_counter() - start_t) * 1000))
            await self.subscriptions.record_ai_usage(
                tenant_id=tenant_id,
                membership_id=doc.uploaded_by_membership_id,
                operation_type="document_embedding",
                provider_name=embedding_model.provider_name,
                model_id=embed_res.model_id,
                prompt_version="embedding-v1",
                input_tokens=embed_res.total_tokens,
                output_tokens=0,
                latency_ms=latency_ms,
            )

            doc.status = "ready"
            doc.failure_reason = None
            doc_ver.extraction_status = "completed"
            job.status = "completed"
            job.error_message = None
            job.completed_at = datetime.now(UTC)
            await self.session.flush()
            return job
        except Exception as exc:
            doc.status = "failed"
            doc.failure_reason = str(exc)
            doc_ver.extraction_status = "failed"
            job.status = "failed"
            job.error_message = str(exc)
            await self.session.flush()
            return job

    async def get_document(
        self, principal: PrincipalContext, document_id: UUID
    ) -> DocumentResponse:
        tenant_id = principal.require_tenant()
        doc = (
            await self.session.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.id == document_id,
                    Document.status != "deleted",
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            raise NotFoundError("Document not found.")
        return await self._to_response(doc)

    async def list_course_documents(
        self, principal: PrincipalContext, course_id: UUID
    ) -> list[DocumentResponse]:
        tenant_id = principal.require_tenant()
        is_staff = principal.has_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        if not is_staff:
            enr = (
                await self.session.execute(
                    select(Enrollment).where(
                        Enrollment.tenant_id == tenant_id,
                        Enrollment.course_id == course_id,
                        Enrollment.membership_id == principal.membership_id,
                    )
                )
            ).scalar_one_or_none()
            if enr is None:
                raise AuthorizationError(
                    "Learners must be enrolled in the course to view course documents."
                )

        stmt = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.course_id == course_id,
                Document.status != "deleted",
            )
            .order_by(Document.created_at.desc())
        )
        if not is_staff:
            stmt = stmt.where(Document.status == "ready")
        docs = list((await self.session.execute(stmt)).scalars().all())
        return [await self._to_response(d) for d in docs]

    async def reprocess_document(
        self,
        *,
        principal: PrincipalContext,
        document_id: UUID,
        process_immediately: bool = True,
    ) -> DocumentResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        doc = (
            await self.session.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.id == document_id,
                    Document.status != "deleted",
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            raise NotFoundError("Document not found.")

        doc_ver = (
            await self.session.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.tenant_id == tenant_id,
                    DocumentVersion.document_id == doc.id,
                    DocumentVersion.version_number == doc.current_version_number,
                )
            )
        ).scalar_one()

        job = DocumentProcessingJob(
            tenant_id=tenant_id,
            document_id=doc.id,
            document_version_id=doc_ver.id,
            status="queued",
            attempt_count=0,
            max_retries=3,
        )
        self.session.add(job)
        doc.status = "pending"
        doc.failure_reason = None
        await self.session.flush()

        if process_immediately:
            await self.process_document_job(tenant_id=tenant_id, job_id=job.id)
        return await self._to_response(doc)

    async def delete_document(
        self,
        *,
        principal: PrincipalContext,
        document_id: UUID,
    ) -> None:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        doc = (
            await self.session.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.id == document_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            raise NotFoundError("Document not found.")

        # Remove embeddings and chunks immediately so deleted documents can never be retrieved
        await self.session.execute(
            delete(ChunkEmbedding).where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.document_id == doc.id,
            )
        )
        await self.session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id == doc.id,
            )
        )
        doc.status = "deleted"
        self.storage.delete_object(doc.storage_key)
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="document.deleted",
            resource_type="document",
            resource_id=str(doc.id),
            metadata_json={"title": doc.title},
        )
        await self.session.flush()
