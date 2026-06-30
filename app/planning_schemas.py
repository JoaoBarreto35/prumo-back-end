from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import GroupType, TransactionType


class PlanningScenarioWrite(BaseModel):
    description: str = Field(
        min_length=1,
        max_length=180,
    )
    notes: str | None = Field(
        default=None,
        max_length=4000,
    )
    transaction_type: TransactionType
    group_type: GroupType
    amount: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )
    occurrence_count: int | None = Field(
        default=None,
        ge=1,
        le=360,
    )
    start_date: date
    is_active: bool = True

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_repetition(self):
        if self.group_type == GroupType.SINGLE:
            self.occurrence_count = None
            return self

        if (
            self.group_type == GroupType.INSTALLMENT
            and (
                self.occurrence_count is None
                or self.occurrence_count < 2
            )
        ):
            raise ValueError(
                "Um cenário parcelado precisa ter pelo menos 2 parcelas."
            )

        return self


class PlanningScenarioRead(PlanningScenarioWrite):
    id: UUID

    model_config = ConfigDict(
        from_attributes=True,
    )


class PlanningScenarioActiveUpdate(BaseModel):
    is_active: bool
