from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import ROLE_PERMISSION_MAP
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.tenant_context import clear_tenant_context, set_tenant_context
from app.modules.identity.models import (
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserSession,
)
from app.modules.identity.schemas import (
    AuthProfileResponse,
    MembershipSummary,
    TokenSessionResponse,
)
from app.modules.memberships.models import MembershipRole, Role
from app.shared.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ValidationAppError,
)


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    async def get_user_memberships_and_roles(
        self, user_id: UUID
    ) -> list[MembershipSummary]:
        rows = (
            await self.session.execute(
                text("SELECT * FROM get_user_memberships_bootstrap(:uid)"),
                {"uid": user_id},
            )
        ).mappings().all()

        summaries: list[MembershipSummary] = []
        for row in rows:
            tid: UUID = row["tenant_id"]
            mid: UUID = row["membership_id"]
            await set_tenant_context(self.session, tid)
            role_stmt = (
                select(Role.code)
                .join(MembershipRole, MembershipRole.role_id == Role.id)
                .where(
                    MembershipRole.tenant_id == tid,
                    MembershipRole.membership_id == mid,
                )
            )
            role_codes = list((await self.session.execute(role_stmt)).scalars().all())
            summaries.append(
                MembershipSummary(
                    membership_id=mid,
                    tenant_id=tid,
                    tenant_name=row["tenant_name"],
                    tenant_slug=row["tenant_slug"],
                    roles=role_codes,
                    status=row["membership_status"],
                )
            )
        await clear_tenant_context(self.session)
        return summaries

    async def build_profile(
        self,
        user: User,
        preferred_tenant_id: UUID | None = None,
    ) -> AuthProfileResponse:
        memberships = await self.get_user_memberships_and_roles(user.id)
        active_mem: MembershipSummary | None = None
        if preferred_tenant_id is not None:
            for m in memberships:
                if m.tenant_id == preferred_tenant_id:
                    active_mem = m
                    break
            if active_mem is None:
                raise AuthorizationError("User does not have an active membership in the requested tenant.")
        elif memberships:
            active_mem = memberships[0]

        active_roles = active_mem.roles if active_mem else []
        perms: set[str] = set()
        for r in active_roles:
            perms.update(ROLE_PERMISSION_MAP.get(r, set()))

        if active_mem:
            await set_tenant_context(self.session, active_mem.tenant_id)

        return AuthProfileResponse(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            email_verified=user.email_verified,
            is_platform_admin=user.is_platform_admin,
            active_tenant_id=active_mem.tenant_id if active_mem else None,
            active_membership_id=active_mem.membership_id if active_mem else None,
            active_roles=active_roles,
            active_permissions=sorted(perms),
            memberships=memberships,
        )

    async def create_session_tokens(
        self,
        *,
        user: User,
        preferred_tenant_id: UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
        verification_token_dev_hint: str | None = None,
    ) -> TokenSessionResponse:
        profile = await self.build_profile(user, preferred_tenant_id=preferred_tenant_id)
        raw_refresh = generate_secure_token(32)
        raw_csrf = generate_secure_token(24)
        now = datetime.now(UTC)

        user_session = UserSession(
            user_id=user.id,
            active_tenant_id=profile.active_tenant_id,
            refresh_token_hash=hash_token(raw_refresh),
            csrf_token_hash=hash_token(raw_csrf),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
        )
        self.session.add(user_session)
        await self.session.flush()

        access_token = create_access_token(
            user_id=user.id,
            tenant_id=profile.active_tenant_id,
            membership_id=profile.active_membership_id,
            roles=profile.active_roles,
            is_platform_admin=user.is_platform_admin,
        )
        return TokenSessionResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            csrf_token=raw_csrf,
            expires_in=self.settings.access_token_expire_minutes * 60,
            user=profile,
            verification_token_dev_hint=verification_token_dev_hint,
        )

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenSessionResponse:
        norm_email = self.normalize_email(email)
        existing = (
            await self.session.execute(select(User).where(User.email == norm_email))
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("An account with this email address already exists.")

        user = User(
            email=norm_email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            status="active",
            email_verified=False,
            is_platform_admin=False,
        )
        self.session.add(user)
        await self.session.flush()

        raw_verify_token = generate_secure_token(24)
        ver_record = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_verify_token),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        self.session.add(ver_record)
        await self.session.flush()

        dev_hint = raw_verify_token if self.settings.app_env != "production" else None
        return await self.create_session_tokens(
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            verification_token_dev_hint=dev_hint,
        )

    async def authenticate_user(
        self,
        *,
        email: str,
        password: str,
        tenant_id: UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenSessionResponse:
        norm_email = self.normalize_email(email)
        user = (
            await self.session.execute(select(User).where(User.email == norm_email))
        ).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")
        if user.status != "active":
            raise AuthorizationError("User account is suspended or deactivated.")

        user.last_login_at = datetime.now(UTC)
        await self.session.flush()
        return await self.create_session_tokens(
            user=user,
            preferred_tenant_id=tenant_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    async def refresh_session(
        self,
        *,
        raw_refresh_token: str,
        preferred_tenant_id: UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenSessionResponse:
        if not raw_refresh_token:
            raise AuthenticationError("Missing refresh token.")
        tok_hash = hash_token(raw_refresh_token)
        sess = (
            await self.session.execute(
                select(UserSession).where(UserSession.refresh_token_hash == tok_hash)
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
            raise AuthenticationError("Refresh session is invalid, expired, or revoked.")

        # Rotate refresh token (revoke old session record)
        sess.revoked_at = now
        user = (
            await self.session.execute(select(User).where(User.id == sess.user_id))
        ).scalar_one_or_none()
        if user is None or user.status != "active":
            raise AuthenticationError("Account is no longer active.")

        target_tenant = preferred_tenant_id or sess.active_tenant_id
        return await self.create_session_tokens(
            user=user,
            preferred_tenant_id=target_tenant,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    async def revoke_session(self, raw_refresh_token: str | None, user_id: UUID | None = None) -> None:
        now = datetime.now(UTC)
        if raw_refresh_token:
            tok_hash = hash_token(raw_refresh_token)
            sess = (
                await self.session.execute(
                    select(UserSession).where(UserSession.refresh_token_hash == tok_hash)
                )
            ).scalar_one_or_none()
            if sess is not None:
                sess.revoked_at = now
        elif user_id is not None:
            sessions = (
                await self.session.execute(
                    select(UserSession).where(
                        UserSession.user_id == user_id,
                        UserSession.revoked_at.is_(None),
                    )
                )
            ).scalars().all()
            for s in sessions:
                s.revoked_at = now
        await self.session.flush()

    async def create_password_reset(self, email: str) -> tuple[str | None, datetime]:
        norm_email = self.normalize_email(email)
        user = (
            await self.session.execute(select(User).where(User.email == norm_email))
        ).scalar_one_or_none()
        expires_at = datetime.now(UTC) + timedelta(minutes=30)
        if user is None:
            return None, expires_at
        raw_tok = generate_secure_token(24)
        reset_rec = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_tok),
            expires_at=expires_at,
        )
        self.session.add(reset_rec)
        await self.session.flush()
        dev_hint = raw_tok if self.settings.app_env != "production" else None
        return dev_hint, expires_at

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        tok_hash = hash_token(raw_token)
        rec = (
            await self.session.execute(
                select(PasswordResetToken).where(PasswordResetToken.token_hash == tok_hash)
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if rec is None or rec.used_at is not None or rec.expires_at <= now:
            raise ValidationAppError("Password recovery token is invalid, expired, or already used.")
        rec.used_at = now
        user = (
            await self.session.execute(select(User).where(User.id == rec.user_id))
        ).scalar_one()
        user.password_hash = hash_password(new_password)
        # Revoke existing active sessions on password reset
        await self.revoke_session(None, user_id=user.id)
        await self.session.flush()

    async def verify_email(self, raw_token: str) -> None:
        tok_hash = hash_token(raw_token)
        rec = (
            await self.session.execute(
                select(EmailVerificationToken).where(
                    EmailVerificationToken.token_hash == tok_hash
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if rec is None or rec.verified_at is not None or rec.expires_at <= now:
            raise ValidationAppError("Email verification token is invalid, expired, or already used.")
        rec.verified_at = now
        user = (
            await self.session.execute(select(User).where(User.id == rec.user_id))
        ).scalar_one()
        user.email_verified = True
        await self.session.flush()
