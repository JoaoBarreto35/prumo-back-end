from datetime import UTC, datetime
from uuid import UUID

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.entities import (
    User,
    UserSession,
)
from app.models.enums import (
    UserRole,
    UserStatus,
)


bearer_scheme = HTTPBearer(
    auto_error=False
)


def get_current_user(
    credentials:
        HTTPAuthorizationCredentials
        | None = Depends(
            bearer_scheme
        ),
    db: Session = Depends(get_db),
) -> User:
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
        user_id = UUID(
            payload["sub"]
        )
        session_id = UUID(
            payload["sid"]
        )
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
            detail="Token inválido.",
        ) from exc

    session = db.get(
        UserSession,
        session_id,
    )

    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at
        is not None
        or session.expires_at
        < datetime.now(UTC)
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Sessão inválida "
                "ou encerrada."
            ),
        )

    user = db.get(
        User,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Usuário não encontrado."
            ),
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=(
                status
                .HTTP_403_FORBIDDEN
            ),
            detail=(
                "Acesso indisponível: "
                f"{user.status.value}."
            ),
        )

    return user


def require_admin(
    user: User = Depends(
        get_current_user
    ),
) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=(
                status
                .HTTP_403_FORBIDDEN
            ),
            detail=(
                "Acesso administrativo "
                "necessário."
            ),
        )

    return user
