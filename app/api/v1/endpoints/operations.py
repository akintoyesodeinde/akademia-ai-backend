from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evaluation.service import AIEvaluationHarness
from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext, TenantRole
from app.core.observability import metrics_registry
from app.db.session import get_db_session
from app.db.tenant_context import set_tenant_context
from app.modules.ai_tutor.models import AIEvaluationRecord, AIUsageRecord
from app.modules.audit.service import AuditService
from app.modules.subscriptions.service import SubscriptionService
from app.modules.tenants.models import Tenant
from app.shared.errors import NotFoundError
from app.shared.schemas import APIModel, PaginatedResponse

router = APIRouter(tags=["SaaS Billing, Audit & Platform Operations"])


class BillingPlanResponse(APIModel):
    subscription_id: UUID
    tenant_id: UUID
    plan_code: str
    plan_name: str
    status: str
    monthly_price_usd: float
    max_active_users: int
    max_published_courses: int
    max_ai_requests_per_month: int
    max_storage_bytes: int
    max_monthly_tokens: int
    current_period_start: datetime
    current_period_end: datetime


class BillingUsageResponse(APIModel):
    tenant_id: UUID
    period_month: str
    active_users_count: int
    published_courses_count: int
    ai_requests_count: int
    storage_bytes_used: int
    monthly_tokens_used: int
    estimated_ai_cost_usd: float
    recent_ai_operations: list[dict[str, Any]] = Field(default_factory=list)


