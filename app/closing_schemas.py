from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClosingStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    REOPENED = "reopened"


class ClosingBreakdownItem(BaseModel):
    id: str
    label: str
    amount: float
    count: int
    percentage: float


class ClosingTransactionItem(BaseModel):
    id: UUID
    description: str
    transaction_type: str
    group_type: str
    status: str
    amount: float
    due_date: date
    account_name: str
    category_name: str
    sequence_number: int
    total_occurrences: int


class ClosingMetrics(BaseModel):
    planned_income: float
    planned_expense: float
    projected_result: float

    actual_income: float
    actual_expense: float
    actual_result: float

    pending_income: float
    pending_expense: float
    pending_count: int
    completed_count: int
    overdue_count: int
    transaction_count: int

    income_realization_rate: float
    expense_realization_rate: float


class ClosingSnapshot(BaseModel):
    generated_at: datetime
    metrics: ClosingMetrics
    category_breakdown: list[ClosingBreakdownItem]
    account_breakdown: list[ClosingBreakdownItem]
    pending_transactions: list[ClosingTransactionItem]
    transactions: list[ClosingTransactionItem]


class ClosingSummaryRead(BaseModel):
    id: UUID | None
    reference_month: date
    status: ClosingStatus
    notes: str | None

    first_closed_at: datetime | None
    last_updated_at: datetime | None
    closed_at: datetime | None
    reopened_at: datetime | None
    update_count: int
    snapshot_version: int

    live: ClosingSnapshot
    closed_snapshot: ClosingSnapshot | None


class ClosingHistoryRead(BaseModel):
    id: UUID
    reference_month: date
    status: ClosingStatus
    notes: str | None
    closed_at: datetime | None
    reopened_at: datetime | None
    snapshot_version: int
    planned_income: float
    planned_expense: float
    projected_result: float
    actual_result: float
    pending_count: int
    overdue_count: int


class ClosingWrite(BaseModel):
    notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )


class ClosingNotesUpdate(ClosingWrite):
    pass


class ClosingMonthStatusRead(BaseModel):
    reference_month: date
    status: ClosingStatus
    is_closed: bool
    warning: str | None
