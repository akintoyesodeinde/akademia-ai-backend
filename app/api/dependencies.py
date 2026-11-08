from uuid import UUID

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import ROLE_PERMISSION_MAP, PrincipalContext
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.db.tenant_context import clear_tenant_context, set_tenant_context
from app.modules.identity.models import User
from app.modules.memberships.models import MembershipRole, Role, TenantMembership
from app.modules.tenants.models import Tenant
from app.shared.errors import AuthenticationError, AuthorizationError

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    session: AsyncSession = Depends(get_db_session),
) -> PrincipalContext:
    """Authenticate JWT access token and verify active database membership before establishing RLS context.
    Never trusts an unverified X-Tenant-ID header or browser field without verifying DB membership.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer authentication token.")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(str(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired authentication token.") from exc

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or user.status != "active":
        raise AuthenticationError("Authenticated user account is not active.")

    # Determine requested tenant_id (from X-Tenant-ID if supplied, or JWT 'tid' claim)
    target_tenant_id: UUID | None = None
    if x_tenant_id:
        try:
            target_tenant_id = UUID(x_tenant_id.strip())
        except ValueError as exc:
            raise AuthorizationError("Malformed X-Tenant-ID header.") from exc
    elif payload.get("tid"):
        try:
            target_tenant_id = UUID(str(payload["tid"]))
        except ValueError:
            target_tenant_id = None

    if target_tenant_id is None:
        await clear_tenant_context(session)
        return PrincipalContext(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_platform_admin=user.is_platform_admin,
        )

    # Verify tenant is active
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == target_tenant_id))
    ).scalar_one_or_none()
    if tenant is None or tenant.status != "active":
        await clear_tenant_context(session)
        raise AuthorizationError("Target tenant does not exist or is suspended.")

    # Temporarily set transaction-local tenant context to query tenant_memberships under RLS
    await set_tenant_context(session, target_tenant_id)
    membership = (
        await session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == target_tenant_id,
                TenantMembership.user_id == user.id,
                TenantMembership.status == "active",
            )
        )
    ).scalar_one_or_none()

    if membership is None:
        # Immediately clear tenant context and fail closed!
        await clear_tenant_context(session)
        raise AuthorizationError(
            "Access denied: User does not hold an active membership in the requested tenant."
        )

    role_stmt = (
        select(Role.code)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(
            MembershipRole.tenant_id == target_tenant_id,
            MembershipRole.membership_id == membership.id,
        )
    )
    role_codes = list((await session.execute(role_stmt)).scalars().all())
    perms: set[str] = set()
    for r in role_codes:
        perms.update(ROLE_PERMISSION_MAP.get(r, set()))

    return PrincipalContext(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=user.is_platform_admin,
        tenant_id=target_tenant_id,
        membership_id=membership.id,
        roles=role_codes,
        permissions=perms,
    )
