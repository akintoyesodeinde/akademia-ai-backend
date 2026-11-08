from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx_var
from app.modules.audit.models import AuditEvent


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        tenant_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str,
        actor_user_id: UUID | None = None,
        actor_membership_id: UUID | None = None,
        ip_address: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_membership_id=actor_membership_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            ip_address=ip_address,
            request_id=request_id_ctx_var.get(),
            metadata_json=metadata_json or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self,
        *,
        tenant_id: UUID,
        page: int = 1,
        page_size: int = 20,
        action_filter: str | None = None,
    ) -> tuple[list[AuditEvent], int]:
        base = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        count_q = select(func.count(AuditEvent.id)).where(AuditEvent.tenant_id == tenant_id)
        if action_filter:
            base = base.where(AuditEvent.action == action_filter)
            count_q = count_q.where(AuditEvent.action == action_filter)
        total = int((await self.session.execute(count_q)).scalar_one() or 0)
        stmt = (
            base.order_by(AuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
