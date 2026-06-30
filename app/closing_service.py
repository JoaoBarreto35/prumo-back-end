from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.closing_models import MonthlyClosingState
from app.closing_schemas import (
    ClosingBreakdownItem,
    ClosingHistoryRead,
    ClosingMetrics,
    ClosingMonthStatusRead,
    ClosingSnapshot,
    ClosingStatus,
    ClosingSummaryRead,
    ClosingTransactionItem,
)
from app.models.entities import (
    Account,
    Category,
    MonthlyClosing,
    Transaction,
    TransactionGroup,
)
from app.models.enums import TransactionStatus, TransactionType
from app.services import add_months


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _float(value: Decimal | int | float) -> float:
    return float(value)


def _percentage(value: Decimal, total: Decimal) -> float:
    if total <= 0:
        return 0.0

    return float(
        (value / total) * Decimal("100")
    )


def _closing_and_state(
    db: Session,
    *,
    user_id: UUID,
    reference_month: date,
) -> tuple[
    MonthlyClosing | None,
    MonthlyClosingState | None,
]:
    month = _month_start(reference_month)

    closing = db.scalar(
        select(MonthlyClosing).where(
            MonthlyClosing.user_id == user_id,
            MonthlyClosing.reference_month == month,
        )
    )

    if closing is None:
        return None, None

    state = db.scalar(
        select(MonthlyClosingState).where(
            MonthlyClosingState.closing_id == closing.id,
            MonthlyClosingState.user_id == user_id,
        )
    )

    return closing, state


def _build_month_snapshot(
    db: Session,
    *,
    user_id: UUID,
    reference_month: date,
) -> ClosingSnapshot:
    month_start = _month_start(reference_month)
    month_end = add_months(month_start, 1)

    occurrence = aliased(Transaction)

    total_occurrences = (
        select(func.count(occurrence.id))
        .where(
            occurrence.group_id == TransactionGroup.id
        )
        .correlate(TransactionGroup)
        .scalar_subquery()
    )

    rows = db.execute(
        select(
            Transaction,
            TransactionGroup.group_type,
            Account.name.label("account_name"),
            Category.name.label("category_name"),
            total_occurrences.label("total_occurrences"),
        )
        .join(
            TransactionGroup,
            TransactionGroup.id == Transaction.group_id,
        )
        .join(
            Account,
            Account.id == Transaction.account_id,
        )
        .outerjoin(
            Category,
            Category.id == Transaction.category_id,
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.due_date >= month_start,
            Transaction.due_date < month_end,
            Transaction.status != TransactionStatus.CANCELLED,
        )
        .order_by(
            Transaction.due_date.asc(),
            Transaction.description.asc(),
        )
    ).all()

    planned_income = Decimal("0")
    planned_expense = Decimal("0")
    actual_income = Decimal("0")
    actual_expense = Decimal("0")
    pending_income = Decimal("0")
    pending_expense = Decimal("0")

    pending_count = 0
    completed_count = 0
    overdue_count = 0

    today = date.today()

    category_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "label": "",
            "amount": Decimal("0"),
            "count": 0,
        }
    )
    account_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "label": "",
            "amount": Decimal("0"),
            "count": 0,
        }
    )

    transaction_items: list[ClosingTransactionItem] = []
    pending_items: list[ClosingTransactionItem] = []

    for (
        transaction,
        group_type,
        account_name,
        category_name,
        occurrence_count,
    ) in rows:
        amount = transaction.amount

        if transaction.transaction_type == TransactionType.INCOME:
            planned_income += amount
        else:
            planned_expense += amount

            category_key = (
                str(transaction.category_id)
                if transaction.category_id
                else "uncategorized"
            )
            category_totals[category_key]["label"] = (
                category_name or "Sem categoria"
            )
            category_totals[category_key]["amount"] += amount
            category_totals[category_key]["count"] += 1

            account_key = str(transaction.account_id)
            account_totals[account_key]["label"] = account_name
            account_totals[account_key]["amount"] += amount
            account_totals[account_key]["count"] += 1

        if transaction.status == TransactionStatus.COMPLETED:
            completed_count += 1

            if transaction.transaction_type == TransactionType.INCOME:
                actual_income += amount
            else:
                actual_expense += amount
        else:
            pending_count += 1

            if transaction.transaction_type == TransactionType.INCOME:
                pending_income += amount
            else:
                pending_expense += amount

            if transaction.due_date < today:
                overdue_count += 1

        item = ClosingTransactionItem(
            id=transaction.id,
            description=transaction.description,
            transaction_type=transaction.transaction_type.value,
            group_type=group_type.value,
            status=transaction.status.value,
            amount=_float(amount),
            due_date=transaction.due_date,
            account_name=account_name,
            category_name=category_name or "Sem categoria",
            sequence_number=transaction.sequence_number,
            total_occurrences=int(occurrence_count),
        )

        transaction_items.append(item)

        if transaction.status == TransactionStatus.PENDING:
            pending_items.append(item)

    def build_breakdown(
        values: dict[str, dict[str, Any]],
        total: Decimal,
    ) -> list[ClosingBreakdownItem]:
        return sorted(
            [
                ClosingBreakdownItem(
                    id=key,
                    label=str(item["label"]),
                    amount=_float(item["amount"]),
                    count=int(item["count"]),
                    percentage=_percentage(
                        item["amount"],
                        total,
                    ),
                )
                for key, item in values.items()
            ],
            key=lambda item: item.amount,
            reverse=True,
        )

    metrics = ClosingMetrics(
        planned_income=_float(planned_income),
        planned_expense=_float(planned_expense),
        projected_result=_float(
            planned_income - planned_expense
        ),
        actual_income=_float(actual_income),
        actual_expense=_float(actual_expense),
        actual_result=_float(
            actual_income - actual_expense
        ),
        pending_income=_float(pending_income),
        pending_expense=_float(pending_expense),
        pending_count=pending_count,
        completed_count=completed_count,
        overdue_count=overdue_count,
        transaction_count=len(transaction_items),
        income_realization_rate=_percentage(
            actual_income,
            planned_income,
        ),
        expense_realization_rate=_percentage(
            actual_expense,
            planned_expense,
        ),
    )

    return ClosingSnapshot(
        generated_at=datetime.now(UTC),
        metrics=metrics,
        category_breakdown=build_breakdown(
            category_totals,
            planned_expense,
        ),
        account_breakdown=build_breakdown(
            account_totals,
            planned_expense,
        ),
        pending_transactions=pending_items,
        transactions=transaction_items,
    )


