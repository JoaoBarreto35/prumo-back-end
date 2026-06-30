from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import (
    Account,
    Category,
    Transaction,
    TransactionGroup,
    User,
)
from app.models.enums import (
    GroupType,
    TransactionStatus,
)
from app.schemas import (
    GroupCreate,
    GroupRead,
    TransactionRead,
    TransactionStatusUpdate,
)
from app.services import (
    create_group,
    refresh_recurring_groups,
)
from app.transaction_list_schemas import TransactionListRead


router = APIRouter(tags=["Transactions"])


@router.post(
    "/transaction-groups",
    response_model=GroupRead,
    status_code=201,
)
def create_transaction_group(
    data: GroupCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        group = create_group(
            db,
            user.id,
            data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return db.scalar(
        select(TransactionGroup)
        .options(
            selectinload(
                TransactionGroup.transactions,
            )
        )
        .where(
            TransactionGroup.id == group.id,
        )
    )


@router.get(
    "/transaction-groups",
    response_model=list[GroupRead],
)
def list_groups(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_recurring_groups(
        db,
        user.id,
    )

    return db.scalars(
        select(TransactionGroup)
        .options(
            selectinload(
                TransactionGroup.transactions,
            )
        )
        .where(
            TransactionGroup.user_id == user.id,
        )
        .order_by(
            TransactionGroup.created_at.desc(),
        )
    ).unique().all()


@router.delete(
    "/transaction-groups/{group_id}",
    status_code=204,
)
def delete_group(
    group_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.scalar(
        select(TransactionGroup).where(
            TransactionGroup.id == group_id,
            TransactionGroup.user_id == user.id,
        )
    )

    if group is None:
        raise HTTPException(
            status_code=404,
            detail="Grupo não encontrado.",
        )

    db.delete(group)
    db.commit()


@router.get(
    "/transactions",
    response_model=list[TransactionListRead],
)
def list_transactions(
    status: TransactionStatus | None = None,
    account_id: UUID | None = None,
    group_type: GroupType | None = None,
    search: str | None = Query(
        default=None,
        min_length=1,
        max_length=120,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionListRead]:
    refresh_recurring_groups(
        db,
        user.id,
    )

    group_transaction = aliased(Transaction)

    total_occurrences = (
        select(
            func.count(group_transaction.id)
        )
        .where(
            group_transaction.group_id
            == TransactionGroup.id
        )
        .correlate(TransactionGroup)
        .scalar_subquery()
    )

    query = (
        select(
            Transaction,
            TransactionGroup.group_type,
            TransactionGroup.is_active,
            Account.name.label("account_name"),
            Category.name.label("category_name"),
            total_occurrences.label(
                "total_occurrences"
            ),
        )
        .join(
            TransactionGroup,
            TransactionGroup.id
            == Transaction.group_id,
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
            Transaction.user_id == user.id,
        )
    )

    if status is not None:
        query = query.where(
            Transaction.status == status,
        )

    if account_id is not None:
        query = query.where(
            Transaction.account_id == account_id,
        )

    if group_type is not None:
        query = query.where(
            TransactionGroup.group_type
            == group_type,
        )

    normalized_search = (
        search.strip()
        if search
        else ""
    )

    if normalized_search:
        pattern = f"%{normalized_search}%"

        query = query.where(
            or_(
                Transaction.description.ilike(
                    pattern
                ),
                Account.name.ilike(pattern),
                Category.name.ilike(pattern),
            )
        )

    rows = db.execute(
        query
        .order_by(
            Transaction.due_date.asc(),
            Transaction.description.asc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return [
        TransactionListRead(
            id=transaction.id,
            group_id=transaction.group_id,
            account_id=transaction.account_id,
            category_id=transaction.category_id,
            account_name=account_name,
            category_name=category_name,
            transaction_type=(
                transaction.transaction_type
            ),
            group_type=group_type_value,
            description=transaction.description,
            amount=transaction.amount,
            status=transaction.status,
            occurrence_date=(
                transaction.occurrence_date
            ),
            due_date=transaction.due_date,
            sequence_number=(
                transaction.sequence_number
            ),
            total_occurrences=int(
                occurrence_count
            ),
            is_group_active=is_group_active,
        )
        for (
            transaction,
            group_type_value,
            is_group_active,
            account_name,
            category_name,
            occurrence_count,
        ) in rows
    ]


@router.patch(
    "/transactions/{transaction_id}/status",
    response_model=TransactionRead,
)
def update_status(
    transaction_id: UUID,
    data: TransactionStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
    )

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Movimentação não encontrada.",
        )

    transaction.status = data.status

    if (
        data.status
        == TransactionStatus.COMPLETED
    ):
        transaction.completed_at = (
            data.completed_at
            or datetime.now(UTC)
        )
        transaction.cancelled_at = None
    elif (
        data.status
        == TransactionStatus.CANCELLED
    ):
        transaction.cancelled_at = (
            datetime.now(UTC)
        )
        transaction.completed_at = None
    else:
        transaction.completed_at = None
        transaction.cancelled_at = None

    db.commit()
    db.refresh(transaction)

    return transaction
