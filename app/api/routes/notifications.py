from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import User
from app.notification_schemas import (
    NotificationCountRead,
    NotificationListRead,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationSnoozeInput,
    NotificationSyncRead,
)
from app.notification_service import (
    dismiss_notification,
    get_preferences,
    get_unread_count,
    list_notifications,
    mark_all_as_read,
    mark_as_read,
    snooze_notification,
    sync_notifications,
    update_preferences,
)


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


@router.get(
    "",
    response_model=NotificationListRead,
)
def get_notifications(
    unread_only: bool = False,
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return list_notifications(
        db,
        user_id=user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/unread-count",
    response_model=NotificationCountRead,
)
def get_count(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return get_unread_count(
        db,
        user_id=user.id,
    )


@router.post(
    "/sync",
    response_model=NotificationSyncRead,
)
def post_sync(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return sync_notifications(
        db,
        user_id=user.id,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationRead,
)
def patch_read(
    notification_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return mark_as_read(
        db,
        notification_id=notification_id,
        user_id=user.id,
    )


@router.post(
    "/read-all",
    response_model=NotificationCountRead,
)
def post_read_all(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return mark_all_as_read(
        db,
        user_id=user.id,
    )


@router.post(
    "/{notification_id}/snooze",
    response_model=NotificationRead,
)
def post_snooze(
    notification_id: UUID,
    payload: NotificationSnoozeInput,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return snooze_notification(
        db,
        notification_id=notification_id,
        user_id=user.id,
        days=payload.days,
    )


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_notification(
    notification_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    dismiss_notification(
        db,
        notification_id=notification_id,
        user_id=user.id,
    )

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )


@router.get(
    "/preferences/me",
    response_model=NotificationPreferenceRead,
)
def get_my_preferences(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return get_preferences(
        db,
        user_id=user.id,
    )


@router.put(
    "/preferences/me",
    response_model=NotificationPreferenceRead,
)
def put_my_preferences(
    payload: NotificationPreferenceUpdate,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return update_preferences(
        db,
        user_id=user.id,
        payload=payload,
    )
