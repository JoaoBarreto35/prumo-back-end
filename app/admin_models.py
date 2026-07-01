from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TimestampMixin


class AdminAuditLog(TimestampMixin, Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        Index(
            "ix_admin_audit_logs_admin_created",
            "admin_user_id",
            "created_at",
        ),
        Index(
            "ix_admin_audit_logs_target_created",
            "target_user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    admin_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    target_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(80),
        index=True,
        nullable=False,
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
