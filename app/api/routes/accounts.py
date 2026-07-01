from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import User
from app.structure_schemas import (
    AccountArchiveInput,
    AccountCreateInput,
    AccountDeleteInput,
    AccountManagementRead,
    AccountTransferInput,
    AccountUpdateInput,
    StructureImpactRead,
    StructureOperationResult,
)
from app.structure_service import (
    activate_account,
    archive_account,
    create_account,
    delete_account,
    get_account_impact,
    list_accounts,
    set_default_account,
    transfer_account,
    update_account,
)


router = APIRouter(
    prefix="/accounts",
    tags=["Accounts"],
)


@router.get(
    "",
    response_model=list[AccountManagementRead],
)
def get_accounts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_accounts(
        db,
        user_id=user.id,
    )


@router.post(
    "",
    response_model=AccountManagementRead,
    status_code=status.HTTP_201_CREATED,
)
def post_account(
    payload: AccountCreateInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_account(
        db,
        user_id=user.id,
        payload=payload,
    )


@router.put(
    "/{account_id}",
    response_model=AccountManagementRead,
)
def put_account(
    account_id: UUID,
    payload: AccountUpdateInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_account(
        db,
        user_id=user.id,
        account_id=account_id,
        payload=payload,
    )


@router.get(
    "/{account_id}/impact",
    response_model=StructureImpactRead,
)
def get_account_operation_impact(
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_account_impact(
        db,
        user_id=user.id,
        account_id=account_id,
    )


@router.post(
    "/{account_id}/default",
    response_model=AccountManagementRead,
)
def post_default_account(
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return set_default_account(
        db,
        user_id=user.id,
        account_id=account_id,
    )


@router.post(
    "/{account_id}/activate",
    response_model=AccountManagementRead,
)
def post_activate_account(
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return activate_account(
        db,
        user_id=user.id,
        account_id=account_id,
    )


@router.post(
    "/{account_id}/archive",
    response_model=AccountManagementRead,
)
def post_archive_account(
    account_id: UUID,
    payload: AccountArchiveInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return archive_account(
        db,
        user_id=user.id,
        account_id=account_id,
        payload=payload,
    )


@router.patch(
    "/{account_id}/deactivate",
    response_model=AccountManagementRead,
)
def compatibility_deactivate_account(
    account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return archive_account(
        db,
        user_id=user.id,
        account_id=account_id,
        payload=AccountArchiveInput(),
    )


@router.post(
    "/{account_id}/transfer",
    response_model=StructureOperationResult,
)
def post_transfer_account(
    account_id: UUID,
    payload: AccountTransferInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return transfer_account(
        db,
        user_id=user.id,
        account_id=account_id,
        payload=payload,
    )


@router.post(
    "/{account_id}/delete",
    response_model=StructureOperationResult,
)
def post_delete_account(
    account_id: UUID,
    payload: AccountDeleteInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_account(
        db,
        user_id=user.id,
        account_id=account_id,
        payload=payload,
    )
