from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UpdateScope(StrEnum):
    SINGLE = "single"
    THIS_AND_FOLLOWING = "this_and_following"
    ENTIRE_GROUP = "entire_group"


class TransactionEditInput(BaseModel):
    scope: UpdateScope = UpdateScope.SINGLE

    description: str = Field(min_length=1, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)

    account_id: UUID
    category_id: UUID | None = None

    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date

    model_config = ConfigDict(str_strip_whitespace=True)


class TransactionStatusInput(BaseModel):
    status: str


class TransactionEditResult(BaseModel):
    updated_transactions: int
    group_id: UUID
    message: str


class TransactionDeleteInput(BaseModel):
    scope: UpdateScope = UpdateScope.SINGLE


class TransactionDeleteResult(BaseModel):
    deleted_transactions: int
    deleted_group: bool
    message: str


class TransactionDetailRead(BaseModel):
    id: UUID
    group_id: UUID
    account_id: UUID
    category_id: UUID | None

    transaction_type: str
    description: str
    amount: Decimal
    status: str

    occurrence_date: date
    due_date: date
    sequence_number: int

    group_type: str
    notes: str | None = None
    total_occurrences: int
    is_group_active: bool

    model_config = ConfigDict(from_attributes=True)
