from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
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


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", values_callable=lambda e: [x.value for x in e]),
        default=UserStatus.PENDING,
        server_default=UserStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [x.value for x in e]),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    accounts: Mapped[list[Account]] = relationship(cascade="all, delete-orphan")
    categories: Mapped[list[Category]] = relationship(cascade="all, delete-orphan")


class UserSession(TimestampMixin, Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(160))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("closing_day IS NULL OR closing_day BETWEEN 1 AND 31", name="valid_closing_day"),
        CheckConstraint("due_day IS NULL OR due_day BETWEEN 1 AND 31", name="valid_due_day"),
        Index("uq_accounts_one_default_per_user", "user_id", unique=True, postgresql_where="is_default = true"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type", values_callable=lambda e: [x.value for x in e])
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    closing_day: Mapped[int | None] = mapped_column(SmallInteger)
    due_day: Mapped[int | None] = mapped_column(SmallInteger)


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", name="user_category_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    application: Mapped[CategoryApplication] = mapped_column(
        Enum(CategoryApplication, name="category_application", values_callable=lambda e: [x.value for x in e])
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class TransactionGroup(TimestampMixin, Base):
    __tablename__ = "transaction_groups"
    __table_args__ = (
        CheckConstraint("base_amount > 0", name="positive_base_amount"),
        CheckConstraint("occurrence_count IS NULL OR occurrence_count > 0", name="positive_occurrence_count"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    category_id: Mapped[UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    group_type: Mapped[GroupType] = mapped_column(
        Enum(GroupType, name="group_type", values_callable=lambda e: [x.value for x in e])
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", values_callable=lambda e: [x.value for x in e])
    )
    origin: Mapped[TransactionOrigin] = mapped_column(
        Enum(TransactionOrigin, name="transaction_origin", values_callable=lambda e: [x.value for x in e]),
        default=TransactionOrigin.MANUAL,
        server_default=TransactionOrigin.MANUAL.value,
    )
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    occurrence_count: Mapped[int | None] = mapped_column(Integer)
    generated_occurrences: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    generated_until: Mapped[date | None] = mapped_column(Date)
    is_indefinite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    transactions: Mapped[list[Transaction]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Transaction.sequence_number",
    )


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_amount"),
        UniqueConstraint("group_id", "sequence_number", name="group_sequence"),
        Index("ix_transactions_user_due_status", "user_id", "due_date", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("transaction_groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    category_id: Mapped[UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", values_callable=lambda e: [x.value for x in e])
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status", values_callable=lambda e: [x.value for x in e]),
        default=TransactionStatus.PENDING,
        server_default=TransactionStatus.PENDING.value,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)


class MonthlyClosing(TimestampMixin, Base):
    __tablename__ = "monthly_closings"
    __table_args__ = (UniqueConstraint("user_id", "reference_month", name="user_closing_month"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reference_month: Mapped[date] = mapped_column(Date, nullable=False)
    first_closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    update_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    income_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    expense_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    projected_result: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    lume_summary: Mapped[str | None] = mapped_column(Text)
