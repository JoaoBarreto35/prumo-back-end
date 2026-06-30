from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class LumeRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class LumeActionKind(StrEnum):
    CREATE_TRANSACTION = "create_transaction"
    CREATE_PLANNING_SCENARIO = (
        "create_planning_scenario"
    )


class LumeActionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class LumeSendRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000,
    )
    conversation_id: UUID | None = None

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )


class LumeActionRead(BaseModel):
    message_id: UUID
    kind: LumeActionKind
    payload: dict[str, Any]
    status: LumeActionStatus
    result_id: str | None = None


class LumeMessageRead(BaseModel):
    id: UUID
    conversation_id: UUID
    role: LumeRole
    content: str
    created_at: datetime
    suggestions: list[str] = Field(
        default_factory=list,
    )
    action: LumeActionRead | None = None


class LumeConversationRead(BaseModel):
    id: UUID
    title: str
    last_message_at: datetime
    message_count: int


class LumeSendResponse(BaseModel):
    conversation_id: UUID
    user_message: LumeMessageRead
    assistant_message: LumeMessageRead


class LumeActionResult(BaseModel):
    success: bool
    message: str
    result_type: str | None = None
    result_id: str | None = None
    assistant_message: LumeMessageRead | None = None


class LumeSummaryRead(BaseModel):
    reference_month: str
    income: float
    expense: float
    result: float
    pending_count: int
    overdue_count: int
    upcoming_7_days: float
    insight: str
    suggestions: list[str]


class LumeModelOutput(BaseModel):
    answer: str = Field(
        min_length=1,
        max_length=5000,
    )
    suggestions: list[str] = Field(
        default_factory=list,
        max_length=3,
    )

    action_kind: Literal[
        "create_transaction",
        "create_planning_scenario",
    ] | None = None

    action_description: str | None = None
    action_notes: str | None = None
    action_transaction_type: Literal[
        "income",
        "expense",
    ] | None = None
    action_group_type: Literal[
        "single",
        "installment",
        "recurring",
    ] | None = None
    action_amount: float | None = None
    action_occurrence_count: int | None = None
    action_start_date: str | None = None
    action_is_indefinite: bool | None = None
    action_account_id: str | None = None
    action_category_id: str | None = None
