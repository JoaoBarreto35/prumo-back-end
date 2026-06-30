from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    verify_password,
)
from app.models import (
    User,
    UserSession,
)
from app.settings_schemas import (
    ChangePasswordInput,
    MessageRead,
    ProfileRead,
    ProfileUpdate,
    SecurityOverviewRead,
    UserPreferenceRead,
    UserPreferenceUpdate,
    UserSessionRead,
)
from app.user_preferences_models import (
    UserPreference,
)


def get_profile(
    user: User,
) -> ProfileRead:
    return ProfileRead.model_validate(
        user
    )


def update_profile(
    db: Session,
    *,
    user: User,
    payload: ProfileUpdate,
) -> ProfileRead:
    normalized_email = (
        payload.email
        .strip()
        .lower()
    )

    existing = db.scalar(
        select(User).where(
            func.lower(User.email)
            == normalized_email,
            User.id != user.id,
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Este e-mail já está "
                "em uso por outra conta."
            ),
        )

    user.name = payload.name.strip()
    user.email = normalized_email

    db.commit()
    db.refresh(user)

    return get_profile(user)


def get_or_create_preferences(
    db: Session,
    *,
    user_id: UUID,
) -> UserPreference:
    preference = db.scalar(
        select(UserPreference).where(
            UserPreference.user_id
            == user_id,
        )
    )

    if preference is not None:
        return preference

    preference = UserPreference(
        user_id=user_id,
    )
    db.add(preference)
    db.flush()

    return preference


def get_preferences(
    db: Session,
    *,
    user_id: UUID,
) -> UserPreferenceRead:
    preference = (
        get_or_create_preferences(
            db,
            user_id=user_id,
        )
    )

    db.commit()
    db.refresh(preference)

    return UserPreferenceRead.model_validate(
        preference
    )


def update_preferences(
    db: Session,
    *,
    user_id: UUID,
    payload: UserPreferenceUpdate,
) -> UserPreferenceRead:
    preference = (
        get_or_create_preferences(
            db,
            user_id=user_id,
        )
    )

    preference.theme = (
        payload.theme.value
    )
    preference.density = (
        payload.density.value
    )
    preference.reduce_motion = (
        payload.reduce_motion
    )
    preference.default_page = (
        payload.default_page.value
    )

    db.commit()
    db.refresh(preference)

    return UserPreferenceRead.model_validate(
        preference
    )


def list_sessions(
    db: Session,
    *,
    user_id: UUID,
    current_session_id: UUID,
) -> SecurityOverviewRead:
    now = datetime.now(UTC)

    sessions = list(
        db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id
                == user_id,
                UserSession.revoked_at
                .is_(None),
                UserSession.expires_at
                > now,
            )
            .order_by(
                UserSession.created_at
                .desc(),
            )
        )
    )

    serialized = [
        UserSessionRead(
            id=session.id,
            device_name=(
                session.device_name
            ),
            created_at=session.created_at,
            expires_at=session.expires_at,
            is_current=(
                session.id
                == current_session_id
            ),
        )
        for session in sessions
    ]

    return SecurityOverviewRead(
        sessions=serialized,
        active_session_count=len(
            serialized
        ),
    )


def revoke_session(
    db: Session,
    *,
    user_id: UUID,
    current_session_id: UUID,
    session_id: UUID,
) -> MessageRead:
    if session_id == current_session_id:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "Use Sair para encerrar "
                "a sessão atual."
            ),
        )

    session = db.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id
            == user_id,
            UserSession.revoked_at
            .is_(None),
        )
    )

    if session is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "Sessão ativa não "
                "encontrada."
            ),
        )

    session.revoked_at = datetime.now(
        UTC
    )
    db.commit()

    return MessageRead(
        message="Sessão encerrada."
    )


def revoke_other_sessions(
    db: Session,
    *,
    user_id: UUID,
    current_session_id: UUID,
) -> MessageRead:
    now = datetime.now(UTC)

    sessions = list(
        db.scalars(
            select(UserSession).where(
                UserSession.user_id
                == user_id,
                UserSession.id
                != current_session_id,
                UserSession.revoked_at
                .is_(None),
                UserSession.expires_at
                > now,
            )
        )
    )

    for session in sessions:
        session.revoked_at = now

    db.commit()

    return MessageRead(
        message=(
            f"{len(sessions)} "
            f"{'sessão encerrada' if len(sessions) == 1 else 'sessões encerradas'}."
        )
    )


def change_password(
    db: Session,
    *,
    user: User,
    current_session_id: UUID,
    payload: ChangePasswordInput,
) -> MessageRead:
    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail="Senha atual incorreta.",
        )

    user.password_hash = hash_password(
        payload.new_password
    )
    user.must_change_password = False

    now = datetime.now(UTC)

    other_sessions = list(
        db.scalars(
            select(UserSession).where(
                UserSession.user_id
                == user.id,
                UserSession.id
                != current_session_id,
                UserSession.revoked_at
                .is_(None),
                UserSession.expires_at
                > now,
            )
        )
    )

    for session in other_sessions:
        session.revoked_at = now

    db.commit()

    return MessageRead(
        message=(
            "Senha alterada com sucesso. "
            "As outras sessões foram "
            "encerradas."
        )
    )
