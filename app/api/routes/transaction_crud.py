from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import (
    Transaction,
    TransactionGroup,
    User,
)
from app.transaction_crud_schemas import (
    TransactionDeleteResult,
    TransactionDetailRead,
    TransactionEditInput,
    TransactionEditResult,
    TransactionGroupActiveResult,
    UpdateScope,
)
from app.transaction_crud_service import (
    count_group_transactions,
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionDetailRead:
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimentação não encontrada.",
        )

    group = db.scalar(
        select(TransactionGroup).where(
            TransactionGroup.id == transaction.group_id,
            TransactionGroup.user_id == user.id,
        )
    )

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grupo da movimentação não encontrado.",
        )

    return TransactionDetailRead(
        id=transaction.id,
        group_id=transaction.group_id,
        account_id=transaction.account_id,
        category_id=transaction.category_id,
        transaction_type=transaction.transaction_type,
        description=transaction.description,
        amount=transaction.amount,
        status=transaction.status,
        occurrence_date=transaction.occurrence_date,
        due_date=transaction.due_date,
        sequence_number=transaction.sequence_number,
        group_type=group.group_type,
        notes=transaction.notes or group.notes,
        total_occurrences=count_group_transactions(
            db,
            group_id=group.id,
            user_id=user.id,
        ),
        is_group_active=group.is_active,
    )


@router.patch(
    "/transactions/{transaction_id}",
    response_model=TransactionEditResult,
)
def edit_transaction(
    transaction_id: UUID,
    payload: TransactionEditInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionEditResult:
    return update_transaction(
        db,
        transaction_id=transaction_id,
        user_id=user.id,
        payload=payload,
    )


@router.delete(
    "/transactions/{transaction_id}",
    response_model=TransactionDeleteResult,
)
def remove_transaction(
    transaction_id: UUID,
    scope: UpdateScope = Query(
        default=UpdateScope.SINGLE,
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionDeleteResult:
    return delete_transaction(
        db,
        transaction_id=transaction_id,
        user_id=user.id,
        scope=scope,
    )


@router.patch(
    "/transaction-groups/{group_id}/activate",
    response_model=TransactionGroupActiveResult,
)
def activate_group(
    group_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionGroupActiveResult:
    return set_group_active(
        db,
        group_id=group_id,
        user_id=user.id,
        active=True,
    )


@router.patch(
    "/transaction-groups/{group_id}/deactivate",
    response_model=TransactionGroupActiveResult,
)
def deactivate_group(
    group_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionGroupActiveResult:
    return set_group_active(
        db,
        group_id=group_id,
        user_id=user.id,
        active=False,
    )
