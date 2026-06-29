from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Category,
    Transaction,
    TransactionGroup,
)
from app.models.enums import (
    CategoryApplication,
    GroupType,
    TransactionType,
)
from app.transaction_crud_schemas import (
    TransactionDeleteResult,
    TransactionEditInput,
    TransactionEditResult,
    TransactionGroupActiveResult,
    UpdateScope,
)


MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )


def _get_owned_transaction(
    session: Session,
    *,
    transaction_id: UUID,
    user_id: UUID,
) -> Transaction:
    transaction = session.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimentação não encontrada.",
        )

    return transaction


def _get_group(
    session: Session,
    *,
    group_id: UUID,
    user_id: UUID,
) -> TransactionGroup:
    group = session.scalar(
        select(TransactionGroup).where(
            TransactionGroup.id == group_id,
            TransactionGroup.user_id == user_id,
        )
    )

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grupo não encontrado.",
        )

    return group


def _get_group_transactions(
    session: Session,
    *,
    group_id: UUID,
    user_id: UUID,
) -> list[Transaction]:
    return list(
        session.scalars(
            select(Transaction)
            .where(
                Transaction.group_id == group_id,
                Transaction.user_id == user_id,
            )
            .order_by(
                Transaction.sequence_number.asc(),
            )
        )
    )


def _validate_account_and_category(
    session: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    category_id: UUID | None,
    transaction_type: TransactionType,
) -> None:
    account = session.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.is_active.is_(True),
        )
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conta inválida ou inativa.",
        )

    if category_id is None:
        return

    category = session.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == user_id,
            Category.is_active.is_(True),
        )
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Categoria inválida ou inativa.",
        )

    expected_application = (
        CategoryApplication.INCOME
        if transaction_type == TransactionType.INCOME
        else CategoryApplication.EXPENSE
    )

    if category.application not in {
        expected_application,
        CategoryApplication.BOTH,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A categoria selecionada não pode ser usada "
                "neste tipo de movimentação."
            ),
        )


def _selected_transactions(
    transactions: list[Transaction],
    *,
    selected: Transaction,
    scope: UpdateScope,
) -> list[Transaction]:
    if scope == UpdateScope.SINGLE:
        return [selected]

    if scope == UpdateScope.THIS_AND_FOLLOWING:
        return [
            transaction
            for transaction in transactions
            if transaction.sequence_number
            >= selected.sequence_number
        ]

    return transactions


def _apply_transaction_fields(
    transaction: Transaction,
    payload: TransactionEditInput,
) -> None:
    transaction.description = payload.description
    transaction.notes = payload.notes
    transaction.account_id = payload.account_id
    transaction.category_id = payload.category_id


def _apply_group_fields(
    group: TransactionGroup,
    payload: TransactionEditInput,
) -> None:
    group.description = payload.description
    group.notes = payload.notes
    group.account_id = payload.account_id
    group.category_id = payload.category_id


def _update_group_dates_from_transactions(
    group: TransactionGroup,
    transactions: list[Transaction],
) -> None:
    if not transactions:
        group.generated_until = None
        return

    ordered = sorted(
        transactions,
        key=lambda item: item.sequence_number,
    )
    group.generated_until = ordered[-1].due_date

    if (
        group.group_type != GroupType.RECURRING
        or not group.is_indefinite
    ):
        group.end_date = ordered[-1].due_date


def _recalculate_installment_group(
    group: TransactionGroup,
    transactions: list[Transaction],
) -> None:
    total = sum(
        (transaction.amount for transaction in transactions),
        Decimal("0.00"),
    )
    group.total_amount = _money(total)

    if transactions:
        group.base_amount = _money(
            total / Decimal(len(transactions))
        )


