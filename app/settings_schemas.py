from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    UserRole,
    UserStatus,
)


class ThemePreference(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class DensityPreference(StrEnum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


class DefaultPagePreference(StrEnum):
    HOME = "/home"
    CALENDAR = "/calendar"
    TRANSACTIONS = "/transactions"
    PLANNING = "/planning"
    REPORTS = "/reports"


class ProfileRead(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    status: UserStatus
    role: UserRole
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )


class ProfileUpdate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=120,
    )
    email: EmailStr

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )


class UserPreferenceRead(BaseModel):
    theme: ThemePreference
    density: DensityPreference
    reduce_motion: bool
    default_page: DefaultPagePreference

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserPreferenceUpdate(
    UserPreferenceRead,
):
    pass


class ChangePasswordInput(BaseModel):
    current_password: str = Field(
        min_length=1,
        max_length=200,
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
    )
    confirm_password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(
        cls,
        value: str,
    ) -> str:
        requirements = (
            any(char.islower() for char in value),
            any(char.isupper() for char in value),
            any(char.isdigit() for char in value),
        )

        if not all(requirements):
            raise ValueError(
                "A nova senha deve conter letra "
                "maiúscula, minúscula e número."
            )

        return value

    @model_validator(mode="after")
    def validate_confirmation(
        self,
    ):
        if (
            self.new_password
            != self.confirm_password
        ):
            raise ValueError(
                "A confirmação da senha "
                "não confere."
            )

        if (
            self.current_password
            == self.new_password
        ):
            raise ValueError(
                "A nova senha deve ser "
                "diferente da atual."
            )

        return self


class UserSessionRead(BaseModel):
    id: UUID
    device_name: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool


class SecurityOverviewRead(BaseModel):
    sessions: list[UserSessionRead]
    active_session_count: int


class MessageRead(BaseModel):
    message: str
