import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

# Point default test environment to the isolated PostgreSQL test database (with ssl=disable for fast local TCP)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://akademia_app:akademia_app_dev_pw@127.0.0.1:5436/akademia_ai_test?ssl=disable",
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgresql+asyncpg://akademia_migrator:akademia_migrator_dev_pw@127.0.0.1:5436/akademia_ai_test?ssl=disable",
)
os.environ.setdefault(
    "WORKER_DATABASE_URL",
    "postgresql+asyncpg://akademia_worker:akademia_worker_dev_pw@127.0.0.1:5436/akademia_ai_test?ssl=disable",
)
os.environ.setdefault(
    "SUPERUSER_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres_dev_pw@127.0.0.1:5436/akademia_ai_test?ssl=disable",
)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOCAL_STORAGE_PATH", "./storage_data_test")

from app.core.config import get_settings  # noqa: E402
from app.db.session import dispose_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.shared.rate_limit import rate_limiter  # noqa: E402

# Advisory lock key that serializes database resets across concurrent pytest processes.
_RESET_LOCK_KEY = 99887766

# Root tables deleted in dependency-safe order; remaining tenant-owned rows are removed
# through ON DELETE CASCADE foreign keys. Child tables whose composite FKs use
# ON DELETE SET NULL on NOT NULL columns (e.g. learning_events) are deleted explicitly first.
_RESET_TABLES: tuple[str, ...] = (
    "outbox_events",
    "audit_events",
    "idempotency_records",
    "ai_usage_records",
    "remediation_plans",
    "learning_events",
    "assessment_attempts",
    "ai_conversations",
    "ai_jobs",
    "courses",
    "invitations",
    "tenants",
    "users",
)


@pytest.fixture(autouse=True)
async def reset_state_between_tests(request: pytest.FixtureRequest) -> AsyncGenerator[None]:
    node_id = request.node.nodeid.replace("\\", "/")
    if any(
        skip in node_id
        for skip in (
            "tests/unit",
            "tests/ai_evaluation",
            "tests/integration/test_migrations_and_schema.py",
            "test_openapi_contract_and_required_paths",
        )
    ):
        yield
        return
    rate_limiter.reset()
    await dispose_engine()
    settings = get_settings()
    su_engine = create_async_engine(
        settings.superuser_database_url, echo=False, poolclass=NullPool
    )
    async with su_engine.connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _RESET_LOCK_KEY})
        try:
            async with su_engine.begin() as conn:
                for table_name in _RESET_TABLES:
                    await conn.execute(text(f"DELETE FROM {table_name}"))
            yield
        finally:
            await dispose_engine()
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": _RESET_LOCK_KEY}
            )
            await lock_conn.commit()
    await su_engine.dispose()


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def app_role_engine() -> AsyncGenerator[AsyncEngine]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def migrator_role_engine() -> AsyncGenerator[AsyncEngine]:
    settings = get_settings()
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()

