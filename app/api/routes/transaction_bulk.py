from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import (
    get_current_user,
)
from app.models.entities import User
from app.transaction_bulk_schemas import (
    BulkTransactionApplyInput,
    BulkTransactionPreview,
    BulkTransactionRequest,
    BulkTransactionResult,
)
from app.transaction_bulk_service import (
    apply_bulk_transactions,
    preview_bulk_transactions,
)


router = APIRouter(
    prefix="/transactions-bulk",
    tags=["Transaction Bulk"],
)


@router.post(
    "/preview",
    response_model=(
        BulkTransactionPreview
    ),
)
def post_bulk_preview(
    payload: BulkTransactionRequest,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return preview_bulk_transactions(
        db,
        user_id=user.id,
        payload=payload,
    )


@router.post(
    "/apply",
    response_model=(
        BulkTransactionResult
    ),
)
def post_bulk_apply(
    payload:
        BulkTransactionApplyInput,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return apply_bulk_transactions(
        db,
        user_id=user.id,
        payload=payload,
    )
