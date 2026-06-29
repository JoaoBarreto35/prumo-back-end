from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import MonthlyClosing, User
from app.schemas import ClosingCreate, ClosingRead
from app.services import calculate_closing

router = APIRouter(prefix="/closings", tags=["Closings"])


@router.get("", response_model=list[ClosingRead])
def list_closings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(MonthlyClosing)
        .where(MonthlyClosing.user_id == user.id)
        .order_by(MonthlyClosing.reference_month.desc())
    ).all()


@router.post("", response_model=ClosingRead)
def create_or_update_closing(
    data: ClosingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calculate_closing(db, user.id, data.reference_month, data.notes)
