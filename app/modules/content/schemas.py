from datetime import datetime
from uuid import UUID

from app.shared.schemas import APIModel


class DocumentJobView(APIModel):
    id: UUID
    status: str
    attempt_count: int
    max_retries: int
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DocumentResponse(APIModel):
    id: UUID
    tenant_id: UUID
    course_id: UUID
    title: str
    filename: str
    content_type: str
    status: str
    current_version_number: int
    checksum_sha256: str
    size_bytes: int
    uploaded_by_membership_id: UUID
    failure_reason: str | None = None
    chunks_count: int = 0
    latest_job: DocumentJobView | None = None
    created_at: datetime
    updated_at: datetime
