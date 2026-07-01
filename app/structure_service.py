from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.closing_models import MonthlyClosingState
from app.models.entities import (
    Account,
    Category,
    MonthlyClosing,
    Transaction,
    TransactionGroup,
)
from app.models.enums import (
    CategoryApplication,
    GroupType,
    TransactionStatus,
    TransactionType,
)
from app.structure_schemas import (
    AccountArchiveInput,
    AccountCreateInput,
    AccountDeleteInput,
    AccountManagementRead,
    AccountTransferInput,
    AccountUpdateInput,
    CategoryCreateInput,
    CategoryDeleteInput,
    CategoryManagementRead,
    CategoryTransferInput,
    CategoryUpdateInput,
    StructureImpactRead,
    StructureOperationResult,
)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def _owned_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
) -> Account:
    account = db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
        )
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta não encontrada.",
        )

    return account


def _owned_category(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
) -> Category:
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == user_id,
        )
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoria não encontrada.",
        )

    return category


def _ensure_unique_account_name(
    db: Session,
    *,
    user_id: UUID,
    name: str,
    exclude_id: UUID | None = None,
) -> None:
    query = select(Account.id).where(
        Account.user_id == user_id,
        func.lower(Account.name) == name.lower(),
    )

    if exclude_id is not None:
        query = query.where(Account.id != exclude_id)

    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma conta com esse nome.",
        )


def _ensure_unique_category_name(
    db: Session,
    *,
    user_id: UUID,
    name: str,
    exclude_id: UUID | None = None,
) -> None:
    query = select(Category.id).where(
        Category.user_id == user_id,
        func.lower(Category.name) == name.lower(),
    )

    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)

    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma categoria com esse nome.",
        )


def _closed_months_for_transactions(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
) -> list[date]:
    query = select(Transaction.due_date).where(
        Transaction.user_id == user_id,
    )

    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)

    if category_id is not None:
        query = query.where(Transaction.category_id == category_id)

    months = sorted(
        {
            _month_start(due_date)
            for due_date in db.scalars(query)
        }
    )

    if not months:
        return []

    return list(
        db.scalars(
            select(MonthlyClosing.reference_month)
            .join(
                MonthlyClosingState,
                MonthlyClosingState.closing_id
                == MonthlyClosing.id,
            )
            .where(
                MonthlyClosing.user_id == user_id,
                MonthlyClosing.reference_month.in_(months),
                MonthlyClosingState.user_id == user_id,
                MonthlyClosingState.status == "closed",
            )
            .order_by(MonthlyClosing.reference_month.asc())
        )
    )


def _impact(
    db: Session,
    *,
    user_id: UUID,
    entity_id: UUID,
    account_id: UUID | None = None,
    category_id: UUID | None = None,
) -> StructureImpactRead:
    transaction_filters = [
        Transaction.user_id == user_id,
    ]
    group_filters = [
        TransactionGroup.user_id == user_id,
    ]

    if account_id is not None:
        transaction_filters.append(Transaction.account_id == account_id)
        group_filters.append(TransactionGroup.account_id == account_id)

    if category_id is not None:
        transaction_filters.append(Transaction.category_id == category_id)
        group_filters.append(TransactionGroup.category_id == category_id)

    def count_transactions(*extra_conditions) -> int:
        return int(
            db.scalar(
                select(func.count(Transaction.id)).where(
                    *transaction_filters,
                    *extra_conditions,
                )
            )
            or 0
        )

    transaction_count = count_transactions()
    group_count = int(
        db.scalar(
            select(func.count(TransactionGroup.id)).where(
                *group_filters,
            )
        )
        or 0
    )
    active_recurring_group_count = int(
        db.scalar(
            select(func.count(TransactionGroup.id)).where(
                *group_filters,
                TransactionGroup.group_type == GroupType.RECURRING,
                TransactionGroup.is_active.is_(True),
            )
        )
        or 0
    )

    date_bounds = db.execute(
        select(
            func.min(Transaction.due_date),
            func.max(Transaction.due_date),
        ).where(*transaction_filters)
    ).one()

    closed_months = _closed_months_for_transactions(
        db,
        user_id=user_id,
        account_id=account_id,
        category_id=category_id,
    )

    return StructureImpactRead(
        entity_id=entity_id,
        transaction_count=transaction_count,
        group_count=group_count,
        pending_count=count_transactions(
            Transaction.status == TransactionStatus.PENDING,
        ),
        completed_count=count_transactions(
            Transaction.status == TransactionStatus.COMPLETED,
        ),
        cancelled_count=count_transactions(
            Transaction.status == TransactionStatus.CANCELLED,
        ),
        income_count=count_transactions(
            Transaction.transaction_type == TransactionType.INCOME,
        ),
        expense_count=count_transactions(
            Transaction.transaction_type == TransactionType.EXPENSE,
        ),
        active_recurring_group_count=active_recurring_group_count,
        first_due_date=date_bounds[0],
        last_due_date=date_bounds[1],
        closed_months=closed_months,
        can_delete_without_transfer=(
            transaction_count == 0 and group_count == 0
        ),
    )