def update_transaction(
    session: Session,
    *,
    transaction_id: UUID,
    user_id: UUID,
    payload: TransactionEditInput,
) -> TransactionEditResult:
    selected = _get_owned_transaction(
        session,
        transaction_id=transaction_id,
        user_id=user_id,
    )
    group = _get_group(
        session,
        group_id=selected.group_id,
        user_id=user_id,
    )
    transactions = _get_group_transactions(
        session,
        group_id=group.id,
        user_id=user_id,
    )

    _validate_account_and_category(
        session,
        user_id=user_id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        transaction_type=selected.transaction_type,
    )

    effective_scope = payload.scope

    if group.group_type == GroupType.SINGLE:
        effective_scope = UpdateScope.ENTIRE_GROUP

    targets = _selected_transactions(
        transactions,
        selected=selected,
        scope=effective_scope,
    )

    if effective_scope == UpdateScope.ENTIRE_GROUP:
        _apply_group_fields(group, payload)
        group.start_date = payload.due_date

        if group.group_type == GroupType.INSTALLMENT:
            total_amount = _money(payload.amount)
            installment_amount = _money(
                total_amount / Decimal(len(transactions))
            )
            distributed = Decimal("0.00")

            for index, transaction in enumerate(transactions):
                _apply_transaction_fields(
                    transaction,
                    payload,
                )
                transaction.due_date = (
                    payload.due_date
                    + relativedelta(months=index)
                )
                transaction.occurrence_date = (
                    transaction.due_date
                )

                if index == len(transactions) - 1:
                    transaction.amount = _money(
                        total_amount - distributed
                    )
                else:
                    transaction.amount = installment_amount
                    distributed += transaction.amount

            group.total_amount = total_amount
            group.base_amount = installment_amount
        else:
            occurrence_amount = _money(payload.amount)

            for index, transaction in enumerate(transactions):
                _apply_transaction_fields(
                    transaction,
                    payload,
                )
                transaction.amount = occurrence_amount
                transaction.due_date = (
                    payload.due_date
                    + relativedelta(months=index)
                )
                transaction.occurrence_date = (
                    transaction.due_date
                )

            group.base_amount = occurrence_amount
            group.total_amount = (
                occurrence_amount
                if group.group_type == GroupType.SINGLE
                else None
            )

    elif effective_scope == UpdateScope.THIS_AND_FOLLOWING:
        selected_sequence = selected.sequence_number
        occurrence_amount = _money(payload.amount)

        for transaction in targets:
            month_offset = (
                transaction.sequence_number
                - selected_sequence
            )
            _apply_transaction_fields(
                transaction,
                payload,
            )
            transaction.amount = occurrence_amount
            transaction.due_date = (
                payload.due_date
                + relativedelta(months=month_offset)
            )
            transaction.occurrence_date = (
                transaction.due_date
            )

        if group.group_type == GroupType.RECURRING:
            _apply_group_fields(group, payload)
            group.base_amount = occurrence_amount
            group.start_date = (
                payload.due_date
                - relativedelta(
                    months=selected_sequence - 1,
                )
            )

    else:
        target = targets[0]
        _apply_transaction_fields(
            target,
            payload,
        )
        target.amount = _money(payload.amount)
        target.due_date = payload.due_date
        target.occurrence_date = payload.due_date

    if group.group_type == GroupType.INSTALLMENT:
        _recalculate_installment_group(
            group,
            transactions,
        )

    _update_group_dates_from_transactions(
        group,
        transactions,
    )

    session.commit()

    return TransactionEditResult(
        updated_transactions=len(targets),
        group_id=group.id,
        message="Movimentação atualizada com sucesso.",
    )


def _renumber_transactions(
    transactions: list[Transaction],
) -> None:
    for sequence_number, transaction in enumerate(
        sorted(
            transactions,
            key=lambda item: item.sequence_number,
        ),
        start=1,
    ):
        transaction.sequence_number = sequence_number


def delete_transaction(
    session: Session,
    *,
    transaction_id: UUID,
    user_id: UUID,
    scope: UpdateScope,
) -> TransactionDeleteResult:
    selected = _get_owned_transaction(
        session,
        transaction_id=transaction_id,
        user_id=user_id,
    )
    group = _get_group(
        session,
        group_id=selected.group_id,
        user_id=user_id,
    )
    transactions = _get_group_transactions(
        session,
        group_id=group.id,
        user_id=user_id,
    )

    effective_scope = scope

    if group.group_type == GroupType.SINGLE:
        effective_scope = UpdateScope.ENTIRE_GROUP

    targets = _selected_transactions(
        transactions,
        selected=selected,
        scope=effective_scope,
    )
    target_ids = {
        transaction.id
        for transaction in targets
    }

    remaining = [
        transaction
        for transaction in transactions
        if transaction.id not in target_ids
    ]

    deleted_group = (
        effective_scope == UpdateScope.ENTIRE_GROUP
        or not remaining
    )

    for transaction in targets:
        session.delete(transaction)

    session.flush()

    if deleted_group:
        session.delete(group)
    else:
        _renumber_transactions(remaining)

        group.occurrence_count = len(remaining)
        group.generated_occurrences = len(remaining)

        if group.group_type == GroupType.INSTALLMENT:
            _recalculate_installment_group(
                group,
                remaining,
            )

        if (
            group.group_type == GroupType.RECURRING
            and effective_scope
            == UpdateScope.THIS_AND_FOLLOWING
        ):
            group.is_active = False
            group.is_indefinite = False

        _update_group_dates_from_transactions(
            group,
            remaining,
        )

    session.commit()

    return TransactionDeleteResult(
        deleted_transactions=len(targets),
        deleted_group=deleted_group,
        message="Movimentação excluída com sucesso.",
    )


def set_group_active(
    session: Session,
    *,
    group_id: UUID,
    user_id: UUID,
    active: bool,
) -> TransactionGroupActiveResult:
    group = _get_group(
        session,
        group_id=group_id,
        user_id=user_id,
    )
    group.is_active = active

    session.commit()

    return TransactionGroupActiveResult(
        group_id=group.id,
        is_active=group.is_active,
        message=(
            "Grupo reativado com sucesso."
            if active
            else "Grupo desativado com sucesso."
        ),
    )


def count_group_transactions(
    session: Session,
    *,
    group_id: UUID,
    user_id: UUID,
) -> int:
    return int(
        session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.group_id == group_id,
                Transaction.user_id == user_id,
            )
        )
        or 0
    )
