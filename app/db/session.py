from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.tenant_context import clear_tenant_context, set_tenant_context

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Provide a transactional database session that always starts with cleared tenant context."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await clear_tenant_context(session)
        yield session


@asynccontextmanager
async def tenant_scoped_session(tenant_id: UUID) -> AsyncGenerator[AsyncSession]:
    """Provide an explicit transaction-scoped session bound to a verified tenant_id."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        yield session
