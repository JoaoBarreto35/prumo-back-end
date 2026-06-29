from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.models.entities import User
from app.models.enums import UserStatus
from app.schemas import UserRead

router = APIRouter(prefix="/admin/users", tags=["Admin"])


@router.get("", response_model=list[UserRead])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.created_at.desc())).all()


@router.patch("/{user_id}/approve", response_model=UserRead)
def approve_user(user_id: UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    user.status = UserStatus.ACTIVE
    db.commit()
    db.refresh(user)
    return user
