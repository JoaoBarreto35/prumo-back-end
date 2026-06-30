from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    GroupType,
    TransactionStatus,
    TransactionType,
)


class TransactionListRead(BaseModel):
    id: UUID
    group_id: UUID
    account_id: UUID
    category_id: UUID | None

    account_name: str
    category_name: str | None

    transaction_type: TransactionType
    group_type: GroupType
    description: str
    amount: Decimal
    status: TransactionStatus

    occurrence_date: date
    due_date: date
    sequence_number: int
    total_occurrences: int
    is_group_active: bool

    model_config = ConfigDict(
        from_attributes=True,
    )
