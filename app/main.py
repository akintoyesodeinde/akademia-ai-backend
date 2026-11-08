from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.observability import RequestTracingMiddleware
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Akademia AI — Learning Management & Intelligence API",
        version="0.1.0",
        description=(
            "Production-grade multi-tenant SaaS Learning Management & Intelligence Platform "
            "with PostgreSQL Row-Level Security, immutable course/assessment versioning, "
            "course-grounded RAG AI tutoring, and explainable learning intelligence."
        ),
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(RequestTracingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID", "Idempotency-Key"],
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/docs", include_in_schema=False)
    async def root_docs_redirect() -> RedirectResponse:
        return RedirectResponse(url=f"{settings.api_v1_prefix}/docs")

    @app.get("/openapi.json", include_in_schema=False)
    async def root_openapi_redirect() -> RedirectResponse:
        return RedirectResponse(url=f"{settings.api_v1_prefix}/openapi.json")

    @app.get("/health", include_in_schema=False)
    async def root_health_redirect() -> RedirectResponse:
        return RedirectResponse(url=f"{settings.api_v1_prefix}/platform/health")

    return app


app = create_app()