def get_account_impact(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
) -> StructureImpactRead:
    _owned_account(db, user_id=user_id, account_id=account_id)

    return _impact(
        db,
        user_id=user_id,
        entity_id=account_id,
        account_id=account_id,
    )


def get_category_impact(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
) -> StructureImpactRead:
    _owned_category(db, user_id=user_id, category_id=category_id)

    return _impact(
        db,
        user_id=user_id,
        entity_id=category_id,
        category_id=category_id,
    )


def list_accounts(
    db: Session,
    *,
    user_id: UUID,
) -> list[AccountManagementRead]:
    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.user_id == user_id)
            .order_by(Account.is_active.desc(), Account.name.asc())
        )
    )

    transaction_counts = dict(
        db.execute(
            select(
                Transaction.account_id,
                func.count(Transaction.id),
            )
            .where(Transaction.user_id == user_id)
            .group_by(Transaction.account_id)
        ).all()
    )
    group_counts = dict(
        db.execute(
            select(
                TransactionGroup.account_id,
                func.count(TransactionGroup.id),
            )
            .where(TransactionGroup.user_id == user_id)
            .group_by(TransactionGroup.account_id)
        ).all()
    )
    recurring_counts = dict(
        db.execute(
            select(
                TransactionGroup.account_id,
                func.count(TransactionGroup.id),
            )
            .where(
                TransactionGroup.user_id == user_id,
                TransactionGroup.group_type == GroupType.RECURRING,
                TransactionGroup.is_active.is_(True),
            )
            .group_by(TransactionGroup.account_id)
        ).all()
    )

    return [
        AccountManagementRead(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            closing_day=account.closing_day,
            due_day=account.due_day,
            transaction_count=int(transaction_counts.get(account.id, 0)),
            group_count=int(group_counts.get(account.id, 0)),
            active_recurring_group_count=int(
                recurring_counts.get(account.id, 0)
            ),
        )
        for account in accounts
    ]


def create_account(
    db: Session,
    *,
    user_id: UUID,
    payload: AccountCreateInput,
) -> AccountManagementRead:
    name = _normalize_name(payload.name)
    _ensure_unique_account_name(db, user_id=user_id, name=name)

    has_default = bool(
        db.scalar(
            select(Account.id).where(
                Account.user_id == user_id,
                Account.is_default.is_(True),
            )
        )
    )
    should_be_default = payload.is_default or not has_default

    if should_be_default:
        db.execute(
            update(Account)
            .where(Account.user_id == user_id)
            .values(is_default=False)
        )

    account = Account(
        user_id=user_id,
        name=name,
        type=payload.type,
        is_default=should_be_default,
        is_active=True,
        closing_day=payload.closing_day,
        due_day=payload.due_day,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return AccountManagementRead(
        id=account.id,
        name=account.name,
        type=account.type,
        is_default=account.is_default,
        is_active=account.is_active,
        closing_day=account.closing_day,
        due_day=account.due_day,
        transaction_count=0,
        group_count=0,
        active_recurring_group_count=0,
    )


def update_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    payload: AccountUpdateInput,
) -> AccountManagementRead:
    account = _owned_account(db, user_id=user_id, account_id=account_id)
    name = _normalize_name(payload.name)

    _ensure_unique_account_name(
        db,
        user_id=user_id,
        name=name,
        exclude_id=account.id,
    )

    account.name = name
    account.type = payload.type
    account.closing_day = payload.closing_day
    account.due_day = payload.due_day

    db.commit()

    return next(
        item
        for item in list_accounts(db, user_id=user_id)
        if item.id == account.id
    )


