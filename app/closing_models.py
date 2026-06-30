from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TimestampMixin


class MonthlyClosingState(TimestampMixin, Base):
    __tablename__ = "monthly_closing_states"
    __table_args__ = (
        Index(
            "ix_monthly_closing_states_user_status",
            "user_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    closing_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "monthly_closings.id",
            ondelete="CASCADE",
        ),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="closed",
        server_default="closed",
        nullable=False,
    )
    snapshot_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reopened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
