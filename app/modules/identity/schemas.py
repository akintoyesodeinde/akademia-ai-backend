from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.shared.schemas import APIModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    tenant_id: UUID | None = None


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


class RefreshRequest(BaseModel):
    refresh_token: str | None = None
    tenant_id: UUID | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10)


class MembershipSummary(APIModel):
    membership_id: UUID
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    roles: list[str]
    status: str


class AuthProfileResponse(APIModel):
    user_id: UUID
    email: str
    full_name: str
    email_verified: bool
    is_platform_admin: bool
    active_tenant_id: UUID | None = None
    active_membership_id: UUID | None = None
    active_roles: list[str] = Field(default_factory=list)
    active_permissions: list[str] = Field(default_factory=list)
    memberships: list[MembershipSummary] = Field(default_factory=list)


class TokenSessionResponse(APIModel):
    access_token: str
    refresh_token: str
    csrf_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthProfileResponse
    verification_token_dev_hint: str | None = None


class ActionStatusResponse(APIModel):
    status: str
    message: str
    token_dev_hint: str | None = None
    expires_at: datetime | None = None
