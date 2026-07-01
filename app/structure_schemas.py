from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    AccountType,
    CategoryApplication,
)


CREDIT_ACCOUNT_TYPES = {
    AccountType.CREDIT_CARD,
    AccountType.THIRD_PARTY_CREDIT,
}


class AccountCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType
    is_default: bool = False
    closing_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def validate_card_days(self):
        if self.type in CREDIT_ACCOUNT_TYPES:
            if self.closing_day is None or self.due_day is None:
                raise ValueError(
                    "Contas de crédito exigem os dias de fechamento e vencimento."
                )
        else:
            self.closing_day = None
            self.due_day = None

        return self


class AccountUpdateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType
    closing_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def validate_card_days(self):
        if self.type in CREDIT_ACCOUNT_TYPES:
            if self.closing_day is None or self.due_day is None:
                raise ValueError(
                    "Contas de crédito exigem os dias de fechamento e vencimento."
                )
        else:
            self.closing_day = None
            self.due_day = None

        return self


class AccountManagementRead(BaseModel):
    id: UUID
    name: str
    type: AccountType
    is_default: bool
    is_active: bool
    closing_day: int | None
    due_day: int | None
    transaction_count: int
    group_count: int
    active_recurring_group_count: int

    model_config = ConfigDict(from_attributes=True)


class CategoryCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    application: CategoryApplication


class CategoryUpdateInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    application: CategoryApplication


class CategoryManagementRead(BaseModel):
    id: UUID
    name: str
    application: CategoryApplication
    is_active: bool
    is_system_default: bool
    transaction_count: int
    group_count: int
    income_count: int
    expense_count: int

    model_config = ConfigDict(from_attributes=True)


class StructureImpactRead(BaseModel):
    entity_id: UUID
    transaction_count: int
    group_count: int
    pending_count: int
    completed_count: int
    cancelled_count: int
    income_count: int
    expense_count: int
    active_recurring_group_count: int
    first_due_date: date | None
    last_due_date: date | None
    closed_months: list[date]
    can_delete_without_transfer: bool


class AccountArchiveInput(BaseModel):
    replacement_default_account_id: UUID | None = None


class AccountTransferInput(BaseModel):
    target_account_id: UUID
    confirm_closed_months: bool = False


class AccountDeleteInput(BaseModel):
    target_account_id: UUID | None = None
    confirm_closed_months: bool = False
    confirm_delete: bool = False


class CategoryTransferInput(BaseModel):
    target_category_id: UUID | None = None
    clear_category: bool = False
    confirm_closed_months: bool = False

    @model_validator(mode="after")
    def validate_destination(self):
        if self.clear_category and self.target_category_id is not None:
            raise ValueError(
                "Escolha uma categoria de destino ou remova a categoria, não ambos."
            )

        if not self.clear_category and self.target_category_id is None:
            raise ValueError(
                "Informe a categoria de destino ou escolha remover a categoria."
            )

        return self


class CategoryDeleteInput(BaseModel):
    target_category_id: UUID | None = None
    clear_category: bool = False
    confirm_closed_months: bool = False
    confirm_delete: bool = False

    @model_validator(mode="after")
    def validate_destination(self):
        if self.clear_category and self.target_category_id is not None:
            raise ValueError(
                "Escolha uma categoria de destino ou remova a categoria, não ambos."
            )

        return self


class StructureOperationResult(BaseModel):
    message: str
    updated_transactions: int = 0
    updated_groups: int = 0
    closed_months: list[date] = Field(default_factory=list)