def _snapshot_from_state(
    state: MonthlyClosingState | None,
) -> ClosingSnapshot | None:
    if state is None:
        return None

    return ClosingSnapshot.model_validate(
        state.snapshot
    )


def get_month_summary(
    db: Session,
    *,
    user_id: UUID,
    reference_month: date,
) -> ClosingSummaryRead:
    month = _month_start(reference_month)

    closing, state = _closing_and_state(
        db,
        user_id=user_id,
        reference_month=month,
    )

    live = _build_month_snapshot(
        db,
        user_id=user_id,
        reference_month=month,
    )

    if (
        state is not None
        and state.status == ClosingStatus.CLOSED.value
    ):
        closing_status = ClosingStatus.CLOSED
    elif state is not None:
        closing_status = ClosingStatus.REOPENED
    else:
        closing_status = ClosingStatus.OPEN

    return ClosingSummaryRead(
        id=closing.id if closing else None,
        reference_month=month,
        status=closing_status,
        notes=closing.notes if closing else None,
        first_closed_at=(
            closing.first_closed_at if closing else None
        ),
        last_updated_at=(
            closing.last_updated_at if closing else None
        ),
        closed_at=state.closed_at if state else None,
        reopened_at=state.reopened_at if state else None,
        update_count=closing.update_count if closing else 0,
        snapshot_version=state.snapshot_version if state else 0,
        live=live,
        closed_snapshot=_snapshot_from_state(state),
    )


