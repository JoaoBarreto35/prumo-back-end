from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import (
    ForeignKey,
    Index,
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


class DataOperationLog(
    TimestampMixin,
    Base,
):
    __tablename__ = (
        "data_operation_logs"
    )
    __table_args__ = (
        Index(
            "ix_data_operation_logs_user_created",
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
    action: Mapped[str] = mapped_column(
        String(40),
        index=True,
        nullable=False,
    )
    data_format: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    summary: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
