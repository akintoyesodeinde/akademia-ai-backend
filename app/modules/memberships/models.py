from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin, TimestampMixin


class TenantMembership(Base, TenantOwnedMixin):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_memberships_tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, invited, suspended, revoked
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)


class RolePermission(Base, TimestampMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_pair"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class MembershipRole(Base, TenantOwnedMixin):
    __tablename__ = "membership_roles"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "membership_id", "role_id", name="uq_membership_roles_unique"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_membership_roles_membership_tenant",
        ),
    )

    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class Invitation(Base, TenantOwnedMixin):
    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        UniqueConstraint("tenant_id", "id", name="uq_invitations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "invited_by_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="SET NULL",
            name="fk_invitations_inviter_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending, accepted, expired, revoked
    invited_by_membership_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
