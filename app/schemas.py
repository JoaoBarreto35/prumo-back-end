from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.models.enums import (
    AccountType,
    CategoryApplication,
    GroupType,
    TransactionOrigin,
    TransactionStatus,
    TransactionType,
    UserRole,
    UserStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=120,
    )
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: str) -> str:
        has_letter = any(character.isalpha() for character in password)
        has_number = any(character.isdigit() for character in password)

        if not has_letter or not has_number:
            raise ValueError(
                "A senha deve conter pelo menos uma letra e um número."
            )

        return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(ORMModel):
    id: UUID
    name: str
    email: EmailStr
    status: UserStatus
    role: UserRole
    must_change_password: bool


class AccountCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )
    type: AccountType
    is_default: bool = False
    closing_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
    )
    due_day: int | None = Field(
        default=None,
        ge=1,
        le=31,
    )


class AccountRead(ORMModel):
    id: UUID
    name: str
    type: AccountType
    is_default: bool
    is_active: bool
    closing_day: int | None
    due_day: int | None


class CategoryCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=80,
    )
    application: CategoryApplication


class CategoryRead(ORMModel):
    id: UUID
    name: str
    application: CategoryApplication
    is_active: bool
    is_system_default: bool


class GroupCreate(BaseModel):
    group_type: GroupType
    transaction_type: TransactionType
    description: str = Field(
        min_length=1,
        max_length=180,
    )
    notes: str | None = None
    account_id: UUID
    category_id: UUID | None = None
    amount: Decimal = Field(
        gt=0,
        decimal_places=2,
    )
    occurrence_count: int | None = Field(
        default=None,
        ge=1,
    )
    start_date: date
    end_date: date | None = None
    is_indefinite: bool = False
    origin: TransactionOrigin = TransactionOrigin.MANUAL


class TransactionRead(ORMModel):
    id: UUID
    group_id: UUID
    account_id: UUID
    category_id: UUID | None

    transaction_type: TransactionType
    description: str
    amount: Decimal
    status: TransactionStatus

    occurrence_date: date
    due_date: date
    sequence_number: int


class GroupRead(ORMModel):
    id: UUID
    group_type: GroupType
    transaction_type: TransactionType
    description: str
    base_amount: Decimal
    total_amount: Decimal | None
    occurrence_count: int | None
    start_date: date
    is_active: bool
    transactions: list[TransactionRead] = Field(
        default_factory=list,
    )


class TransactionStatusUpdate(BaseModel):
    status: TransactionStatus
    completed_at: datetime | None = None


class ClosingCreate(BaseModel):
    reference_month: date
    notes: str | None = None


class ClosingRead(ORMModel):
    id: UUID
    reference_month: date
    income_total: Decimal
    expense_total: Decimal
    projected_result: Decimal
    pending_count: int
    update_count: int
    notes: str | None


class LumeRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000,
    )


class LumeResponse(BaseModel):
    answer: str