import asyncio
from uuid import UUID

from sqlalchemy import text

from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory, tenant_scoped_session
from app.modules.ai_tutor.service import AITutorService
from app.modules.content.service import DocumentService

logger = get_logger("worker")


async def run_worker_iteration() -> dict[str, int]:
    """Poll and execute queued or interrupted document processing and AI jobs.
    Each job executes strictly inside its own verified transaction-local tenant RLS context.
    """
    factory = get_session_factory()
    async with factory() as bootstrap_session:
        doc_rows = (
            await bootstrap_session.execute(
                text("SELECT * FROM list_pending_document_jobs_bootstrap(10)")
            )
        ).mappings().all()
        ai_rows = (
            await bootstrap_session.execute(
                text("SELECT * FROM list_pending_ai_jobs_bootstrap(10)")
            )
        ).mappings().all()

    doc_processed = 0
    for row in doc_rows:
        job_id: UUID = row["job_id"]
        tenant_id: UUID = row["tenant_id"]
        try:
            async with tenant_scoped_session(tenant_id) as session:
                doc_svc = DocumentService(session)
                await doc_svc.process_document_job(tenant_id=tenant_id, job_id=job_id)
                doc_processed += 1
        except Exception as exc:
            logger.error(
                "worker_document_job_error",
                job_id=str(job_id),
                tenant_id=str(tenant_id),
                error=str(exc),
            )

    ai_processed = 0
    for row in ai_rows:
        job_id = row["job_id"]
        tenant_id = row["tenant_id"]
        try:
            async with tenant_scoped_session(tenant_id) as session:
                ai_svc = AITutorService(session)
                await ai_svc.execute_practice_generation_job(
                    tenant_id=tenant_id, job_id=job_id
                )
                ai_processed += 1
        except Exception as exc:
            logger.error(
                "worker_ai_job_error",
                job_id=str(job_id),
                tenant_id=str(tenant_id),
                error=str(exc),
            )

    return {"document_jobs": doc_processed, "ai_jobs": ai_processed}


async def worker_loop(poll_interval_seconds: float = 2.0) -> None:
    configure_logging()
    logger.info("worker_started")
    while True:
        try:
            counts = await run_worker_iteration()
            if counts["document_jobs"] or counts["ai_jobs"]:
                logger.info("worker_batch_completed", **counts)
        except Exception as exc:
            logger.error("worker_loop_error", error=str(exc))
        await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(worker_loop())
