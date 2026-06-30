from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.closing_schemas import (
    ClosingHistoryRead,
    ClosingMonthStatusRead,
    ClosingNotesUpdate,
    ClosingSummaryRead,
    ClosingWrite,
)
from app.closing_service import (
    close_month,
    get_month_status,
    get_month_summary,
    list_closing_history,
    reopen_month,
    update_notes,
)
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import User


router = APIRouter(
    prefix="/closings",
    tags=["Closings"],
)


@router.get(
    "",
    response_model=list[ClosingHistoryRead],
)
def get_closing_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_closing_history(
        db,
        user_id=user.id,
    )


@router.get(
    "/summary",
    response_model=ClosingSummaryRead,
)
def get_closing_summary(
    reference_month: date = Query(
        ...,
        description="Qualquer data do mês desejado.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_month_summary(
        db,
        user_id=user.id,
        reference_month=reference_month,
    )


@router.get(
    "/month-status",
    response_model=ClosingMonthStatusRead,
)
def read_month_status(
    reference_date: date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_month_status(
        db,
        user_id=user.id,
        reference_date=reference_date,
    )


@router.post(
    "/{reference_month}/close",
    response_model=ClosingSummaryRead,
)
def post_close_month(
    reference_month: date,
    payload: ClosingWrite,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return close_month(
        db,
        user_id=user.id,
        reference_month=reference_month,
        notes=payload.notes,
    )


@router.post(
    "/{reference_month}/reopen",
    response_model=ClosingSummaryRead,
)
def post_reopen_month(
    reference_month: date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return reopen_month(
        db,
        user_id=user.id,
        reference_month=reference_month,
    )


@router.put(
    "/{reference_month}/notes",
    response_model=ClosingSummaryRead,
)
def put_closing_notes(
    reference_month: date,
    payload: ClosingNotesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_notes(
        db,
        user_id=user.id,
        reference_month=reference_month,
        notes=payload.notes,
    )