def set_default_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
) -> AccountManagementRead:
    account = _owned_account(db, user_id=user_id, account_id=account_id)

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Uma conta inativa não pode ser definida como padrão.",
        )

    db.execute(
        update(Account)
        .where(Account.user_id == user_id)
        .values(is_default=False)
    )
    account.is_default = True
    db.commit()

    return next(
        item
        for item in list_accounts(db, user_id=user_id)
        if item.id == account.id
    )


def activate_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
) -> AccountManagementRead:
    account = _owned_account(db, user_id=user_id, account_id=account_id)
    account.is_active = True

    has_default = bool(
        db.scalar(
            select(Account.id).where(
                Account.user_id == user_id,
                Account.is_default.is_(True),
            )
        )
    )

    if not has_default:
        account.is_default = True

    db.commit()

    return next(
        item
        for item in list_accounts(db, user_id=user_id)
        if item.id == account.id
    )


def archive_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    payload: AccountArchiveInput,
) -> AccountManagementRead:
    account = _owned_account(db, user_id=user_id, account_id=account_id)

    if not account.is_active:
        return next(
            item
            for item in list_accounts(db, user_id=user_id)
            if item.id == account.id
        )

    impact = get_account_impact(
        db,
        user_id=user_id,
        account_id=account.id,
    )

    if impact.active_recurring_group_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A conta possui recorrências ativas. "
                "Transfira os dados para outra conta ou desative as recorrências antes de arquivar."
            ),
        )

    active_count = int(
        db.scalar(
            select(func.count(Account.id)).where(
                Account.user_id == user_id,
                Account.is_active.is_(True),
            )
        )
        or 0
    )

    if active_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Crie ou reative outra conta antes de arquivar a última conta ativa.",
        )

    if account.is_default:
        if payload.replacement_default_account_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Escolha uma nova conta padrão antes de arquivar esta conta.",
            )

        replacement = _owned_account(
            db,
            user_id=user_id,
            account_id=payload.replacement_default_account_id,
        )

        if replacement.id == account.id or not replacement.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta padrão substituta deve ser outra conta ativa.",
            )

        account.is_default = False
        replacement.is_default = True

    account.is_active = False
    db.commit()

    return next(
        item
        for item in list_accounts(db, user_id=user_id)
        if item.id == account.id
    )


def _require_closed_month_confirmation(
    *,
    closed_months: list[date],
    confirmed: bool,
) -> None:
    if closed_months and not confirmed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A operação altera a situação atual de meses fechados. "
                "Confirme explicitamente para continuar; as fotografias oficiais serão preservadas."
            ),
        )


def _move_account_links(
    db: Session,
    *,
    user_id: UUID,
    source_id: UUID,
    target_id: UUID,
) -> tuple[int, int]:
    group_count = int(
        db.scalar(
            select(func.count(TransactionGroup.id)).where(
                TransactionGroup.user_id == user_id,
                TransactionGroup.account_id == source_id,
            )
        )
        or 0
    )
    transaction_count = int(
        db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user_id,
                Transaction.account_id == source_id,
            )
        )
        or 0
    )

    db.execute(
        update(TransactionGroup)
        .where(
            TransactionGroup.user_id == user_id,
            TransactionGroup.account_id == source_id,
        )
        .values(account_id=target_id)
    )
    db.execute(
        update(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.account_id == source_id,
        )
        .values(account_id=target_id)
    )

    return transaction_count, group_count


