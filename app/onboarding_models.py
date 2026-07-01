from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.base import Base
from app.models.entities import (
    TimestampMixin,
)


class UserOnboardingState(
    TimestampMixin,
    Base,
):
    __tablename__ = (
        "user_onboarding_states"
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
        unique=True,
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="not_started",
        server_default="not_started",
        nullable=False,
    )
    current_step: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    completed_steps: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    draft: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    auto_completed: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )
    started_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime(timezone=True),
        )
    )
    completed_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime(timezone=True),
        )
    )
    skipped_at: Mapped[datetime | None] = (
        mapped_column(
            DateTime(timezone=True),
        )
    )
