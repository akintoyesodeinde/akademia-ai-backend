from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import ROLE_PERMISSION_MAP, PrincipalContext, TenantRole
from app.core.security import create_access_token, generate_secure_token, hash_token
from app.db.tenant_context import set_tenant_context
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.memberships.models import (
    Invitation,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    TenantMembership,
)
from app.modules.subscriptions.service import SubscriptionService
from app.modules.tenants.models import (
    Cohort,
    CohortMembership,
    Tenant,
    TenantSettings,
)
from app.modules.tenants.schemas import (
    AddCohortMemberRequest,
    CohortResponse,
    CreateCohortRequest,
    CreateInvitationRequest,
    CreateTenantRequest,
    InvitationResponse,
    MemberResponse,
    RoleResponse,
    TenantProvisionResponse,
    TenantResponse,
    UpdateMembershipRequest,
    UpdateTenantRequest,
)
from app.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationAppError,
)


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)
        self.subscriptions = SubscriptionService(session)

    async def ensure_role(self, role_code: str) -> Role:
        role = (
            await self.session.execute(select(Role).where(Role.code == role_code))
        ).scalar_one_or_none()
        if role is None:
            role = Role(
                code=role_code,
                name=role_code.capitalize(),
                description=f"Standard tenant role: {role_code}",
            )
            self.session.add(role)
            await self.session.flush()
        return role

    async def provision_tenant(
        self,
        *,
        principal: PrincipalContext,
        req: CreateTenantRequest,
        ip_address: str | None = None,
    ) -> TenantProvisionResponse:
        slug = req.slug.strip().lower()
        existing = (
            await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Tenant slug '{slug}' is already in use.")

        tenant = Tenant(
            name=req.name.strip(),
            slug=slug,
            institution_type=req.institution_type,
            status="active",
            primary_contact_email=req.primary_contact_email or principal.email,
        )
        self.session.add(tenant)
        await self.session.flush()

        # Establish transaction-local tenant context BEFORE inserting tenant-owned rows
        await set_tenant_context(self.session, tenant.id)

        settings = TenantSettings(
            tenant_id=tenant.id,
            academic_integrity_policy="strict_during_assessment",
            ai_tutor_enabled=True,
            ai_practice_enabled=True,
            default_locale="en-US",
            branding_config={"primaryColor": "#1e40af"},
            feature_flags={},
        )
        self.session.add(settings)

        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=principal.user_id,
            status="active",
            title="Institution Owner",
            joined_at=datetime.now(UTC),
        )
        self.session.add(membership)
        await self.session.flush()

        owner_role = await self.ensure_role(TenantRole.OWNER.value)
        mem_role = MembershipRole(
            tenant_id=tenant.id,
            membership_id=membership.id,
            role_id=owner_role.id,
        )
        self.session.add(mem_role)

        await self.subscriptions.ensure_tenant_subscription(tenant.id, plan_code="starter")
        await self.subscriptions.get_or_create_usage_record(tenant.id)

        await self.audit.record(
            tenant_id=tenant.id,
            actor_user_id=principal.user_id,
            actor_membership_id=membership.id,
            action="tenant.provisioned",
            resource_type="tenant",
            resource_id=str(tenant.id),
            ip_address=ip_address,
            metadata_json={"slug": tenant.slug, "institution_type": tenant.institution_type},
        )

        access_token = create_access_token(
            user_id=principal.user_id,
            tenant_id=tenant.id,
            membership_id=membership.id,
            roles=[TenantRole.OWNER.value],
            is_platform_admin=principal.is_platform_admin,
        )

        return TenantProvisionResponse(
            tenant=TenantResponse(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                institution_type=tenant.institution_type,
                status=tenant.status,
                primary_contact_email=tenant.primary_contact_email,
                academic_integrity_policy=settings.academic_integrity_policy,
                ai_tutor_enabled=settings.ai_tutor_enabled,
                ai_practice_enabled=settings.ai_practice_enabled,
                branding_config=settings.branding_config,
                created_at=tenant.created_at,
            ),
            membership_id=membership.id,
            assigned_roles=[TenantRole.OWNER.value],
            access_token=access_token,
        )

    async def get_current_tenant(self, tenant_id: UUID) -> TenantResponse:
        tenant = (
            await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        settings = (
            await self.session.execute(
                select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            institution_type=tenant.institution_type,
            status=tenant.status,
            primary_contact_email=tenant.primary_contact_email,
            academic_integrity_policy=(
                settings.academic_integrity_policy
                if settings
                else "strict_during_assessment"
            ),
            ai_tutor_enabled=settings.ai_tutor_enabled if settings else True,
            ai_practice_enabled=settings.ai_practice_enabled if settings else True,
            branding_config=settings.branding_config if settings else {},
            created_at=tenant.created_at,
        )

    async def update_current_tenant(
        self,
        *,
        principal: PrincipalContext,
        req: UpdateTenantRequest,
    ) -> TenantResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(TenantRole.OWNER.value, TenantRole.ADMIN.value)

        tenant = (
            await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if tenant is None:
            raise NotFoundError("Tenant not found.")

        settings = (
            await self.session.execute(
                select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if settings is None:
            settings = TenantSettings(tenant_id=tenant_id)
            self.session.add(settings)

        if req.name is not None:
            tenant.name = req.name.strip()
        if req.primary_contact_email is not None:
            tenant.primary_contact_email = req.primary_contact_email
        if req.academic_integrity_policy is not None:
            settings.academic_integrity_policy = req.academic_integrity_policy
        if req.ai_tutor_enabled is not None:
            settings.ai_tutor_enabled = req.ai_tutor_enabled
        if req.ai_practice_enabled is not None:
            settings.ai_practice_enabled = req.ai_practice_enabled
        if req.branding_config is not None:
            settings.branding_config = req.branding_config

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="tenant.updated",
            resource_type="tenant",
            resource_id=str(tenant_id),
            metadata_json=req.model_dump(exclude_none=True),
        )
        await self.session.flush()
        return await self.get_current_tenant(tenant_id)

    async def list_members(self, tenant_id: UUID) -> list[MemberResponse]:
        stmt = (
            select(TenantMembership, User)
            .join(User, User.id == TenantMembership.user_id)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        members: list[MemberResponse] = []
        for mem, usr in rows:
            role_stmt = (
                select(Role.code)
                .join(MembershipRole, MembershipRole.role_id == Role.id)
                .where(
                    MembershipRole.tenant_id == tenant_id,
                    MembershipRole.membership_id == mem.id,
                )
            )
            roles = list((await self.session.execute(role_stmt)).scalars().all())
            members.append(
                MemberResponse(
                    membership_id=mem.id,
                    tenant_id=mem.tenant_id,
                    user_id=usr.id,
                    email=usr.email,
                    full_name=usr.full_name,
                    status=mem.status,
                    title=mem.title,
                    roles=roles,
                    joined_at=mem.joined_at,
                )
            )
        return members

    async def create_invitation(
        self,
        *,
        principal: PrincipalContext,
        req: CreateInvitationRequest,
    ) -> InvitationResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(TenantRole.OWNER.value, TenantRole.ADMIN.value)

        raw_token = generate_secure_token(24)
        inv = Invitation(
            tenant_id=tenant_id,
            email=req.email.strip().lower(),
            role_code=req.role_code,
            token_hash=hash_token(raw_token),
            status="pending",
            invited_by_membership_id=principal.membership_id,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        self.session.add(inv)
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="invitation.created",
            resource_type="invitation",
            resource_id=str(inv.id),
            metadata_json={"email": inv.email, "role_code": inv.role_code},
        )
        await self.session.flush()
        return InvitationResponse(
            id=inv.id,
            tenant_id=inv.tenant_id,
            email=inv.email,
            role_code=inv.role_code,
            status=inv.status,
            expires_at=inv.expires_at,
            invitation_token=raw_token,
        )

    async def accept_invitation(
        self,
        *,
        principal: PrincipalContext,
        raw_token: str,
    ) -> MemberResponse:
        tok_hash = hash_token(raw_token)
        resolved_tenant_id = (
            await self.session.execute(
                text("SELECT resolve_invitation_tenant_bootstrap(:th)"),
                {"th": tok_hash},
            )
        ).scalar_one_or_none()

        if resolved_tenant_id is None:
            raise NotFoundError("Invitation token is invalid or no longer pending.")

        await set_tenant_context(self.session, resolved_tenant_id)

        inv = (
            await self.session.execute(
                select(Invitation).where(
                    Invitation.tenant_id == resolved_tenant_id,
                    Invitation.token_hash == tok_hash,
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if inv is None or inv.status != "pending":
            raise ValidationAppError("Invitation is not active.")
        if inv.expires_at <= now:
            inv.status = "expired"
            await self.session.flush()
            raise ValidationAppError("Invitation has expired.")
        if inv.email.lower() != principal.email.lower():
            raise AuthorizationError(
                "Invitation email does not match the authenticated user's email address."
            )

        existing_mem = (
            await self.session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == resolved_tenant_id,
                    TenantMembership.user_id == principal.user_id,
                )
            )
        ).scalar_one_or_none()

        if existing_mem is None:
            existing_mem = TenantMembership(
                tenant_id=resolved_tenant_id,
                user_id=principal.user_id,
                status="active",
                title=inv.role_code.capitalize(),
                joined_at=now,
            )
            self.session.add(existing_mem)
            await self.session.flush()
        else:
            existing_mem.status = "active"

        role = await self.ensure_role(inv.role_code)
        existing_role_link = (
            await self.session.execute(
                select(MembershipRole).where(
                    MembershipRole.tenant_id == resolved_tenant_id,
                    MembershipRole.membership_id == existing_mem.id,
                    MembershipRole.role_id == role.id,
                )
            )
        ).scalar_one_or_none()
        if existing_role_link is None:
            self.session.add(
                MembershipRole(
                    tenant_id=resolved_tenant_id,
                    membership_id=existing_mem.id,
                    role_id=role.id,
                )
            )

        inv.status = "accepted"
        inv.accepted_at = now

        await self.audit.record(
            tenant_id=resolved_tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=existing_mem.id,
            action="invitation.accepted",
            resource_type="membership",
            resource_id=str(existing_mem.id),
            metadata_json={"role_code": inv.role_code},
        )
        await self.session.flush()

        role_stmt = (
            select(Role.code)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == resolved_tenant_id,
                MembershipRole.membership_id == existing_mem.id,
            )
        )
        roles = list((await self.session.execute(role_stmt)).scalars().all())
        return MemberResponse(
            membership_id=existing_mem.id,
            tenant_id=existing_mem.tenant_id,
            user_id=principal.user_id,
            email=principal.email,
            full_name=principal.full_name,
            status=existing_mem.status,
            title=existing_mem.title,
            roles=roles,
            joined_at=existing_mem.joined_at,
        )

    async def update_membership(
        self,
        *,
        principal: PrincipalContext,
        membership_id: UUID,
        req: UpdateMembershipRequest,
    ) -> MemberResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(TenantRole.OWNER.value, TenantRole.ADMIN.value)

        mem = (
            await self.session.execute(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.id == membership_id,
                )
            )
        ).scalar_one_or_none()
        if mem is None:
            raise NotFoundError("Membership not found in current tenant.")

        # Prevent non-owner from granting owner role or escalating their own role
        if req.roles is not None:
            if membership_id == principal.membership_id and not principal.has_role(
                TenantRole.OWNER.value
            ):
                raise AuthorizationError("Users cannot escalate their own tenant roles.")
            if TenantRole.OWNER.value in req.roles and not principal.has_role(
                TenantRole.OWNER.value
            ):
                raise AuthorizationError("Only a tenant owner can assign the owner role.")

            existing_links = (
                await self.session.execute(
                    select(MembershipRole).where(
                        MembershipRole.tenant_id == tenant_id,
                        MembershipRole.membership_id == mem.id,
                    )
                )
            ).scalars().all()
            for link in existing_links:
                await self.session.delete(link)
            await self.session.flush()

            for rcode in req.roles:
                role = await self.ensure_role(rcode)
                self.session.add(
                    MembershipRole(
                        tenant_id=tenant_id,
                        membership_id=mem.id,
                        role_id=role.id,
                    )
                )

        if req.status is not None:
            mem.status = req.status
        if req.title is not None:
            mem.title = req.title

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=principal.user_id,
            actor_membership_id=principal.membership_id,
            action="membership.updated",
            resource_type="membership",
            resource_id=str(mem.id),
            metadata_json=req.model_dump(exclude_none=True),
        )
        await self.session.flush()

        usr = (
            await self.session.execute(select(User).where(User.id == mem.user_id))
        ).scalar_one()
        role_stmt = (
            select(Role.code)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == tenant_id,
                MembershipRole.membership_id == mem.id,
            )
        )
        roles = list((await self.session.execute(role_stmt)).scalars().all())
        return MemberResponse(
            membership_id=mem.id,
            tenant_id=mem.tenant_id,
            user_id=usr.id,
            email=usr.email,
            full_name=usr.full_name,
            status=mem.status,
            title=mem.title,
            roles=roles,
            joined_at=mem.joined_at,
        )

    async def list_roles(self) -> list[RoleResponse]:
        roles = list(
            (await self.session.execute(select(Role).order_by(Role.code.asc()))).scalars().all()
        )
        result: list[RoleResponse] = []
        for r in roles:
            p_stmt = (
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == r.id)
                .order_by(Permission.code.asc())
            )
            perms = list((await self.session.execute(p_stmt)).scalars().all())
            if not perms:
                perms = sorted(ROLE_PERMISSION_MAP.get(r.code, set()))
            result.append(
                RoleResponse(
                    id=r.id,
                    code=r.code,
                    name=r.name,
                    description=r.description,
                    permissions=perms,
                )
            )
        return result

    async def create_cohort(
        self,
        *,
        principal: PrincipalContext,
        req: CreateCohortRequest,
    ) -> CohortResponse:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        cohort = Cohort(
            tenant_id=tenant_id,
            name=req.name.strip(),
            code=req.code.strip().upper(),
            description=req.description,
            status="active",
        )
        self.session.add(cohort)
        await self.session.flush()
        return CohortResponse(
            id=cohort.id,
            tenant_id=cohort.tenant_id,
            name=cohort.name,
            code=cohort.code,
            description=cohort.description,
            status=cohort.status,
            created_at=cohort.created_at,
        )

    async def list_cohorts(self, tenant_id: UUID) -> list[CohortResponse]:
        rows = (
            await self.session.execute(
                select(Cohort)
                .where(Cohort.tenant_id == tenant_id)
                .order_by(Cohort.created_at.desc())
            )
        ).scalars().all()
        return [
            CohortResponse(
                id=c.id,
                tenant_id=c.tenant_id,
                name=c.name,
                code=c.code,
                description=c.description,
                status=c.status,
                created_at=c.created_at,
            )
            for c in rows
        ]

    async def add_cohort_member(
        self,
        *,
        principal: PrincipalContext,
        cohort_id: UUID,
        req: AddCohortMemberRequest,
    ) -> dict[str, str]:
        tenant_id = principal.require_tenant()
        principal.require_any_role(
            TenantRole.OWNER.value, TenantRole.ADMIN.value, TenantRole.INSTRUCTOR.value
        )
        cm = CohortMembership(
            tenant_id=tenant_id,
            cohort_id=cohort_id,
            membership_id=req.membership_id,
            role_in_cohort=req.role_in_cohort,
        )
        self.session.add(cm)
        await self.session.flush()
        return {"status": "added", "cohort_id": str(cohort_id), "membership_id": str(req.membership_id)}
