from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
)
from sqlalchemy.orm import Session

from app.core.security import (
    decode_token,
)
from app.db.session import get_db
from app.dependencies import (
    bearer_scheme,
    get_current_user,
)
from app.models import User
from app.settings_schemas import (
    ChangePasswordInput,
    MessageRead,
    ProfileRead,
    ProfileUpdate,
    SecurityOverviewRead,
    UserPreferenceRead,
    UserPreferenceUpdate,
)
from app.settings_service import (
    change_password,
    get_preferences,
    get_profile,
    list_sessions,
    revoke_other_sessions,
    revoke_session,
    update_preferences,
    update_profile,
)


router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
)


def get_current_session_id(
    credentials:
        HTTPAuthorizationCredentials
        | None = Depends(
            bearer_scheme
        ),
) -> UUID:
    if credentials is None:
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Autenticação necessária."
            ),
        )

    payload = decode_token(
        credentials.credentials,
        "access",
    )

    try:
        return UUID(payload["sid"])
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Sessão inválida."
            ),
        ) from exc


@router.get(
    "/profile",
    response_model=ProfileRead,
)
def read_profile(
    user: User = Depends(
        get_current_user
    ),
):
    return get_profile(user)


@router.put(
    "/profile",
    response_model=ProfileRead,
)
def put_profile(
    payload: ProfileUpdate,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return update_profile(
        db,
        user=user,
        payload=payload,
    )


@router.get(
    "/preferences",
    response_model=UserPreferenceRead,
)
def read_preferences(
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
    "/preferences",
    response_model=UserPreferenceRead,
)
def put_preferences(
    payload: UserPreferenceUpdate,
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


@router.get(
    "/security",
    response_model=SecurityOverviewRead,
)
def read_security(
    user: User = Depends(
        get_current_user
    ),
    current_session_id: UUID = Depends(
        get_current_session_id
    ),
    db: Session = Depends(get_db),
):
    return list_sessions(
        db,
        user_id=user.id,
        current_session_id=(
            current_session_id
        ),
    )


@router.put(
    "/password",
    response_model=MessageRead,
)
def put_password(
    payload: ChangePasswordInput,
    user: User = Depends(
        get_current_user
    ),
    current_session_id: UUID = Depends(
        get_current_session_id
    ),
    db: Session = Depends(get_db),
):
    return change_password(
        db,
        user=user,
        current_session_id=(
            current_session_id
        ),
        payload=payload,
    )


@router.delete(
    "/sessions/others",
    response_model=MessageRead,
)
def delete_other_sessions(
    user: User = Depends(
        get_current_user
    ),
    current_session_id: UUID = Depends(
        get_current_session_id
    ),
    db: Session = Depends(get_db),
):
    return revoke_other_sessions(
        db,
        user_id=user.id,
        current_session_id=(
            current_session_id
        ),
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageRead,
)
def delete_session(
    session_id: UUID,
    user: User = Depends(
        get_current_user
    ),
    current_session_id: UUID = Depends(
        get_current_session_id
    ),
    db: Session = Depends(get_db),
):
    return revoke_session(
        db,
        user_id=user.id,
        current_session_id=(
            current_session_id
        ),
        session_id=session_id,
    )