def close_month(
    db: Session,
    *,
    user_id: UUID,
    reference_month: date,
    notes: str | None,
) -> ClosingSummaryRead:
    month = _month_start(reference_month)
    current_month = date.today().replace(day=1)

    if month > current_month:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível fechar um mês futuro.",
        )

    closing, state = _closing_and_state(
        db,
        user_id=user_id,
        reference_month=month,
    )

    if (
        state is not None
        and state.status == ClosingStatus.CLOSED.value
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este mês já está fechado. "
                "Reabra antes de gerar uma nova fotografia."
            ),
        )

    snapshot = _build_month_snapshot(
        db,
        user_id=user_id,
        reference_month=month,
    )
    metrics = snapshot.metrics
    now = datetime.now(UTC)

    if closing is None:
        closing = MonthlyClosing(
            user_id=user_id,
            reference_month=month,
            first_closed_at=now,
            last_updated_at=now,
            update_count=0,
        )
        db.add(closing)
        db.flush()
    else:
        closing.update_count += 1
        closing.last_updated_at = now

    closing.income_total = Decimal(
        str(metrics.planned_income)
    )
    closing.expense_total = Decimal(
        str(metrics.planned_expense)
    )
    closing.projected_result = Decimal(
        str(metrics.projected_result)
    )
    closing.pending_count = metrics.pending_count
    closing.notes = notes

    if state is None:
        state = MonthlyClosingState(
            closing_id=closing.id,
            user_id=user_id,
            status=ClosingStatus.CLOSED.value,
            snapshot_version=1,
            snapshot=snapshot.model_dump(mode="json"),
            closed_at=now,
        )
        db.add(state)
    else:
        state.status = ClosingStatus.CLOSED.value
        state.snapshot_version += 1
        state.snapshot = snapshot.model_dump(mode="json")
        state.closed_at = now

    db.commit()

    return get_month_summary(
        db,
        user_id=user_id,
        reference_month=month,
    )


def reopen_month(
    db: Session,
    *,
    user_id: UUID,
    reference_month: date,
) -> ClosingSummaryRead:
    month = _month_start(reference_month)

    closing, state = _closing_and_state(
        db,
        user_id=user_id,
        reference_month=month,
    )

    if closing is None or state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fechamento não encontrado.",
        )

    if state.status != ClosingStatus.CLOSED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este mês já está aberto.",
        )

    state.status = ClosingStatus.REOPENED.value
    state.reopened_at = datetime.now(UTC)
    closing.last_updated_at = datetime.now(UTC)

    db.commit()

    return get_month_summary(
        db,
        user_id=user_id,
        reference_month=month,
    )


def update_notes(
    db: Session,
    *,
    user_id: UUID,
    reference_month: date,
    notes: str | None,
) -> ClosingSummaryRead:
    month = _month_start(reference_month)

    closing, _ = _closing_and_state(
        db,
        user_id=user_id,
        reference_month=month,
    )

    if closing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fechamento não encontrado.",
        )

    closing.notes = notes
    closing.last_updated_at = datetime.now(UTC)

    db.commit()

    return get_month_summary(
        db,
        user_id=user_id,
        reference_month=month,
    )


def list_closing_history(
    db: Session,
    *,
    user_id: UUID,
) -> list[ClosingHistoryRead]:
    rows = db.execute(
        select(
            MonthlyClosing,
            MonthlyClosingState,
        )
        .join(
            MonthlyClosingState,
            MonthlyClosingState.closing_id
            == MonthlyClosing.id,
        )
        .where(
            MonthlyClosing.user_id == user_id,
            MonthlyClosingState.user_id == user_id,
        )
        .order_by(
            MonthlyClosing.reference_month.desc(),
        )
    ).all()

    history: list[ClosingHistoryRead] = []

    for closing, state in rows:
        snapshot = ClosingSnapshot.model_validate(
            state.snapshot
        )
        metrics = snapshot.metrics

        history.append(
            ClosingHistoryRead(
                id=closing.id,
                reference_month=closing.reference_month,
                status=ClosingStatus(state.status),
                notes=closing.notes,
                closed_at=state.closed_at,
                reopened_at=state.reopened_at,
                snapshot_version=state.snapshot_version,
                planned_income=metrics.planned_income,
                planned_expense=metrics.planned_expense,
                projected_result=metrics.projected_result,
                actual_result=metrics.actual_result,
                pending_count=metrics.pending_count,
                overdue_count=metrics.overdue_count,
            )
        )

    return history


def get_month_status(
    db: Session,
    *,
    user_id: UUID,
    reference_date: date,
) -> ClosingMonthStatusRead:
    month = _month_start(reference_date)

    _, state = _closing_and_state(
        db,
        user_id=user_id,
        reference_month=month,
    )

    is_closed = bool(
        state
        and state.status == ClosingStatus.CLOSED.value
    )

    status_value = (
        ClosingStatus.CLOSED
        if is_closed
        else (
            ClosingStatus.REOPENED
            if state
            else ClosingStatus.OPEN
        )
    )

    warning = None

    if is_closed:
        warning = (
            "Este mês está fechado. "
            "A alteração muda os dados atuais, "
            "mas a fotografia oficial permanecerá preservada."
        )

    return ClosingMonthStatusRead(
        reference_month=month,
        status=status_value,
        is_closed=is_closed,
        warning=warning,
    )
