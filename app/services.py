import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_token, hash_password, verify_password
from app.core.settings import settings
from app.models.entities import (
    Account,
    Category,
    MonthlyClosing,
    Transaction,
    TransactionGroup,
    User,
    UserSession,
)
from app.models.enums import (
    AccountType,
    CategoryApplication,
    GroupType,
    TransactionStatus,
    TransactionType,
    UserRole,
    UserStatus,
)
from app.schemas import GroupCreate


EXPENSE_CATEGORIES = [
    "Alimentação", "Transporte", "Carro", "Moradia", "Saúde",
    "Educação", "Lazer", "Assinaturas", "Compras", "Dívidas",
]
INCOME_CATEGORIES = ["Salário", "Renda extra", "Venda", "Reembolso", "Presente"]


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def create_defaults(db: Session, user: User) -> None:
    db.add(Account(
        user_id=user.id,
        name="PIX",
        type=AccountType.IMMEDIATE_PAYMENT,
        is_default=True,
        is_active=True,
    ))
    for name in EXPENSE_CATEGORIES:
        db.add(Category(
            user_id=user.id, name=name,
            application=CategoryApplication.EXPENSE,
            is_system_default=True,
        ))
    for name in INCOME_CATEGORIES:
        db.add(Category(
            user_id=user.id, name=name,
            application=CategoryApplication.INCOME,
            is_system_default=True,
        ))
    db.add(Category(
        user_id=user.id, name="Outros",
        application=CategoryApplication.BOTH,
        is_system_default=True,
    ))


def ensure_admin(db: Session) -> None:
    admin = db.scalar(select(User).where(User.role == UserRole.ADMIN))
    if admin is not None:
        return

    admin = User(
        name="Administrador",
        email="admin@prumo.local",
        password_hash=hash_password("Prumo123"),
        status=UserStatus.ACTIVE,
        role=UserRole.ADMIN,
        must_change_password=True,
    )
    db.add(admin)
    db.flush()
    create_defaults(db, admin)
    db.commit()


