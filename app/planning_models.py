from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TimestampMixin
from app.models.enums import GroupType, TransactionType


class PlanningScenario(TimestampMixin, Base):
    __tablename__ = "planning_scenarios"
    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="positive_planning_scenario_amount",
        ),
        CheckConstraint(
            "occurrence_count IS NULL OR occurrence_count > 0",
            name="positive_planning_occurrence_count",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(
            TransactionType,
            name="planning_transaction_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    group_type: Mapped[GroupType] = mapped_column(
        Enum(
            GroupType,
            name="planning_group_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )
    occurrence_count: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
