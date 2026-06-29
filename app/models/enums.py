from enum import StrEnum


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class AccountType(StrEnum):
    IMMEDIATE_PAYMENT = "immediate_payment"
    CREDIT_CARD = "credit_card"
    THIRD_PARTY_CREDIT = "third_party_credit"
    CASH = "cash"
    OTHER = "other"


class CategoryApplication(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    BOTH = "both"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class GroupType(StrEnum):
    SINGLE = "single"
    INSTALLMENT = "installment"
    RECURRING = "recurring"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TransactionOrigin(StrEnum):
    MANUAL = "manual"
    AI = "ai"
