from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.models import Transaction, TransactionGroup, User
from app.schemas.transaction_crud import (
    TransactionDeleteResult,
    TransactionDetailRead,
    TransactionEditInput,
    TransactionEditResult,
    UpdateScope,
)
from app.services.transaction_crud_service import (
    delete_transaction,
    set_group_active,
    update_transaction,
)


router = APIRouter(tags=["Transaction CRUD"])


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionDetailRead,
)
def get_transaction_detail(
    transaction_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = session.execute(
        select(
            Transaction,
            TransactionGroup.group_type,
            TransactionGroup.notes,
            TransactionGroup.is_active,
            func.count(Transaction.id)
            .over(partition_by=Transaction.group_id)
            .label("total_occurrences"),
        )
        .join(
            TransactionGroup,
            TransactionGroup.id == Transaction.group_id,
        )
        .where(
            Transaction.id == transaction_id,
            Transaction.user_id == current_user.id,
        )
    ).one_or_none()

    if row is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimentação não encontrada.",
        )

    transaction, group_type, notes, is_active, total_occurrences = row

    return TransactionDetailRead(
        id=transaction.id,
        group_id=transaction.group_id,
        account_id=transaction.account_id,
        category_id=transaction.category_id,
        transaction_type=str(transaction.transaction_type),
        description=transaction.description,
        amount=transaction.amount,
        status=str(transaction.status),
        occurrence_date=transaction.occurrence_date,
        due_date=transaction.due_date,
        sequence_number=transaction.sequence_number,
        group_type=str(group_type),
        notes=notes,
        total_occurrences=total_occurrences,
        is_group_active=is_active,
    )


@router.patch(
    "/transactions/{transaction_id}",
    response_model=TransactionEditResult,
)
def edit_transaction(
    transaction_id: UUID,
    payload: TransactionEditInput,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return update_transaction(
        session,
        transaction_id=transaction_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.delete(
    "/transactions/{transaction_id}",
    response_model=TransactionDeleteResult,
)
def remove_transaction(
    transaction_id: UUID,
    scope: UpdateScope = Query(default=UpdateScope.SINGLE),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return delete_transaction(
        session,
        transaction_id=transaction_id,
        user_id=current_user.id,
        scope=scope,
    )


@router.patch("/transaction-groups/{group_id}/activate")
def activate_group(
    group_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return set_group_active(
        session,
        group_id=group_id,
        user_id=current_user.id,
        active=True,
    )


@router.patch("/transaction-groups/{group_id}/deactivate")
def deactivate_group(
    group_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return set_group_active(
        session,
        group_id=group_id,
        user_id=current_user.id,
        active=False,
    )
