from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from app.models.enums import (
    TransactionStatus,
    TransactionType,
)


class BulkTransactionScope(StrEnum):
    SELECTED = "selected"
    MONTH = "month"
    PAST_DUE = "past_due"
    UNTIL_DATE = "until_date"


class BulkTransactionAction(StrEnum):
    COMPLETE = "complete"
    REOPEN = "reopen"


class BulkTransactionRequest(BaseModel):
    action: BulkTransactionAction
    scope: BulkTransactionScope

    transaction_ids: list[UUID] = Field(
        default_factory=list,
        max_length=500,
    )
    reference_month: date | None = None
    until_date: date | None = None
    completion_date: date | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        if (
            self.scope
            == BulkTransactionScope.SELECTED
            and not self.transaction_ids
        ):
            raise ValueError(
                "Selecione pelo menos uma movimentação."
            )

        if (
            self.scope
            == BulkTransactionScope.MONTH
            and self.reference_month is None
        ):
            raise ValueError(
                "Informe o mês desejado."
            )

        if (
            self.scope
            == BulkTransactionScope.UNTIL_DATE
            and self.until_date is None
        ):
            raise ValueError(
                "Informe a data-limite."
            )

        return self


class BulkTransactionSample(BaseModel):
    id: UUID
    description: str
    transaction_type: TransactionType
    status: TransactionStatus
    amount: float
    due_date: date


class BulkTransactionPreview(BaseModel):
    action: BulkTransactionAction
    scope: BulkTransactionScope

    candidate_count: int
    skipped_count: int

    income_count: int
    expense_count: int
    income_total: float
    expense_total: float
    net_total: float

    first_due_date: date | None
    last_due_date: date | None

    closed_months: list[date]
    requires_closed_month_confirmation: bool

    sample: list[BulkTransactionSample]


class BulkTransactionApplyInput(
    BulkTransactionRequest
):
    confirm_closed_months: bool = False


class BulkTransactionResult(BaseModel):
    action: BulkTransactionAction
    updated_count: int
    skipped_count: int
    closed_months: list[date]
    message: str
