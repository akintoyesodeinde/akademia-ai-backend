from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwnedMixin


class Notification(Base, TenantOwnedMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "recipient_membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_notifications_recipient_tenant",
        ),
    )

    recipient_membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base, TenantOwnedMixin):
    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending, published, failed, dead_letter
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
