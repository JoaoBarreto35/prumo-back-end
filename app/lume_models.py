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
    Text,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.db.base import Base
from app.models.entities import TimestampMixin


class LumeConversation(TimestampMixin, Base):
    __tablename__ = "lume_conversations"
    __table_args__ = (
        Index(
            "ix_lume_conversations_user_last_message",
            "user_id",
            "last_message_at",
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
    title: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        default="Nova conversa",
        server_default="Nova conversa",
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    messages: Mapped[list[LumeMessage]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LumeMessage.created_at",
    )


class LumeMessage(TimestampMixin, Base):
    __tablename__ = "lume_messages"
    __table_args__ = (
        Index(
            "ix_lume_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_lume_messages_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "lume_conversations.id",
            ondelete="CASCADE",
        ),
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
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    action_kind: Mapped[str | None] = mapped_column(
        String(40),
    )
    action_payload: Mapped[dict | None] = mapped_column(
        JSON,
    )
    action_status: Mapped[str | None] = mapped_column(
        String(24),
    )
    action_result_id: Mapped[str | None] = mapped_column(
        String(64),
    )

    model_name: Mapped[str | None] = mapped_column(
        String(120),
    )
    input_tokens: Mapped[int | None] = mapped_column(
        Integer,
    )
    output_tokens: Mapped[int | None] = mapped_column(
        Integer,
    )
