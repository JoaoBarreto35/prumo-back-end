from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import User
from app.structure_schemas import (
    CategoryCreateInput,
    CategoryDeleteInput,
    CategoryManagementRead,
    CategoryTransferInput,
    CategoryUpdateInput,
    StructureImpactRead,
    StructureOperationResult,
)
from app.structure_service import (
    activate_category,
    archive_category,
    create_category,
    delete_category,
    get_category_impact,
    list_categories,
    transfer_category,
    update_category,
)


router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


@router.get(
    "",
    response_model=list[CategoryManagementRead],
)
def get_categories(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_categories(
        db,
        user_id=user.id,
    )


@router.post(
    "",
    response_model=CategoryManagementRead,
    status_code=status.HTTP_201_CREATED,
)
def post_category(
    payload: CategoryCreateInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_category(
        db,
        user_id=user.id,
        payload=payload,
    )


@router.put(
    "/{category_id}",
    response_model=CategoryManagementRead,
)
def put_category(
    category_id: UUID,
    payload: CategoryUpdateInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_category(
        db,
        user_id=user.id,
        category_id=category_id,
        payload=payload,
    )


@router.get(
    "/{category_id}/impact",
    response_model=StructureImpactRead,
)
def get_category_operation_impact(
    category_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_category_impact(
        db,
        user_id=user.id,
        category_id=category_id,
    )


@router.post(
    "/{category_id}/activate",
    response_model=CategoryManagementRead,
)
def post_activate_category(
    category_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return activate_category(
        db,
        user_id=user.id,
        category_id=category_id,
    )


@router.post(
    "/{category_id}/archive",
    response_model=CategoryManagementRead,
)
def post_archive_category(
    category_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return archive_category(
        db,
        user_id=user.id,
        category_id=category_id,
    )


@router.post(
    "/{category_id}/transfer",
    response_model=StructureOperationResult,
)
def post_transfer_category(
    category_id: UUID,
    payload: CategoryTransferInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return transfer_category(
        db,
        user_id=user.id,
        category_id=category_id,
        payload=payload,
    )


@router.post(
    "/{category_id}/delete",
    response_model=StructureOperationResult,
)
def post_delete_category(
    category_id: UUID,
    payload: CategoryDeleteInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_category(
        db,
        user_id=user.id,
        category_id=category_id,
        payload=payload,
    )
