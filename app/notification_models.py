from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TimestampMixin


class NotificationPreference(TimestampMixin, Base):
    __tablename__ = "notification_preferences"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        unique=True,
        index=True,
        nullable=False,
    )

    due_soon_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    due_today_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    overdue_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    browser_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    reminder_days_csv: Mapped[str] = mapped_column(
        String(80),
        default="1,3,7",
        server_default="1,3,7",
        nullable=False,
    )


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "fingerprint",
            name="uq_notifications_user_fingerprint",
        ),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            "read_at",
            "dismissed_at",
        ),
        Index(
            "ix_notifications_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "transactions.id",
            ondelete="SET NULL",
        ),
        index=True,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(
        String(40),
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="info",
        server_default="info",
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    action_path: Mapped[str | None] = mapped_column(
        String(255),
    )
    due_date: Mapped[date | None] = mapped_column(
        Date,
        index=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
