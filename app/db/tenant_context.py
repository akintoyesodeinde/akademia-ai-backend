from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import tenant_id_log_ctx_var


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Establish transaction-local tenant context (`SET LOCAL app.tenant_id = ...`).
    This setting automatically resets when the PostgreSQL transaction ends.
    """
    tid_str = str(tenant_id)
    tenant_id_log_ctx_var.set(tid_str)
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tid_str},
    )


async def clear_tenant_context(session: AsyncSession) -> None:
    """Explicitly clear transaction-local tenant context within the active transaction."""
    tenant_id_log_ctx_var.set("-")
    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))


async def get_current_db_tenant_context(session: AsyncSession) -> str | None:
    """Read back the active PostgreSQL transaction-local `app.tenant_id` setting."""
    result = await session.execute(
        text("SELECT NULLIF(current_setting('app.tenant_id', true), '')")
    )
    return result.scalar_one_or_none()
