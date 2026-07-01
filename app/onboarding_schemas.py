from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class OnboardingStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class OnboardingProgressUpdate(
    BaseModel,
):
    current_step: int = Field(
        ge=1,
        le=6,
    )
    completed_steps: list[str] = (
        Field(
            default_factory=list,
            max_length=6,
        )
    )
    draft: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )

    @field_validator(
        "completed_steps",
    )
    @classmethod
    def unique_steps(
        cls,
        value: list[str],
    ) -> list[str]:
        allowed = {
            "welcome",
            "account",
            "categories",
            "income",
            "expenses",
            "tour",
        }

        normalized = []

        for step in value:
            if step not in allowed:
                raise ValueError(
                    "Etapa de onboarding inválida."
                )

            if step not in normalized:
                normalized.append(step)

        return normalized


class OnboardingRead(BaseModel):
    status: OnboardingStatus
    current_step: int
    completed_steps: list[str]
    draft: dict[str, Any]

    account_count: int
    category_count: int
    transaction_count: int

    auto_completed: bool
    needs_onboarding: bool

    started_at: datetime | None
    completed_at: datetime | None
    skipped_at: datetime | None


class OnboardingMessageRead(
    BaseModel,
):
    message: str
    onboarding: OnboardingRead
