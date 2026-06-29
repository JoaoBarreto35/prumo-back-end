from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import Category, User
from app.schemas import CategoryCreate, CategoryRead

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Category).where(Category.user_id == user.id).order_by(Category.name)).all()


@router.post("", response_model=CategoryRead, status_code=201)
def create_category(data: CategoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = Category(user_id=user.id, **data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category
