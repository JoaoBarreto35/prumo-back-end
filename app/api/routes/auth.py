from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decode_token, hash_password, verify_password
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.entities import User, UserSession
from app.models.enums import UserStatus
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserRead
from app.services import authenticate, create_defaults

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if exists:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

    user = User(name=data.name, email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    db.flush()
    create_defaults(db, user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(
            func.lower(User.email)
            == data.email.lower()
        )
    )

    if (
        user is None
        or not verify_password(
            data.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "E-mail ou senha inválidos."
            ),
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail=(
                "Acesso indisponível: "
                f"{user.status.value}."
            ),
        )

    result = authenticate(
        db,
        data.email,
        data.password,
        data.device_name,
    )

    if result is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "E-mail ou senha inválidos."
            ),
        )

    _, access, refresh = result

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
    )



@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token, "refresh")
    session = db.get(UserSession, UUID(payload["sid"]))
    if session is None or session.revoked_at is not None or session.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Sessão inválida.")

    if not verify_password(data.refresh_token, session.refresh_token_hash):
        raise HTTPException(status_code=401, detail="Refresh token inválido.")

    # Renovação simples sem validar senha novamente.
    from datetime import timedelta
    from app.core.security import create_token, hash_password
    from app.core.settings import settings
    user = db.get(User, UUID(payload["sub"]))
    access = create_token(user.id, "access", timedelta(minutes=settings.access_token_minutes), session.id)
    refresh_token = create_token(user.id, "refresh", timedelta(days=settings.refresh_token_days), session.id)
    session.refresh_token_hash = hash_password(refresh_token)
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh_token)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout", status_code=204)
def logout(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    payload = decode_token(data.refresh_token, "refresh")
    session = db.get(UserSession, UUID(payload["sid"]))
    if session:
        session.revoked_at = datetime.now(UTC)
        db.commit()
