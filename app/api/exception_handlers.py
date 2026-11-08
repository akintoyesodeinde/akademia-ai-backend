from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import get_logger, request_id_ctx_var
from app.shared.errors import AppError

logger = get_logger("exceptions")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "request_id": request_id_ctx_var.get(),
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized_errors = [
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "msg": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_FAILED",
                    "message": "Request validation failed.",
                    "request_id": request_id_ctx_var.get(),
                    "details": sanitized_errors,
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        logger.warning(
            "database_integrity_conflict",
            path=request.url.path,
            error_type=type(getattr(exc, "orig", exc)).__name__,
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "DATABASE_CONSTRAINT_CONFLICT",
                    "message": "The requested operation violates a uniqueness or relational constraint.",
                    "request_id": request_id_ctx_var.get(),
                    "details": None,
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_error(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        # Never expose raw SQL statements or internal driver traces to clients
        logger.error(
            "database_operation_failed",
            path=request.url.path,
            error_type=type(getattr(exc, "orig", exc)).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "DATABASE_OPERATION_ERROR",
                    "message": "A database error occurred while processing the request.",
                    "request_id": request_id_ctx_var.get(),
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_server_exception",
            path=request.url.path,
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected internal error occurred.",
                    "request_id": request_id_ctx_var.get(),
                    "details": None,
                }
            },
        )
