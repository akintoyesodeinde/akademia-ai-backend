from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_tutor.models import AIUsageRecord
from app.modules.courses.models import Course
from app.modules.memberships.models import TenantMembership
from app.modules.subscriptions.models import (
    BillingEvent,
    IdempotencyRecord,
    SubscriptionPlan,
    TenantSubscription,
    TenantUsageRecord,
)
from app.shared.errors import QuotaExceededError


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def current_period_month() -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    async def ensure_tenant_subscription(
        self, tenant_id: UUID, plan_code: str = "starter"
    ) -> tuple[TenantSubscription, SubscriptionPlan]:
        sub = (
            await self.session.execute(
                select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()

        if sub is not None:
            existing_plan = (
                await self.session.execute(
                    select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
                )
            ).scalar_one()
            return sub, existing_plan

        plan: SubscriptionPlan | None = (
            await self.session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.code == plan_code)
            )
        ).scalar_one_or_none()

        if plan is None:
            plan = SubscriptionPlan(
                code="starter",
                name="Academic Starter",
                monthly_price_usd=0.0,
                max_active_users=50,
                max_published_courses=10,
                max_ai_requests_per_month=500,
                max_storage_bytes=500 * 1024 * 1024,
                max_monthly_tokens=500000,
                is_active=True,
            )
            self.session.add(plan)
            await self.session.flush()

        now = datetime.now(UTC)
        sub = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status="active",
            billing_provider="invoiced_contract",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        self.session.add(sub)
        await self.session.flush()
        return sub, plan

    async def get_or_create_usage_record(self, tenant_id: UUID) -> TenantUsageRecord:
        period = self.current_period_month()
        usage = (
            await self.session.execute(
                select(TenantUsageRecord).where(
                    TenantUsageRecord.tenant_id == tenant_id,
                    TenantUsageRecord.period_month == period,
                )
            )
        ).scalar_one_or_none()
        if usage is None:
            active_users = int(
                (
                    await self.session.execute(
                        select(func.count(TenantMembership.id)).where(
                            TenantMembership.tenant_id == tenant_id,
                            TenantMembership.status == "active",
                        )
                    )
                ).scalar_one()
                or 0
            )
            published_courses = int(
                (
                    await self.session.execute(
                        select(func.count(Course.id)).where(
                            Course.tenant_id == tenant_id,
                            Course.status == "published",
                        )
                    )
                ).scalar_one()
                or 0
            )
            usage = TenantUsageRecord(
                tenant_id=tenant_id,
                period_month=period,
                active_users_count=active_users,
                published_courses_count=published_courses,
                ai_requests_count=0,
                storage_bytes_used=0,
                monthly_tokens_used=0,
                estimated_ai_cost_usd=0.0,
            )
            self.session.add(usage)
            await self.session.flush()
        return usage

    async def check_and_increment_course_publish_quota(self, tenant_id: UUID) -> None:
        _, plan = await self.ensure_tenant_subscription(tenant_id)
        usage = await self.get_or_create_usage_record(tenant_id)
        published_courses = int(
            (
                await self.session.execute(
                    select(func.count(Course.id)).where(
                        Course.tenant_id == tenant_id,
                        Course.status == "published",
                    )
                )
            ).scalar_one()
            or 0
        )
        if published_courses >= plan.max_published_courses:
            raise QuotaExceededError(
                f"Tenant plan '{plan.code}' limit of {plan.max_published_courses} published courses reached."
            )
        usage.published_courses_count = published_courses + 1
        await self.session.flush()

    async def check_and_increment_storage_quota(
        self, tenant_id: UUID, additional_bytes: int
    ) -> None:
        _, plan = await self.ensure_tenant_subscription(tenant_id)
        usage = await self.get_or_create_usage_record(tenant_id)
        if usage.storage_bytes_used + additional_bytes > plan.max_storage_bytes:
            raise QuotaExceededError(
                f"Document upload exceeds tenant storage quota ({plan.max_storage_bytes} bytes)."
            )
        usage.storage_bytes_used += additional_bytes
        await self.session.flush()

    async def check_ai_quota(self, tenant_id: UUID) -> None:
        _, plan = await self.ensure_tenant_subscription(tenant_id)
        usage = await self.get_or_create_usage_record(tenant_id)
        if usage.ai_requests_count >= plan.max_ai_requests_per_month:
            raise QuotaExceededError(
                f"Monthly AI request quota ({plan.max_ai_requests_per_month}) exceeded for plan '{plan.code}'."
            )
        if usage.monthly_tokens_used >= plan.max_monthly_tokens:
            raise QuotaExceededError(
                f"Monthly AI token quota ({plan.max_monthly_tokens}) exceeded for plan '{plan.code}'."
            )

    async def record_ai_usage(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID | None,
        operation_type: str,
        provider_name: str,
        model_id: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> AIUsageRecord:
        settings = get_settings()
        total_tokens = input_tokens + output_tokens
        if operation_type == "document_embedding":
            cost = round(
                (total_tokens / 1000.0) * settings.ai_embedding_cost_per_1k_tokens_usd, 6
            )
        else:
            cost = round(
                (input_tokens / 1000.0) * settings.ai_input_cost_per_1k_tokens_usd
                + (output_tokens / 1000.0) * settings.ai_output_cost_per_1k_tokens_usd,
                6,
            )

        rec = AIUsageRecord(
            tenant_id=tenant_id,
            membership_id=membership_id,
            operation_type=operation_type,
            provider_name=provider_name,
            model_id=model_id,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency_ms,
        )
        self.session.add(rec)
        usage = await self.get_or_create_usage_record(tenant_id)
        usage.ai_requests_count += 1
        usage.monthly_tokens_used += total_tokens
        usage.estimated_ai_cost_usd = round(usage.estimated_ai_cost_usd + cost, 6)
        await self.session.flush()
        return rec

    async def record_idempotent_billing_event(
        self,
        *,
        tenant_id: UUID,
        external_event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> tuple[BillingEvent, bool]:
        existing = (
            await self.session.execute(
                select(BillingEvent).where(
                    BillingEvent.tenant_id == tenant_id,
                    BillingEvent.external_event_id == external_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

        ev = BillingEvent(
            tenant_id=tenant_id,
            external_event_id=external_event_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(ev)
        if event_type == "plan.upgraded" and "plan_code" in payload:
            target_plan = (
                await self.session.execute(
                    select(SubscriptionPlan).where(
                        SubscriptionPlan.code == str(payload["plan_code"])
                    )
                )
            ).scalar_one_or_none()
            if target_plan is not None:
                sub, _ = await self.ensure_tenant_subscription(tenant_id)
                sub.plan_id = target_plan.id
        await self.session.flush()
        return ev, True

    async def check_idempotency(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
        operation_scope: str,
        request_hash: str,
    ) -> IdempotencyRecord | None:
        return (
            await self.session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == tenant_id,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                    IdempotencyRecord.operation_scope == operation_scope,
                )
            )
        ).scalar_one_or_none()

    async def save_idempotency(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
        operation_scope: str,
        request_hash: str,
        response_status_code: int,
        response_body: dict[str, Any],
    ) -> IdempotencyRecord:
        rec = IdempotencyRecord(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            operation_scope=operation_scope,
            request_hash=request_hash,
            response_status_code=response_status_code,
            response_body=response_body,
        )
        self.session.add(rec)
        await self.session.flush()
        return rec