def authenticate(db: Session, email: str, password: str, device_name: str | None):
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        return None

    session = UserSession(
        user_id=user.id,
        refresh_token_hash="pending",
        device_name=device_name,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    db.flush()

    access = create_token(user.id, "access", timedelta(minutes=settings.access_token_minutes), session.id)
    refresh = create_token(user.id, "refresh", timedelta(days=settings.refresh_token_days), session.id)
    session.refresh_token_hash = hash_password(refresh)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return user, access, refresh


def calculate_due_date(account: Account, start_date: date) -> date:
    if account.type in {AccountType.IMMEDIATE_PAYMENT, AccountType.CASH, AccountType.OTHER}:
        return start_date

    if account.closing_day is None or account.due_day is None:
        return start_date

    target_month = start_date
    if start_date.day > account.closing_day:
        target_month = add_months(start_date.replace(day=1), 1)

    last_day = calendar.monthrange(target_month.year, target_month.month)[1]
    return date(target_month.year, target_month.month, min(account.due_day, last_day))


def create_group(db: Session, user_id: UUID, data: GroupCreate) -> TransactionGroup:
    account = db.scalar(
    select(Account).where(
        Account.id == data.account_id,
        Account.user_id == user_id,
        Account.is_active.is_(True),
    )
)

    if account is None:
        raise ValueError(
            "Conta não encontrada ou inativa."
        )


    if data.category_id is not None:
        category = db.scalar(
        select(Category).where(
            Category.id == data.category_id,
            Category.user_id == user_id,
            Category.is_active.is_(True),
        )
    )

    if category is None:
        raise ValueError(
            "Categoria não encontrada ou inativa."
        )

    expected_application = (
        CategoryApplication.INCOME
        if data.transaction_type
        == TransactionType.INCOME
        else CategoryApplication.EXPENSE
    )

    if category.application not in {
        expected_application,
        CategoryApplication.BOTH,
    }:
        raise ValueError(
            "A categoria selecionada não pode "
            "ser usada neste tipo de movimentação."
        )


    if data.group_type == GroupType.SINGLE:
        count = 1
    elif data.group_type == GroupType.INSTALLMENT:
        if not data.occurrence_count:
            raise ValueError("Parcelamento exige occurrence_count.")
        count = data.occurrence_count
    else:
        count = data.occurrence_count or 12
        if data.is_indefinite:
            count = 12

    total = data.amount if data.group_type != GroupType.INSTALLMENT else data.amount
    per_occurrence = data.amount
    if data.group_type == GroupType.INSTALLMENT:
        per_occurrence = (data.amount / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    group = TransactionGroup(
        user_id=user_id,
        account_id=data.account_id,
        category_id=data.category_id,
        group_type=data.group_type,
        transaction_type=data.transaction_type,
        origin=data.origin,
        description=data.description,
        notes=data.notes,
        base_amount=per_occurrence,
        total_amount=total if data.group_type != GroupType.RECURRING else None,
        occurrence_count=None if data.is_indefinite else count,
        generated_occurrences=0,
        start_date=data.start_date,
        end_date=data.end_date,
        is_indefinite=data.is_indefinite,
        is_active=True,
    )
    db.add(group)
    db.flush()

    first_due = calculate_due_date(account, data.start_date)
    running_total = Decimal("0.00")

    for index in range(1, count + 1):
        due_date = add_months(first_due, index - 1)
        if data.end_date and due_date > data.end_date:
            break

        amount = per_occurrence
        if data.group_type == GroupType.INSTALLMENT and index == count:
            amount = data.amount - running_total
        running_total += amount

        status_value = (
            TransactionStatus.COMPLETED
            if account.type in {AccountType.IMMEDIATE_PAYMENT, AccountType.CASH}
            and due_date <= date.today()
            else TransactionStatus.PENDING
        )

        db.add(Transaction(
            group_id=group.id,
            user_id=user_id,
            account_id=data.account_id,
            category_id=data.category_id,
            transaction_type=data.transaction_type,
            status=status_value,
            description=data.description,
            notes=data.notes,
            amount=amount,
            occurrence_date=add_months(data.start_date, index - 1),
            due_date=due_date,
            completed_at=datetime.now(UTC) if status_value == TransactionStatus.COMPLETED else None,
            sequence_number=index,
        ))
        group.generated_occurrences = index
        group.generated_until = due_date

    db.commit()
    db.refresh(group)
    return group


def refresh_recurring_groups(db: Session, user_id: UUID) -> None:
    groups = db.scalars(
        select(TransactionGroup).where(
            TransactionGroup.user_id == user_id,
            TransactionGroup.group_type == GroupType.RECURRING,
            TransactionGroup.is_active.is_(True),
        )
    ).all()

    limit_date = add_months(date.today(), 12)

    for group in groups:
        while group.generated_until is None or group.generated_until < limit_date:
            next_sequence = group.generated_occurrences + 1
            if group.occurrence_count and next_sequence > group.occurrence_count:
                group.is_active = False
                break

            due_date = add_months(group.start_date, next_sequence - 1)
            if group.end_date and due_date > group.end_date:
                group.is_active = False
                break

            db.add(Transaction(
                group_id=group.id,
                user_id=group.user_id,
                account_id=group.account_id,
                category_id=group.category_id,
                transaction_type=group.transaction_type,
                status=TransactionStatus.PENDING,
                description=group.description,
                notes=group.notes,
                amount=group.base_amount,
                occurrence_date=due_date,
                due_date=due_date,
                sequence_number=next_sequence,
            ))
            group.generated_occurrences = next_sequence
            group.generated_until = due_date

    db.commit()


def calculate_closing(db: Session, user_id: UUID, reference_month: date, notes: str | None):
    month_start = reference_month.replace(day=1)
    month_end = add_months(month_start, 1)

    rows = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.due_date >= month_start,
            Transaction.due_date < month_end,
            Transaction.status != TransactionStatus.CANCELLED,
        )
    ).all()

    income = sum((x.amount for x in rows if x.transaction_type == TransactionType.INCOME), Decimal("0"))
    expense = sum((x.amount for x in rows if x.transaction_type == TransactionType.EXPENSE), Decimal("0"))
    pending = sum(1 for x in rows if x.status == TransactionStatus.PENDING)

    closing = db.scalar(
        select(MonthlyClosing).where(
            MonthlyClosing.user_id == user_id,
            MonthlyClosing.reference_month == month_start,
        )
    )
    if closing is None:
        closing = MonthlyClosing(user_id=user_id, reference_month=month_start)
        db.add(closing)
    else:
        closing.update_count += 1
        closing.last_updated_at = datetime.now(UTC)

    closing.income_total = income
    closing.expense_total = expense
    closing.projected_result = income - expense
    closing.pending_count = pending
    closing.notes = notes
    db.commit()
    db.refresh(closing)
    return closing
