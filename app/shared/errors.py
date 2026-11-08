from typing import Any


class AppError(Exception):
    """Base application exception with deterministic HTTP status and error code."""

    status_code: int = 400
    error_code: str = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class AuthenticationError(AppError):
    status_code = 401
    error_code = "AUTHENTICATION_FAILED"


class AuthorizationError(AppError):
    status_code = 403
    error_code = "PERMISSION_DENIED"


class NotFoundError(AppError):
    status_code = 404
    error_code = "RESOURCE_NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    error_code = "RESOURCE_CONFLICT"


class ValidationAppError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class RateLimitExceededError(AppError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class QuotaExceededError(AppError):
    status_code = 429
    error_code = "TENANT_QUOTA_EXCEEDED"


class ExternalProviderError(AppError):
    status_code = 502
    error_code = "EXTERNAL_PROVIDER_ERROR"
