from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import Transaction, TransactionGroup, User
from app.models.enums import TransactionStatus
from app.schemas import GroupCreate, GroupRead, TransactionRead, TransactionStatusUpdate
from app.services import create_group, refresh_recurring_groups

router = APIRouter(tags=["Transactions"])


@router.post("/transaction-groups", response_model=GroupRead, status_code=201)
def create_transaction_group(
    data: GroupCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        group = create_group(db, user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return db.scalar(
        select(TransactionGroup)
        .options(selectinload(TransactionGroup.transactions))
        .where(TransactionGroup.id == group.id)
    )


@router.get("/transaction-groups", response_model=list[GroupRead])
def list_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refresh_recurring_groups(db, user.id)
    return db.scalars(
        select(TransactionGroup)
        .options(selectinload(TransactionGroup.transactions))
        .where(TransactionGroup.user_id == user.id)
        .order_by(TransactionGroup.created_at.desc())
    ).unique().all()


@router.delete("/transaction-groups/{group_id}", status_code=204)
def delete_group(group_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.scalar(select(TransactionGroup).where(TransactionGroup.id == group_id, TransactionGroup.user_id == user.id))
    if group is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")
    db.delete(group)
    db.commit()


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions(
    status: TransactionStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_recurring_groups(db, user.id)
    query = select(Transaction).where(Transaction.user_id == user.id)
    if status is not None:
        query = query.where(Transaction.status == status)
    return db.scalars(query.order_by(Transaction.due_date).offset(offset).limit(limit)).all()


@router.patch("/transactions/{transaction_id}/status", response_model=TransactionRead)
def update_status(
    transaction_id: UUID,
    data: TransactionStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user.id))
    if transaction is None:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada.")

    transaction.status = data.status
    if data.status == TransactionStatus.COMPLETED:
        transaction.completed_at = data.completed_at or datetime.now(UTC)
        transaction.cancelled_at = None
    elif data.status == TransactionStatus.CANCELLED:
        transaction.cancelled_at = datetime.now(UTC)
        transaction.completed_at = None
    else:
        transaction.completed_at = None
        transaction.cancelled_at = None

    db.commit()
    db.refresh(transaction)
    return transaction
