from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import Account, User
from app.schemas import AccountCreate, AccountRead

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("", response_model=list[AccountRead])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.name)).all()


@router.post("", response_model=AccountRead, status_code=201)
def create_account(data: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.is_default:
        db.execute(update(Account).where(Account.user_id == user.id).values(is_default=False))

    account = Account(user_id=user.id, **data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{account_id}/deactivate", response_model=AccountRead)
def deactivate(account_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user.id))
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    if account.is_default:
        raise HTTPException(status_code=400, detail="A conta padrão não pode ser inativada.")
    account.is_active = False
    db.commit()
    db.refresh(account)
    return account