class BillingEventInput(BaseModel):
    external_event_id: str = Field(min_length=3, max_length=128)
    event_type: str = Field(min_length=3, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditEventView(APIModel):
    id: UUID
    tenant_id: UUID
    actor_user_id: UUID | None = None
    actor_membership_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str
    ip_address: str | None = None
    request_id: str | None = None
    metadata_json: dict[str, Any]
    created_at: datetime


class PlatformTenantStatusInput(BaseModel):
    status: str = Field(pattern=r"^(active|suspended|closed)$")
    reason: str = Field(min_length=3, max_length=500)


@router.get("/billing/plan", response_model=BillingPlanResponse)
async def get_billing_plan(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BillingPlanResponse:
    tenant_id = principal.require_tenant()
    svc = SubscriptionService(session)
    sub, plan = await svc.ensure_tenant_subscription(tenant_id)
    return BillingPlanResponse(
        subscription_id=sub.id,
        tenant_id=sub.tenant_id,
        plan_code=plan.code,
        plan_name=plan.name,
        status=sub.status,
        monthly_price_usd=plan.monthly_price_usd,
        max_active_users=plan.max_active_users,
        max_published_courses=plan.max_published_courses,
        max_ai_requests_per_month=plan.max_ai_requests_per_month,
        max_storage_bytes=plan.max_storage_bytes,
        max_monthly_tokens=plan.max_monthly_tokens,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
    )


@router.get("/billing/usage", response_model=BillingUsageResponse)
async def get_billing_usage(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BillingUsageResponse:
    tenant_id = principal.require_tenant()
    svc = SubscriptionService(session)
    usage = await svc.get_or_create_usage_record(tenant_id)

    ai_rows = list(
        (
            await session.execute(
                select(AIUsageRecord)
                .where(AIUsageRecord.tenant_id == tenant_id)
                .order_by(AIUsageRecord.created_at.desc())
                .limit(15)
            )
        )
        .scalars()
        .all()
    )
    return BillingUsageResponse(
        tenant_id=usage.tenant_id,
        period_month=usage.period_month,
        active_users_count=usage.active_users_count,
        published_courses_count=usage.published_courses_count,
        ai_requests_count=usage.ai_requests_count,
        storage_bytes_used=usage.storage_bytes_used,
        monthly_tokens_used=usage.monthly_tokens_used,
        estimated_ai_cost_usd=usage.estimated_ai_cost_usd,
        recent_ai_operations=[
            {
                "id": str(r.id),
                "operation_type": r.operation_type,
                "provider_name": r.provider_name,
                "model_id": r.model_id,
                "total_tokens": r.total_tokens,
                "estimated_cost_usd": r.estimated_cost_usd,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in ai_rows
        ],
    )


@router.post("/billing/events")
async def record_billing_event(
    req: BillingEventInput,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    tenant_id = principal.require_tenant()
    principal.require_any_role(TenantRole.OWNER.value, TenantRole.ADMIN.value)
    svc = SubscriptionService(session)
    ev, created = await svc.record_idempotent_billing_event(
        tenant_id=tenant_id,
        external_event_id=req.external_event_id,
        event_type=req.event_type,
        payload=req.payload,
    )
    return {
        "event_id": str(ev.id),
        "external_event_id": ev.external_event_id,
        "idempotent_replay": not created,
    }


@router.get(
    "/tenant-admin/audit-events",
    response_model=PaginatedResponse[AuditEventView],
)
async def list_tenant_audit_events(
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[AuditEventView]:
    tenant_id = principal.require_tenant()
    principal.require_any_role(TenantRole.OWNER.value, TenantRole.ADMIN.value)

    audit_svc = AuditService(session)
    items, total = await audit_svc.list_events(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        action_filter=action,
    )
    return PaginatedResponse[AuditEventView](
        items=[
            AuditEventView(
                id=ev.id,
                tenant_id=ev.tenant_id,
                actor_user_id=ev.actor_user_id,
                actor_membership_id=ev.actor_membership_id,
                action=ev.action,
                resource_type=ev.resource_type,
                resource_id=ev.resource_id,
                ip_address=ev.ip_address,
                request_id=ev.request_id,
                metadata_json=ev.metadata_json,
                created_at=ev.created_at,
            )
            for ev in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/platform/health")
async def platform_health(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Public platform health check (does not expose sensitive internal details)."""
    db_ok = False
    try:
        val = (await session.execute(text("SELECT 1"))).scalar_one()
        db_ok = val == 1
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "akademia-ai-backend",
        "database": "connected" if db_ok else "unavailable",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/platform/tenants")
async def list_all_tenants_for_platform_operator(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Privileged platform-operator endpoint (separate from tenant roles)."""
    principal.require_platform_admin()
    rows = list(
        (await session.execute(select(Tenant).order_by(Tenant.created_at.desc())))
        .scalars()
        .all()
    )
    return {
        "tenants": [
            {
                "id": str(t.id),
                "name": t.name,
                "slug": t.slug,
                "institution_type": t.institution_type,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ],
        "telemetry": metrics_registry.snapshot(),
    }


@router.patch("/platform/tenants/{tenant_id}/status")
async def update_tenant_status_for_platform_operator(
    tenant_id: UUID,
    req: PlatformTenantStatusInput,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    principal.require_platform_admin()
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise NotFoundError("Tenant not found.")

    prev_status = tenant.status
    tenant.status = req.status
    await set_tenant_context(session, tenant.id)
    audit_svc = AuditService(session)
    await audit_svc.record(
        tenant_id=tenant.id,
        actor_user_id=principal.user_id,
        action="platform.tenant_status_changed",
        resource_type="tenant",
        resource_id=str(tenant.id),
        metadata_json={
            "previous_status": prev_status,
            "new_status": req.status,
            "reason": req.reason,
        },
    )
    await session.flush()
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "previous_status": prev_status,
        "status": tenant.status,
    }


@router.post("/platform/ai-evaluations/run")
async def run_platform_ai_evaluation(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    principal.require_platform_admin()
    harness = AIEvaluationHarness()
    report = await harness.run_suite()
    record = AIEvaluationRecord(
        dataset_version=report["dataset_version"],
        prompt_version=report["prompt_version"],
        model_id=report["model_id"],
        sample_size=report["sample_size"],
        retrieval_recall_at_5=report["retrieval_recall_at_5"],
        citation_authorization_rate=report["citation_authorization_rate"],
        groundedness_score=report["groundedness_score"],
        answer_relevance_score=report["answer_relevance_score"],
        unauthorized_leak_count=report["unauthorized_leak_count"],
        structured_validity_rate=report["structured_validity_rate"],
        metrics_detail={"cases": report["cases"]},
    )
    session.add(record)
    await session.flush()
    return {"evaluation_id": str(record.id), **report}
