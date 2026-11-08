from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.db.session import get_db_session
from app.modules.content.schemas import DocumentResponse
from app.modules.content.service import DocumentService

router = APIRouter(tags=["Course Documents & Processing"])


@router.post(
    "/courses/{course_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_course_document(
    course_id: UUID,
    title: str = Form(..., min_length=2, max_length=255),
    file: UploadFile = File(...),
    process_async: bool = Query(default=False),
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    content_bytes = await file.read()
    svc = DocumentService(session)
    return await svc.upload_course_document(
        principal=principal,
        course_id=course_id,
        title=title,
        filename=file.filename or "document.txt",
        content_type=file.content_type or "text/plain",
        content_bytes=content_bytes,
        process_immediately=not process_async,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    svc = DocumentService(session)
    return await svc.get_document(principal, document_id)


@router.get(
    "/courses/{course_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_course_documents(
    course_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentResponse]:
    svc = DocumentService(session)
    return await svc.list_course_documents(principal, course_id)


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_document(
    document_id: UUID,
    process_async: bool = Query(default=False),
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    svc = DocumentService(session)
    return await svc.reprocess_document(
        principal=principal,
        document_id=document_id,
        process_immediately=not process_async,
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_id: UUID,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    svc = DocumentService(session)
    await svc.delete_document(principal=principal, document_id=document_id)
