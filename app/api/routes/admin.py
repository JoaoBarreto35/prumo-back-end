from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin_schemas import (
    AdminAction,
    AdminAuditListRead,
    AdminMessageRead,
    AdminRoleUpdate,
    AdminSessionListRead,
    AdminStatusUpdate,
    AdminUserListRead,
    TemporaryPasswordRead,
)
from app.admin_service import (
    list_audit_logs,
    list_user_sessions,
    list_users,
    reset_temporary_password,
    revoke_all_user_sessions,
    revoke_user_session,
    update_user_role,
    update_user_status,
)
from app.db.session import get_db
from app.dependencies import require_admin
from app.models.entities import User
from app.models.enums import UserRole, UserStatus


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


@router.get(
    "/users",
    response_model=AdminUserListRead,
)
def get_users(
    search: str | None = None,
    user_status: UserStatus | None = Query(
        default=None,
        alias="status",
    ),
    role: UserRole | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_users(
        db,
        admin=admin,
        search=search,
        user_status=user_status,
        role=role,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/users/{user_id}/status",
    response_model=AdminMessageRead,
)
def patch_user_status(
    user_id: UUID,
    payload: AdminStatusUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_status(
        db,
        admin=admin,
        user_id=user_id,
        payload=payload,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminMessageRead,
)
def patch_user_role(
    user_id: UUID,
    payload: AdminRoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_role(
        db,
        admin=admin,
        user_id=user_id,
        payload=payload,
    )


@router.post(
    "/users/{user_id}/temporary-password",
    response_model=TemporaryPasswordRead,
)
def post_temporary_password(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return reset_temporary_password(
        db,
        admin=admin,
        user_id=user_id,
    )


@router.get(
    "/users/{user_id}/sessions",
    response_model=AdminSessionListRead,
)
def get_user_sessions(
    user_id: UUID,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_user_sessions(
        db,
        user_id=user_id,
    )


@router.delete(
    "/users/{user_id}/sessions",
    response_model=AdminMessageRead,
)
def delete_user_sessions(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return revoke_all_user_sessions(
        db,
        admin=admin,
        user_id=user_id,
    )


@router.delete(
    "/users/{user_id}/sessions/{session_id}",
    response_model=AdminMessageRead,
)
def delete_user_session(
    user_id: UUID,
    session_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return revoke_user_session(
        db,
        admin=admin,
        user_id=user_id,
        session_id=session_id,
    )


@router.get(
    "/audit",
    response_model=AdminAuditListRead,
)
def get_audit_logs(
    action: AdminAction | None = None,
    target_user_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_audit_logs(
        db,
        page=page,
        page_size=page_size,
        action=action,
        target_user_id=target_user_id,
    )
