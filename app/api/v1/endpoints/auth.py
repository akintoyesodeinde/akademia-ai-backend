from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.core.authorization import PrincipalContext
from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    ActionStatusResponse,
    AuthProfileResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SwitchTenantRequest,
    TokenSessionResponse,
    VerifyEmailRequest,
)
from app.modules.identity.service import IdentityService
from app.shared.rate_limit import rate_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_session_cookies(response: Response, token_res: TokenSessionResponse) -> None:
    settings = get_settings()
    max_age = settings.refresh_token_expire_days * 86400
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token_res.refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=max_age,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token_res.csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=max_age,
        path="/",
    )


@router.post(
    "/register",
    response_model=TokenSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    req: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> TokenSessionResponse:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"auth:register:{client_ip}", settings.rate_limit_auth_per_minute)

    svc = IdentityService(session)
    token_res = await svc.register_user(
        email=req.email,
        password=req.password,
        full_name=req.full_name,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip,
    )
    _set_session_cookies(response, token_res)
    return token_res


@router.post("/login", response_model=TokenSessionResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> TokenSessionResponse:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"auth:login:{client_ip}", settings.rate_limit_auth_per_minute)

    svc = IdentityService(session)
    token_res = await svc.authenticate_user(
        email=req.email,
        password=req.password,
        tenant_id=req.tenant_id,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip,
    )
    _set_session_cookies(response, token_res)
    return token_res


@router.post("/refresh", response_model=TokenSessionResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    cookie_refresh: str | None = Cookie(default=None, alias="akademia_refresh_token"),
    session: AsyncSession = Depends(get_db_session),
) -> TokenSessionResponse:
    raw_token = (body.refresh_token if body and body.refresh_token else None) or cookie_refresh or ""
    preferred_tenant = body.tenant_id if body else None
    client_ip = request.client.host if request.client else "unknown"

    svc = IdentityService(session)
    token_res = await svc.refresh_session(
        raw_refresh_token=raw_token,
        preferred_tenant_id=preferred_tenant,
        user_agent=request.headers.get("User-Agent"),
        ip_address=client_ip,
    )
    _set_session_cookies(response, token_res)
    return token_res


@router.post("/switch-tenant", response_model=TokenSessionResponse)
async def switch_active_tenant(
    req: SwitchTenantRequest,
    request: Request,
    response: Response,
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> TokenSessionResponse:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one()
    svc = IdentityService(session)
    token_res = await svc.create_session_tokens(
        user=user,
        preferred_tenant_id=req.tenant_id,
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_session_cookies(response, token_res)
    return token_res


@router.post("/logout", response_model=ActionStatusResponse)
async def logout(
    response: Response,
    body: RefreshRequest | None = None,
    cookie_refresh: str | None = Cookie(default=None, alias="akademia_refresh_token"),
    session: AsyncSession = Depends(get_db_session),
) -> ActionStatusResponse:
    settings = get_settings()
    raw_token = (body.refresh_token if body and body.refresh_token else None) or cookie_refresh
    svc = IdentityService(session)
    await svc.revoke_session(raw_token)
    response.delete_cookie(settings.session_cookie_name, path="/api/v1/auth")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return ActionStatusResponse(status="ok", message="Session revoked and logged out.")


@router.post("/forgot-password", response_model=ActionStatusResponse)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ActionStatusResponse:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"auth:forgot:{client_ip}", settings.rate_limit_auth_per_minute)

    svc = IdentityService(session)
    dev_hint, expires_at = await svc.create_password_reset(req.email)
    return ActionStatusResponse(
        status="ok",
        message="If an account matches that email, a password recovery token has been issued.",
        token_dev_hint=dev_hint,
        expires_at=expires_at,
    )


@router.post("/reset-password", response_model=ActionStatusResponse)
async def reset_password(
    req: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ActionStatusResponse:
    svc = IdentityService(session)
    await svc.reset_password(req.token, req.new_password)
    return ActionStatusResponse(
        status="ok",
        message="Password has been reset and existing sessions revoked.",
    )


@router.post("/verify-email", response_model=ActionStatusResponse)
async def verify_email(
    req: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ActionStatusResponse:
    svc = IdentityService(session)
    await svc.verify_email(req.token)
    return ActionStatusResponse(status="ok", message="Email address verified.")


@router.get("/me", response_model=AuthProfileResponse)
async def get_me(
    principal: PrincipalContext = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AuthProfileResponse:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one()
    svc = IdentityService(session)
    return await svc.build_profile(user, preferred_tenant_id=principal.tenant_id)