def transfer_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    payload: AccountTransferInput,
) -> StructureOperationResult:
    source = _owned_account(db, user_id=user_id, account_id=account_id)
    target = _owned_account(
        db,
        user_id=user_id,
        account_id=payload.target_account_id,
    )

    if source.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escolha uma conta de destino diferente.",
        )

    if not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conta de destino precisa estar ativa.",
        )

    impact = get_account_impact(
        db,
        user_id=user_id,
        account_id=source.id,
    )
    _require_closed_month_confirmation(
        closed_months=impact.closed_months,
        confirmed=payload.confirm_closed_months,
    )

    transaction_count, group_count = _move_account_links(
        db,
        user_id=user_id,
        source_id=source.id,
        target_id=target.id,
    )
    db.commit()

    return StructureOperationResult(
        message=(
            f"Dados transferidos de {source.name} para {target.name}. "
            "As datas existentes foram preservadas."
        ),
        updated_transactions=transaction_count,
        updated_groups=group_count,
        closed_months=impact.closed_months,
    )


def delete_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    payload: AccountDeleteInput,
) -> StructureOperationResult:
    source = _owned_account(db, user_id=user_id, account_id=account_id)

    if not payload.confirm_delete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirme a exclusão definitiva.",
        )

    impact = get_account_impact(
        db,
        user_id=user_id,
        account_id=source.id,
    )
    _require_closed_month_confirmation(
        closed_months=impact.closed_months,
        confirmed=payload.confirm_closed_months,
    )

    target: Account | None = None

    if payload.target_account_id is not None:
        target = _owned_account(
            db,
            user_id=user_id,
            account_id=payload.target_account_id,
        )

        if target.id == source.id or not target.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta de destino deve ser outra conta ativa.",
            )

    if not impact.can_delete_without_transfer and target is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conta possui movimentações ou grupos. Escolha uma conta de destino.",
        )

    if source.is_default and target is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conta padrão precisa ser substituída antes da exclusão.",
        )

    active_count = int(
        db.scalar(
            select(func.count(Account.id)).where(
                Account.user_id == user_id,
                Account.is_active.is_(True),
            )
        )
        or 0
    )

    if source.is_active and active_count <= 1 and target is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Crie ou reative outra conta antes de excluir "
                "a última conta ativa."
            ),
        )

    updated_transactions = 0
    updated_groups = 0

    if target is not None:
        updated_transactions, updated_groups = _move_account_links(
            db,
            user_id=user_id,
            source_id=source.id,
            target_id=target.id,
        )

        if source.is_default:
            db.execute(
                update(Account)
                .where(Account.user_id == user_id)
                .values(is_default=False)
            )
            target.is_default = True

    db.delete(source)
    db.commit()

    return StructureOperationResult(
        message="Conta excluída definitivamente.",
        updated_transactions=updated_transactions,
        updated_groups=updated_groups,
        closed_months=impact.closed_months,
    )


def list_categories(
    db: Session,
    *,
    user_id: UUID,
) -> list[CategoryManagementRead]:
    categories = list(
        db.scalars(
            select(Category)
            .where(Category.user_id == user_id)
            .order_by(Category.is_active.desc(), Category.name.asc())
        )
    )

    transaction_counts = dict(
        db.execute(
            select(
                Transaction.category_id,
                func.count(Transaction.id),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.category_id.is_not(None),
            )
            .group_by(Transaction.category_id)
        ).all()
    )
    group_counts = dict(
        db.execute(
            select(
                TransactionGroup.category_id,
                func.count(TransactionGroup.id),
            )
            .where(
                TransactionGroup.user_id == user_id,
                TransactionGroup.category_id.is_not(None),
            )
            .group_by(TransactionGroup.category_id)
        ).all()
    )
    income_counts = dict(
        db.execute(
            select(
                Transaction.category_id,
                func.count(Transaction.id),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.category_id.is_not(None),
                Transaction.transaction_type == TransactionType.INCOME,
            )
            .group_by(Transaction.category_id)
        ).all()
    )
    expense_counts = dict(
        db.execute(
            select(
                Transaction.category_id,
                func.count(Transaction.id),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.category_id.is_not(None),
                Transaction.transaction_type == TransactionType.EXPENSE,
            )
            .group_by(Transaction.category_id)
        ).all()
    )

    return [
        CategoryManagementRead(
            id=category.id,
            name=category.name,
            application=category.application,
            is_active=category.is_active,
            is_system_default=category.is_system_default,
            transaction_count=int(transaction_counts.get(category.id, 0)),
            group_count=int(group_counts.get(category.id, 0)),
            income_count=int(income_counts.get(category.id, 0)),
            expense_count=int(expense_counts.get(category.id, 0)),
        )
        for category in categories
    ]


