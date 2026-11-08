import hashlib
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.shared.errors import ValidationAppError

ALLOWED_MIME_TYPES: dict[str, set[str]] = {
    "text/plain": {".txt", ".md"},
    "text/markdown": {".md", ".txt"},
    "application/pdf": {".pdf"},
}


class PrivateObjectStorage:
    """Private object storage abstraction that never exposes storage keys as public URLs.
    Enforces tenant-partitioned paths, size limits, and content validation.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        settings = get_settings()
        self.base_path = Path(base_dir or settings.local_storage_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = settings.max_upload_size_bytes

    def validate_and_store(
        self,
        *,
        tenant_id: UUID,
        course_id: UUID,
        document_id: UUID,
        version_number: int,
        filename: str,
        content_type: str,
        content_bytes: bytes,
    ) -> tuple[str, str, int]:
        if not content_bytes:
            raise ValidationAppError("Uploaded document cannot be empty.")
        if len(content_bytes) > self.max_size_bytes:
            raise ValidationAppError(
                f"Uploaded file exceeds maximum allowed size of {self.max_size_bytes} bytes."
            )

        normalized_ct = content_type.split(";")[0].strip().lower()
        ext = Path(filename).suffix.lower() or ".txt"
        if normalized_ct not in ALLOWED_MIME_TYPES:
            raise ValidationAppError(
                f"Unsupported content type '{normalized_ct}'. Allowed: text/plain, text/markdown, application/pdf."
            )
        if ext not in ALLOWED_MIME_TYPES[normalized_ct]:
            raise ValidationAppError(
                f"File extension '{ext}' does not match content type '{normalized_ct}'."
            )

        # Signature verification for PDFs vs text
        if normalized_ct == "application/pdf" and not content_bytes.startswith(b"%PDF-"):
            raise ValidationAppError("Invalid PDF file signature.")
        if normalized_ct in ("text/plain", "text/markdown") and b"\x00" in content_bytes[:4096]:
            raise ValidationAppError("Binary content detected in text upload.")

        checksum = hashlib.sha256(content_bytes).hexdigest()
        safe_name = f"v{version_number}_{checksum[:16]}{ext}"
        rel_key = f"tenants/{tenant_id}/courses/{course_id}/documents/{document_id}/{safe_name}"
        full_path = (self.base_path / rel_key).resolve()

        # Prevent path traversal outside base_path
        if not str(full_path).startswith(str(self.base_path)):
            raise ValidationAppError("Invalid storage key path.")

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content_bytes)
        return rel_key, checksum, len(content_bytes)

    def read_bytes(self, storage_key: str) -> bytes:
        full_path = (self.base_path / storage_key).resolve()
        if not str(full_path).startswith(str(self.base_path)) or not full_path.is_file():
            raise ValidationAppError("Stored document payload could not be located.")
        return full_path.read_bytes()

    def delete_object(self, storage_key: str) -> None:
        full_path = (self.base_path / storage_key).resolve()
        if str(full_path).startswith(str(self.base_path)) and full_path.is_file():
            full_path.unlink(missing_ok=True)
