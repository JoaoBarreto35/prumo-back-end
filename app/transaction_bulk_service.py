from __future__ import annotations

from datetime import (
    UTC,
    date,
    datetime,
    time,
)
from decimal import Decimal
from uuid import UUID

from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.closing_models import (
    MonthlyClosingState,
)
from app.models.entities import (
    MonthlyClosing,
    Transaction,
)
from app.models.enums import (
    TransactionStatus,
    TransactionType,
)
from app.services import add_months
from app.transaction_bulk_schemas import (
    BulkTransactionAction,
    BulkTransactionApplyInput,
    BulkTransactionPreview,
    BulkTransactionRequest,
    BulkTransactionResult,
    BulkTransactionSample,
    BulkTransactionScope,
)


MAX_BULK_CANDIDATES = 5000


def _month_start(
    value: date,
) -> date:
    return value.replace(day=1)


def _target_status(
    action: BulkTransactionAction,
) -> TransactionStatus:
    if (
        action
        == BulkTransactionAction.COMPLETE
    ):
        return TransactionStatus.COMPLETED

    return TransactionStatus.PENDING


def _source_status(
    action: BulkTransactionAction,
) -> TransactionStatus:
    if (
        action
        == BulkTransactionAction.COMPLETE
    ):
        return TransactionStatus.PENDING

    return TransactionStatus.COMPLETED


def _candidate_query(
    *,
    user_id: UUID,
    payload: BulkTransactionRequest,
):
    query = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.status
        == _source_status(payload.action),
    )

    if (
        payload.scope
        == BulkTransactionScope.SELECTED
    ):
        query = query.where(
            Transaction.id.in_(
                payload.transaction_ids
            )
        )

    elif (
        payload.scope
        == BulkTransactionScope.MONTH
    ):
        month = _month_start(
            payload.reference_month
            or date.today()
        )
        next_month = add_months(
            month,
            1,
        )

        query = query.where(
            Transaction.due_date >= month,
            Transaction.due_date
            < next_month,
        )

    elif (
        payload.scope
        == BulkTransactionScope.PAST_DUE
    ):
        query = query.where(
            Transaction.due_date
            <= date.today(),
        )

    elif (
        payload.scope
        == BulkTransactionScope.UNTIL_DATE
    ):
        query = query.where(
            Transaction.due_date
            <= (
                payload.until_date
                or date.today()
            ),
        )

    return query.order_by(
        Transaction.due_date.asc(),
        Transaction.description.asc(),
    )


def _load_candidates(
    db: Session,
    *,
    user_id: UUID,
    payload: BulkTransactionRequest,
    lock_rows: bool = False,
) -> list[Transaction]:
    query = _candidate_query(
        user_id=user_id,
        payload=payload,
    ).limit(
        MAX_BULK_CANDIDATES
        + 1
    )

    if lock_rows:
        query = query.with_for_update()

    candidates = list(
        db.scalars(query)
    )

    if (
        len(candidates)
        > MAX_BULK_CANDIDATES
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=(
                "A operação encontrou mais "
                f"de {MAX_BULK_CANDIDATES} "
                "movimentações. Use um período menor."
            ),
        )

    return candidates


def _closed_months(
    db: Session,
    *,
    user_id: UUID,
    transactions: list[Transaction],
) -> list[date]:
    months = sorted(
        {
            _month_start(
                transaction.due_date
            )
            for transaction
            in transactions
        }
    )

    if not months:
        return []

    rows = db.scalars(
        select(
            MonthlyClosing.reference_month
        )
        .join(
            MonthlyClosingState,
            MonthlyClosingState.closing_id
            == MonthlyClosing.id,
        )
        .where(
            MonthlyClosing.user_id
            == user_id,
            MonthlyClosing.reference_month
            .in_(months),
            MonthlyClosingState.user_id
            == user_id,
            MonthlyClosingState.status
            == "closed",
        )
        .order_by(
            MonthlyClosing
            .reference_month
            .asc(),
        )
    ).all()

    return list(rows)


