from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy.orm import Session

from app.data_schemas import (
    ClearFinancialDataInput,
    DataExportFile,
    DataImportApplyRequest,
    DataImportPreviewRead,
    DataImportRequest,
    DataImportResultRead,
    DataMessageRead,
    DataOperationLogRead,
    DataSummaryRead,
    DeleteAccountInput,
)
from app.data_service import (
    apply_import,
    clear_financial_data,
    delete_user_account,
    export_backup_file,
    export_csv_file,
    get_data_summary,
    list_data_history,
    preview_import,
)
from app.db.session import get_db
from app.dependencies import (
    get_current_user,
)
from app.models.entities import User


router = APIRouter(
    prefix="/data",
    tags=["Data and Backup"],
)


@router.get(
    "/summary",
    response_model=DataSummaryRead,
)
def read_data_summary(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return get_data_summary(
        db,
        user_id=user.id,
    )


@router.get(
    "/export/backup",
    response_model=DataExportFile,
)
def export_backup(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return export_backup_file(
        db,
        user=user,
    )


@router.get(
    "/export/csv",
    response_model=DataExportFile,
)
def export_csv(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return export_csv_file(
        db,
        user=user,
    )


@router.post(
    "/import/preview",
    response_model=(
        DataImportPreviewRead
    ),
)
def post_import_preview(
    payload: DataImportRequest,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return preview_import(
        db,
        user_id=user.id,
        request=payload,
    )


@router.post(
    "/import/apply",
    response_model=(
        DataImportResultRead
    ),
)
def post_import_apply(
    payload: DataImportApplyRequest,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return apply_import(
        db,
        user=user,
        request=payload,
    )


@router.post(
    "/clear-financial",
    response_model=DataMessageRead,
)
def post_clear_financial(
    payload:
        ClearFinancialDataInput,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return clear_financial_data(
        db,
        user=user,
        payload=payload,
    )


@router.delete(
    "/account",
    response_model=DataMessageRead,
)
def delete_account(
    payload: DeleteAccountInput,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return delete_user_account(
        db,
        user=user,
        payload=payload,
    )


@router.get(
    "/history",
    response_model=list[
        DataOperationLogRead
    ],
)
def read_data_history(
    page: int = Query(
        default=1,
        ge=1,
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return list_data_history(
        db,
        user_id=user.id,
        page=page,
        page_size=page_size,
    )