def create_category(
    db: Session,
    *,
    user_id: UUID,
    payload: CategoryCreateInput,
) -> CategoryManagementRead:
    name = _normalize_name(payload.name)
    _ensure_unique_category_name(db, user_id=user_id, name=name)

    category = Category(
        user_id=user_id,
        name=name,
        application=payload.application,
        is_active=True,
        is_system_default=False,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    return CategoryManagementRead(
        id=category.id,
        name=category.name,
        application=category.application,
        is_active=category.is_active,
        is_system_default=category.is_system_default,
        transaction_count=0,
        group_count=0,
        income_count=0,
        expense_count=0,
    )


def _application_allows(
    application: CategoryApplication,
    transaction_type: TransactionType,
) -> bool:
    if application == CategoryApplication.BOTH:
        return True

    if transaction_type == TransactionType.INCOME:
        return application == CategoryApplication.INCOME

    return application == CategoryApplication.EXPENSE


def _used_category_types(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
) -> set[TransactionType]:
    transaction_types = set(
        db.scalars(
            select(Transaction.transaction_type)
            .where(
                Transaction.user_id == user_id,
                Transaction.category_id == category_id,
            )
            .distinct()
        )
    )
    group_types = set(
        db.scalars(
            select(TransactionGroup.transaction_type)
            .where(
                TransactionGroup.user_id == user_id,
                TransactionGroup.category_id == category_id,
            )
            .distinct()
        )
    )

    return transaction_types | group_types


def _ensure_category_compatible(
    db: Session,
    *,
    user_id: UUID,
    source_category_id: UUID,
    application: CategoryApplication,
) -> None:
    incompatible = [
        transaction_type
        for transaction_type in _used_category_types(
            db,
            user_id=user_id,
            category_id=source_category_id,
        )
        if not _application_allows(application, transaction_type)
    ]

    if incompatible:
        labels = ", ".join(
            "receitas" if item == TransactionType.INCOME else "despesas"
            for item in sorted(incompatible, key=lambda value: value.value)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A aplicação escolhida é incompatível com "
                f"{labels} já vinculadas a esta categoria."
            ),
        )


def update_category(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
    payload: CategoryUpdateInput,
) -> CategoryManagementRead:
    category = _owned_category(
        db,
        user_id=user_id,
        category_id=category_id,
    )
    name = _normalize_name(payload.name)

    _ensure_unique_category_name(
        db,
        user_id=user_id,
        name=name,
        exclude_id=category.id,
    )
    _ensure_category_compatible(
        db,
        user_id=user_id,
        source_category_id=category.id,
        application=payload.application,
    )

    category.name = name
    category.application = payload.application
    db.commit()

    return next(
        item
        for item in list_categories(db, user_id=user_id)
        if item.id == category.id
    )


def activate_category(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
) -> CategoryManagementRead:
    category = _owned_category(
        db,
        user_id=user_id,
        category_id=category_id,
    )
    category.is_active = True
    db.commit()

    return next(
        item
        for item in list_categories(db, user_id=user_id)
        if item.id == category.id
    )


