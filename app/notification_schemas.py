from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class NotificationType(StrEnum):
    DUE_SOON = "due_soon"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"
    SYSTEM = "system"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"
    SUCCESS = "success"


class NotificationRead(BaseModel):
    id: UUID
    transaction_id: UUID | None
    notification_type: NotificationType
    severity: NotificationSeverity
    title: str
    message: str
    action_path: str | None
    due_date: date | None
    read_at: datetime | None
    snoozed_until: datetime | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class NotificationListRead(BaseModel):
    items: list[NotificationRead]
    unread_count: int


class NotificationCountRead(BaseModel):
    unread_count: int


class NotificationPreferenceRead(BaseModel):
    due_soon_enabled: bool
    due_today_enabled: bool
    overdue_enabled: bool
    browser_notifications_enabled: bool
    reminder_days: list[int]


class NotificationPreferenceUpdate(BaseModel):
    due_soon_enabled: bool = True
    due_today_enabled: bool = True
    overdue_enabled: bool = True
    browser_notifications_enabled: bool = False
    reminder_days: list[int] = Field(
        default_factory=lambda: [1, 3, 7],
        max_length=10,
    )

    @field_validator("reminder_days")
    @classmethod
    def validate_reminder_days(
        cls,
        value: list[int],
    ) -> list[int]:
        normalized = sorted(set(value))

        if any(
            day < 1 or day > 30
            for day in normalized
        ):
            raise ValueError(
                "Os dias de antecedência devem estar entre 1 e 30."
            )

        return normalized


class NotificationSnoozeInput(BaseModel):
    days: int = Field(
        default=1,
        ge=1,
        le=30,
    )


class NotificationSyncRead(BaseModel):
    synchronized: int
    unread_count: int
