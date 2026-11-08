from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.db.session import get_db_session
from app.modules.tenants.schemas import (
    AcceptInvitationRequest,
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
from app.modules.tenants.service import TenantService

router = APIRouter(tags=["Tenants & Memberships"])


@router.post(
    "/tenants",
    response_model=TenantProvisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    req: CreateTenantRequest,
    request: Request,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantProvisionResponse:
    svc = TenantService(session)
    return await svc.provision_tenant(
        principal=principal,
        req=req,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/tenants/current", response_model=TenantResponse)
async def get_current_tenant(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    tenant_id = principal.require_tenant()
    svc = TenantService(session)
    return await svc.get_current_tenant(tenant_id)


@router.patch("/tenants/current", response_model=TenantResponse)
async def update_current_tenant(
    req: UpdateTenantRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    svc = TenantService(session)
    return await svc.update_current_tenant(principal=principal, req=req)


@router.get("/tenants/current/members", response_model=list[MemberResponse])
async def list_current_tenant_members(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemberResponse]:
    tenant_id = principal.require_tenant()
    svc = TenantService(session)
    return await svc.list_members(tenant_id)


@router.post(
    "/tenants/current/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    req: CreateInvitationRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> InvitationResponse:
    svc = TenantService(session)
    return await svc.create_invitation(principal=principal, req=req)


@router.post("/invitations/accept", response_model=MemberResponse)
async def accept_invitation(
    req: AcceptInvitationRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    svc = TenantService(session)
    return await svc.accept_invitation(principal=principal, raw_token=req.token)


@router.patch(
    "/tenants/current/members/{membership_id}",
    response_model=MemberResponse,
)
async def update_tenant_member(
    membership_id: UUID,
    req: UpdateMembershipRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    svc = TenantService(session)
    return await svc.update_membership(
        principal=principal, membership_id=membership_id, req=req
    )


@router.get("/tenants/current/roles", response_model=list[RoleResponse])
async def list_tenant_roles(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[RoleResponse]:
    principal.require_tenant()
    svc = TenantService(session)
    return await svc.list_roles()


@router.post(
    "/tenants/current/cohorts",
    response_model=CohortResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cohort(
    req: CreateCohortRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CohortResponse:
    svc = TenantService(session)
    return await svc.create_cohort(principal=principal, req=req)


@router.get("/tenants/current/cohorts", response_model=list[CohortResponse])
async def list_cohorts(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[CohortResponse]:
    tenant_id = principal.require_tenant()
    svc = TenantService(session)
    return await svc.list_cohorts(tenant_id)


@router.post("/tenants/current/cohorts/{cohort_id}/members")
async def add_cohort_member(
    cohort_id: UUID,
    req: AddCohortMemberRequest,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    svc = TenantService(session)
    return await svc.add_cohort_member(
        principal=principal, cohort_id=cohort_id, req=req
    )
