from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from app.shared.errors import AuthorizationError


class TenantRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    INSTRUCTOR = "instructor"
    LEARNER = "learner"


class PermissionCode(StrEnum):
    # Tenant & membership management
    TENANT_READ = "tenant:read"
    TENANT_MANAGE = "tenant:manage"
    MEMBERS_READ = "members:read"
    MEMBERS_INVITE = "members:invite"
    MEMBERS_MANAGE = "members:manage"
    COHORTS_MANAGE = "cohorts:manage"
    # Course & content management
    COURSE_CREATE = "course:create"
    COURSE_EDIT = "course:edit"
    COURSE_PUBLISH = "course:publish"
    COURSE_READ = "course:read"
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_MANAGE = "document:manage"
    # Enrollment & learning
    COURSE_ENROLL = "course:enroll"
    LESSON_STUDY = "lesson:study"
    # Assessments
    ASSESSMENT_AUTHOR = "assessment:author"
    ASSESSMENT_TAKE = "assessment:take"
    ASSESSMENT_GRADE_REVIEW = "assessment:grade_review"
    # AI & Learning Intelligence
    TUTOR_USE = "tutor:use"
    PRACTICE_GENERATE = "practice:generate"
    PRACTICE_REVIEW = "practice:review"
    ANALYTICS_LEARNER_SELF = "analytics:learner_self"
    ANALYTICS_INSTRUCTOR = "analytics:instructor"
    # Commercial & Audit
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"
    AUDIT_READ = "audit:read"


ROLE_PERMISSION_MAP: dict[str, set[str]] = {
    TenantRole.OWNER.value: {p.value for p in PermissionCode},
    TenantRole.ADMIN.value: {
        PermissionCode.TENANT_READ.value,
        PermissionCode.TENANT_MANAGE.value,
        PermissionCode.MEMBERS_READ.value,
        PermissionCode.MEMBERS_INVITE.value,
        PermissionCode.MEMBERS_MANAGE.value,
        PermissionCode.COHORTS_MANAGE.value,
        PermissionCode.COURSE_CREATE.value,
        PermissionCode.COURSE_EDIT.value,
        PermissionCode.COURSE_PUBLISH.value,
        PermissionCode.COURSE_READ.value,
        PermissionCode.DOCUMENT_UPLOAD.value,
        PermissionCode.DOCUMENT_MANAGE.value,
        PermissionCode.COURSE_ENROLL.value,
        PermissionCode.LESSON_STUDY.value,
        PermissionCode.ASSESSMENT_AUTHOR.value,
        PermissionCode.ASSESSMENT_GRADE_REVIEW.value,
        PermissionCode.TUTOR_USE.value,
        PermissionCode.PRACTICE_GENERATE.value,
        PermissionCode.PRACTICE_REVIEW.value,
        PermissionCode.ANALYTICS_LEARNER_SELF.value,
        PermissionCode.ANALYTICS_INSTRUCTOR.value,
        PermissionCode.BILLING_READ.value,
        PermissionCode.BILLING_MANAGE.value,
        PermissionCode.AUDIT_READ.value,
    },
    TenantRole.INSTRUCTOR.value: {
        PermissionCode.TENANT_READ.value,
        PermissionCode.MEMBERS_READ.value,
        PermissionCode.COURSE_CREATE.value,
        PermissionCode.COURSE_EDIT.value,
        PermissionCode.COURSE_PUBLISH.value,
        PermissionCode.COURSE_READ.value,
        PermissionCode.DOCUMENT_UPLOAD.value,
        PermissionCode.DOCUMENT_MANAGE.value,
        PermissionCode.LESSON_STUDY.value,
        PermissionCode.ASSESSMENT_AUTHOR.value,
        PermissionCode.ASSESSMENT_GRADE_REVIEW.value,
        PermissionCode.TUTOR_USE.value,
        PermissionCode.PRACTICE_GENERATE.value,
        PermissionCode.PRACTICE_REVIEW.value,
        PermissionCode.ANALYTICS_LEARNER_SELF.value,
        PermissionCode.ANALYTICS_INSTRUCTOR.value,
    },
    TenantRole.LEARNER.value: {
        PermissionCode.TENANT_READ.value,
        PermissionCode.COURSE_READ.value,
        PermissionCode.COURSE_ENROLL.value,
        PermissionCode.LESSON_STUDY.value,
        PermissionCode.ASSESSMENT_TAKE.value,
        PermissionCode.TUTOR_USE.value,
        PermissionCode.ANALYTICS_LEARNER_SELF.value,
    },
}


@dataclass(slots=True)
class PrincipalContext:
    user_id: UUID
    email: str
    full_name: str
    is_platform_admin: bool = False
    tenant_id: UUID | None = None
    membership_id: UUID | None = None
    roles: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)

    def require_tenant(self) -> UUID:
        if self.tenant_id is None or self.membership_id is None:
            raise AuthorizationError(
                "An active verified tenant membership context is required for this operation."
            )
        return self.tenant_id

    def has_role(self, *allowed_roles: str) -> bool:
        return any(r in self.roles for r in allowed_roles)

    def has_permission(self, permission: str) -> bool:
        if permission in self.permissions:
            return True
        return any(permission in ROLE_PERMISSION_MAP.get(role, set()) for role in self.roles)

    def require_permission(self, permission: str) -> None:
        self.require_tenant()
        if not self.has_permission(permission):
            raise AuthorizationError(f"Missing required permission: {permission}")

    def require_any_role(self, *allowed_roles: str) -> None:
        self.require_tenant()
        if not self.has_role(*allowed_roles):
            raise AuthorizationError(
                f"Operation requires one of the following tenant roles: {', '.join(allowed_roles)}"
            )

    def require_platform_admin(self) -> None:
        if not self.is_platform_admin:
            raise AuthorizationError(
                "Platform operator authorization is required for this endpoint."
            )
