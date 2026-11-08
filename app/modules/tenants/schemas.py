from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.shared.schemas import APIModel


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")
    institution_type: str = Field(
        default="university",
        pattern=r"^(school|university|training_provider|corporate)$",
    )
    primary_contact_email: EmailStr | None = None


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    primary_contact_email: EmailStr | None = None
    academic_integrity_policy: str | None = Field(
        default=None,
        pattern=r"^(strict_during_assessment|guided_hints_allowed|open_book)$",
    )
    ai_tutor_enabled: bool | None = None
    ai_practice_enabled: bool | None = None
    branding_config: dict[str, Any] | None = None


class TenantResponse(APIModel):
    id: UUID
    name: str
    slug: str
    institution_type: str
    status: str
    primary_contact_email: str | None = None
    academic_integrity_policy: str = "strict_during_assessment"
    ai_tutor_enabled: bool = True
    ai_practice_enabled: bool = True
    branding_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TenantProvisionResponse(APIModel):
    tenant: TenantResponse
    membership_id: UUID
    assigned_roles: list[str]
    access_token: str


class MemberResponse(APIModel):
    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    email: str
    full_name: str
    status: str
    title: str | None = None
    roles: list[str]
    joined_at: datetime | None = None


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role_code: str = Field(pattern=r"^(admin|instructor|learner)$")


class InvitationResponse(APIModel):
    id: UUID
    tenant_id: UUID
    email: str
    role_code: str
    status: str
    expires_at: datetime
    invitation_token: str | None = None


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=10)


class UpdateMembershipRequest(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(active|suspended|revoked)$")
    title: str | None = Field(default=None, max_length=128)
    roles: list[str] | None = None


class RoleResponse(APIModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class CreateCohortRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=64)
    description: str | None = None


class CohortResponse(APIModel):
    id: UUID
    tenant_id: UUID
    name: str
    code: str
    description: str | None = None
    status: str
    created_at: datetime


class AddCohortMemberRequest(BaseModel):
    membership_id: UUID
    role_in_cohort: str = Field(default="learner", pattern=r"^(learner|instructor)$")
