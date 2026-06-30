from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.lume_schemas import (
    LumeActionResult,
    LumeConversationRead,
    LumeMessageRead,
    LumeSendRequest,
    LumeSendResponse,
    LumeSummaryRead,
)
from app.lume_service import (
    cancel_action,
    confirm_action,
    delete_conversation,
    get_home_summary,
    list_conversations,
    list_messages,
    send_message,
)
from app.models.entities import User


router = APIRouter(
    prefix="/lume",
    tags=["Lume"],
)


@router.get(
    "/conversations",
    response_model=list[
        LumeConversationRead
    ],
)
def get_conversations(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return list_conversations(
        db,
        user_id=user.id,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[
        LumeMessageRead
    ],
)
def get_messages(
    conversation_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return list_messages(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
)
def remove_conversation(
    conversation_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    delete_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
    )
    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )


@router.post(
    "/message",
    response_model=LumeSendResponse,
)
def post_message(
    payload: LumeSendRequest,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return send_message(
        db,
        user_id=user.id,
        message=payload.message,
        conversation_id=(
            payload.conversation_id
        ),
    )


@router.post(
    "/actions/{message_id}/confirm",
    response_model=LumeActionResult,
)
def post_confirm_action(
    message_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return confirm_action(
        db,
        message_id=message_id,
        user_id=user.id,
    )


@router.post(
    "/actions/{message_id}/cancel",
    response_model=LumeActionResult,
)
def post_cancel_action(
    message_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return cancel_action(
        db,
        message_id=message_id,
        user_id=user.id,
    )


@router.get(
    "/summary",
    response_model=LumeSummaryRead,
)
def get_summary(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return get_home_summary(
        db,
        user_id=user.id,
    )
