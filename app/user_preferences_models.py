from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.base import Base
from app.models.entities import TimestampMixin


class UserPreference(
    TimestampMixin,
    Base,
):
    __tablename__ = "user_preferences"

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

    theme: Mapped[str] = mapped_column(
        String(16),
        default="system",
        server_default="system",
        nullable=False,
    )
    density: Mapped[str] = mapped_column(
        String(16),
        default="comfortable",
        server_default="comfortable",
        nullable=False,
    )
    reduce_motion: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    default_page: Mapped[str] = mapped_column(
        String(40),
        default="/home",
        server_default="/home",
        nullable=False,
    )