def archive_category(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
) -> CategoryManagementRead:
    category = _owned_category(
        db,
        user_id=user_id,
        category_id=category_id,
    )
    category.is_active = False
    db.commit()

    return next(
        item
        for item in list_categories(db, user_id=user_id)
        if item.id == category.id
    )


def _move_category_links(
    db: Session,
    *,
    user_id: UUID,
    source_id: UUID,
    target_id: UUID | None,
) -> tuple[int, int]:
    group_count = int(
        db.scalar(
            select(func.count(TransactionGroup.id)).where(
                TransactionGroup.user_id == user_id,
                TransactionGroup.category_id == source_id,
            )
        )
        or 0
    )
    transaction_count = int(
        db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user_id,
                Transaction.category_id == source_id,
            )
        )
        or 0
    )

    db.execute(
        update(TransactionGroup)
        .where(
            TransactionGroup.user_id == user_id,
            TransactionGroup.category_id == source_id,
        )
        .values(category_id=target_id)
    )
    db.execute(
        update(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.category_id == source_id,
        )
        .values(category_id=target_id)
    )

    return transaction_count, group_count


def _category_destination(
    db: Session,
    *,
    user_id: UUID,
    source: Category,
    target_category_id: UUID | None,
    clear_category: bool,
) -> Category | None:
    if clear_category:
        return None

    if target_category_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe uma categoria de destino.",
        )

    target = _owned_category(
        db,
        user_id=user_id,
        category_id=target_category_id,
    )

    if target.id == source.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escolha uma categoria de destino diferente.",
        )

    if not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A categoria de destino precisa estar ativa.",
        )

    _ensure_category_compatible(
        db,
        user_id=user_id,
        source_category_id=source.id,
        application=target.application,
    )

    return target


def transfer_category(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
    payload: CategoryTransferInput,
) -> StructureOperationResult:
    source = _owned_category(
        db,
        user_id=user_id,
        category_id=category_id,
    )
    target = _category_destination(
        db,
        user_id=user_id,
        source=source,
        target_category_id=payload.target_category_id,
        clear_category=payload.clear_category,
    )
    impact = get_category_impact(
        db,
        user_id=user_id,
        category_id=source.id,
    )
    _require_closed_month_confirmation(
        closed_months=impact.closed_months,
        confirmed=payload.confirm_closed_months,
    )

    transaction_count, group_count = _move_category_links(
        db,
        user_id=user_id,
        source_id=source.id,
        target_id=target.id if target else None,
    )
    db.commit()

    destination_label = target.name if target else "Sem categoria"

    return StructureOperationResult(
        message=(
            f"Dados transferidos de {source.name} para {destination_label}."
        ),
        updated_transactions=transaction_count,
        updated_groups=group_count,
        closed_months=impact.closed_months,
    )


def delete_category(
    db: Session,
    *,
    user_id: UUID,
    category_id: UUID,
    payload: CategoryDeleteInput,
) -> StructureOperationResult:
    source = _owned_category(
        db,
        user_id=user_id,
        category_id=category_id,
    )

    if not payload.confirm_delete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirme a exclusão definitiva.",
        )

    impact = get_category_impact(
        db,
        user_id=user_id,
        category_id=source.id,
    )
    _require_closed_month_confirmation(
        closed_months=impact.closed_months,
        confirmed=payload.confirm_closed_months,
    )

    target: Category | None = None

    if not impact.can_delete_without_transfer:
        target = _category_destination(
            db,
            user_id=user_id,
            source=source,
            target_category_id=payload.target_category_id,
            clear_category=payload.clear_category,
        )

    updated_transactions = 0
    updated_groups = 0

    if not impact.can_delete_without_transfer:
        updated_transactions, updated_groups = _move_category_links(
            db,
            user_id=user_id,
            source_id=source.id,
            target_id=target.id if target else None,
        )

    db.delete(source)
    db.commit()

    return StructureOperationResult(
        message="Categoria excluída definitivamente.",
        updated_transactions=updated_transactions,
        updated_groups=updated_groups,
        closed_months=impact.closed_months,
    )