def preview_bulk_transactions(
    db: Session,
    *,
    user_id: UUID,
    payload: BulkTransactionRequest,
) -> BulkTransactionPreview:
    candidates = _load_candidates(
        db,
        user_id=user_id,
        payload=payload,
    )

    selected_count = (
        len(
            set(
                payload.transaction_ids
            )
        )
        if payload.scope
        == BulkTransactionScope.SELECTED
        else len(candidates)
    )

    skipped_count = max(
        0,
        selected_count
        - len(candidates),
    )

    income_transactions = [
        transaction
        for transaction in candidates
        if (
            transaction.transaction_type
            == TransactionType.INCOME
        )
    ]
    expense_transactions = [
        transaction
        for transaction in candidates
        if (
            transaction.transaction_type
            == TransactionType.EXPENSE
        )
    ]

    income_total = sum(
        (
            transaction.amount
            for transaction
            in income_transactions
        ),
        Decimal("0"),
    )
    expense_total = sum(
        (
            transaction.amount
            for transaction
            in expense_transactions
        ),
        Decimal("0"),
    )

    closed_months = _closed_months(
        db,
        user_id=user_id,
        transactions=candidates,
    )

    return BulkTransactionPreview(
        action=payload.action,
        scope=payload.scope,
        candidate_count=len(candidates),
        skipped_count=skipped_count,
        income_count=len(
            income_transactions
        ),
        expense_count=len(
            expense_transactions
        ),
        income_total=float(
            income_total
        ),
        expense_total=float(
            expense_total
        ),
        net_total=float(
            income_total
            - expense_total
        ),
        first_due_date=(
            candidates[0].due_date
            if candidates
            else None
        ),
        last_due_date=(
            candidates[-1].due_date
            if candidates
            else None
        ),
        closed_months=closed_months,
        requires_closed_month_confirmation=(
            len(closed_months) > 0
        ),
        sample=[
            BulkTransactionSample(
                id=transaction.id,
                description=(
                    transaction.description
                ),
                transaction_type=(
                    transaction
                    .transaction_type
                ),
                status=(
                    transaction.status
                ),
                amount=float(
                    transaction.amount
                ),
                due_date=(
                    transaction.due_date
                ),
            )
            for transaction
            in candidates[:10]
        ],
    )


def apply_bulk_transactions(
    db: Session,
    *,
    user_id: UUID,
    payload: BulkTransactionApplyInput,
) -> BulkTransactionResult:
    candidates = _load_candidates(
        db,
        user_id=user_id,
        payload=payload,
        lock_rows=True,
    )

    closed_months = _closed_months(
        db,
        user_id=user_id,
        transactions=candidates,
    )

    if (
        closed_months
        and not payload
        .confirm_closed_months
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "A operação altera a situação "
                "atual de meses fechados. "
                "Confirme explicitamente para continuar."
            ),
        )

    now = datetime.now(UTC)

    if payload.completion_date:
        completion_datetime = (
            datetime.combine(
                payload.completion_date,
                time(
                    hour=12,
                    tzinfo=UTC,
                ),
            )
        )
    else:
        completion_datetime = now

    target_status = _target_status(
        payload.action
    )

    for transaction in candidates:
        transaction.status = (
            target_status
        )
        transaction.cancelled_at = None

        if (
            target_status
            == TransactionStatus.COMPLETED
        ):
            transaction.completed_at = (
                completion_datetime
            )
        else:
            transaction.completed_at = None

    db.commit()

    selected_count = (
        len(
            set(
                payload.transaction_ids
            )
        )
        if payload.scope
        == BulkTransactionScope.SELECTED
        else len(candidates)
    )

    skipped_count = max(
        0,
        selected_count
        - len(candidates),
    )

    action_label = (
        "concluídas"
        if payload.action
        == BulkTransactionAction.COMPLETE
        else "reabertas"
    )

    return BulkTransactionResult(
        action=payload.action,
        updated_count=len(candidates),
        skipped_count=skipped_count,
        closed_months=closed_months,
        message=(
            f"{len(candidates)} "
            f"{'movimentação' if len(candidates) == 1 else 'movimentações'} "
            f"{action_label} com sucesso."
        ),
    )
