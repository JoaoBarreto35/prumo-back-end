from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction, TransactionGroup
from app.schemas.transaction_crud import (
    TransactionDeleteResult,
    TransactionEditInput,
    TransactionEditResult,
    UpdateScope,
)


MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


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
            .order_by(Transaction.sequence_number.asc())
        )
    )


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
            if transaction.sequence_number >= selected.sequence_number
        ]

    return transactions


def _apply_common_fields(
    transaction: Transaction,
    payload: TransactionEditInput,
) -> None:
    transaction.description = payload.description
    transaction.notes = payload.notes
    transaction.account_id = payload.account_id
    transaction.category_id = payload.category_id


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
    targets = _selected_transactions(
        transactions,
        selected=selected,
        scope=payload.scope,
    )

    if payload.scope == UpdateScope.ENTIRE_GROUP:
        group.description = payload.description
        group.notes = payload.notes
        group.account_id = payload.account_id
        group.category_id = payload.category_id
        group.start_date = payload.due_date

        if str(group.group_type) == "installment":
            group.total_amount = _money(payload.amount)
            group.base_amount = _money(
                payload.amount / Decimal(len(transactions))
            )

            distributed = Decimal("0.00")
            for index, transaction in enumerate(transactions):
                _apply_common_fields(transaction, payload)
                transaction.due_date = payload.due_date + relativedelta(
                    months=index
                )
                transaction.occurrence_date = transaction.due_date

                if index == len(transactions) - 1:
                    transaction.amount = _money(
                        payload.amount - distributed
                    )
                else:
                    transaction.amount = group.base_amount
                    distributed += transaction.amount
        else:
            group.base_amount = _money(payload.amount)

            if str(group.group_type) == "single":
                group.total_amount = _money(payload.amount)

            for index, transaction in enumerate(transactions):
                _apply_common_fields(transaction, payload)
                transaction.amount = _money(payload.amount)
                transaction.due_date = payload.due_date + relativedelta(
                    months=index
                )
                transaction.occurrence_date = transaction.due_date

    elif payload.scope == UpdateScope.THIS_AND_FOLLOWING:
        selected_index = targets[0].sequence_number

        for transaction in targets:
            month_offset = transaction.sequence_number - selected_index
            _apply_common_fields(transaction, payload)
            transaction.amount = _money(payload.amount)
            transaction.due_date = payload.due_date + relativedelta(
                months=month_offset
            )
            transaction.occurrence_date = transaction.due_date

    else:
        target = targets[0]
        _apply_common_fields(target, payload)
        target.amount = _money(payload.amount)
        target.due_date = payload.due_date
        target.occurrence_date = payload.due_date

    session.commit()

    return TransactionEditResult(
        updated_transactions=len(targets),
        group_id=group.id,
        message="Movimentação atualizada com sucesso.",
    )


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
    targets = _selected_transactions(
        transactions,
        selected=selected,
        scope=scope,
    )

    deleted_group = scope == UpdateScope.ENTIRE_GROUP

    for transaction in targets:
        session.delete(transaction)

    if deleted_group:
        session.delete(group)
    else:
        remaining = len(transactions) - len(targets)

        if remaining == 0:
            session.delete(group)
            deleted_group = True
        else:
            group.occurrence_count = remaining

            if str(group.group_type) == "installment":
                group.total_amount = _money(
                    sum(
                        (
                            transaction.amount
                            for transaction in transactions
                            if transaction not in targets
                        ),
                        Decimal("0.00"),
                    )
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
) -> TransactionGroup:
    group = _get_group(
        session,
        group_id=group_id,
        user_id=user_id,
    )
    group.is_active = active
    session.commit()
    session.refresh(group)
    return group
