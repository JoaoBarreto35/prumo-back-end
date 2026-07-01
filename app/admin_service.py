from __future__ import annotations

import math
import secrets
import string
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.admin_models import AdminAuditLog
from app.admin_schemas import (
    AdminAction,
    AdminAuditListRead,
    AdminAuditRead,
    AdminMessageRead,
    AdminRoleUpdate,
    AdminSessionListRead,
    AdminSessionRead,
    AdminStatusUpdate,
    AdminUserListRead,
    AdminUserRead,
    AdminUserSummary,
    TemporaryPasswordRead,
)
from app.core.security import hash_password
from app.models.entities import (
    Account,
    Category,
    Transaction,
    User,
    UserSession,
)
from app.models.enums import UserRole, UserStatus


def _now() -> datetime:
    return datetime.now(UTC)


def _get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )

    return user


def _ensure_not_self(
    admin: User,
    target: User,
    action_label: str,
) -> None:
    if admin.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Você não pode {action_label} "
                "a própria conta por esta tela."
            ),
        )


def _active_admin_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.status == UserStatus.ACTIVE,
            )
        )
        or 0
    )


def _protect_last_active_admin(
    db: Session,
    *,
    target: User,
    next_status: UserStatus | None = None,
    next_role: UserRole | None = None,
) -> None:
    currently_active_admin = (
        target.role == UserRole.ADMIN
        and target.status == UserStatus.ACTIVE
    )

    final_role = next_role if next_role is not None else target.role
    final_status = next_status if next_status is not None else target.status
    remains_active_admin = (
        final_role == UserRole.ADMIN
        and final_status == UserStatus.ACTIVE
    )

    if (
        currently_active_admin
        and not remains_active_admin
        and _active_admin_count(db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Não é possível remover, suspender ou rejeitar "
                "o último administrador ativo."
            ),
        )


def _revoke_active_sessions(
    db: Session,
    *,
    user_id: UUID,
) -> int:
    now = _now()

    sessions = list(
        db.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
    )

    for session in sessions:
        session.revoked_at = now

    return len(sessions)


def _audit(
    db: Session,
    *,
    admin: User,
    target: User | None,
    action: AdminAction,
    metadata: dict,
) -> None:
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            target_user_id=target.id if target else None,
            action=action.value,
            metadata_json=metadata,
        )
    )


def _generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"

    while True:
        password = "".join(
            secrets.choice(alphabet)
            for _ in range(length)
        )

        if (
            any(character.islower() for character in password)
            and any(character.isupper() for character in password)
            and any(character.isdigit() for character in password)
            and any(character in "!@#$%&*" for character in password)
        ):
            return password


def _count_users_by_status(
    db: Session,
    user_status: UserStatus,
) -> int:
    return int(
        db.scalar(
            select(func.count(User.id)).where(
                User.status == user_status
            )
        )
        or 0
    )


def list_users(
    db: Session,
    *,
    admin: User,
    search: str | None,
    user_status: UserStatus | None,
    role: UserRole | None,
    page: int,
    page_size: int,
) -> AdminUserListRead:
    now = _now()

    account_count = (
        select(func.count(Account.id))
        .where(Account.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    category_count = (
        select(func.count(Category.id))
        .where(Category.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    transaction_count = (
        select(func.count(Transaction.id))
        .where(Transaction.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    active_session_count = (
        select(func.count(UserSession.id))
        .where(
            UserSession.user_id == User.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .correlate(User)
        .scalar_subquery()
    )

    conditions = []

    if search and search.strip():
        normalized = search.strip().lower()
        conditions.append(
            or_(
                func.lower(User.name).contains(normalized),
                func.lower(User.email).contains(normalized),
            )
        )

    if user_status is not None:
        conditions.append(User.status == user_status)

    if role is not None:
        conditions.append(User.role == role)

    count_query = select(func.count(User.id))

    if conditions:
        count_query = count_query.where(and_(*conditions))

    total = int(db.scalar(count_query) or 0)

    query = select(
        User,
        account_count.label("account_count"),
        category_count.label("category_count"),
        transaction_count.label("transaction_count"),
        active_session_count.label("active_session_count"),
    )

    if conditions:
        query = query.where(and_(*conditions))

    rows = db.execute(
        query
        .order_by(
            User.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        AdminUserRead(
            id=user.id,
            name=user.name,
            email=user.email,
            status=user.status,
            role=user.role,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
            account_count=int(account_total),
            category_count=int(category_total),
            transaction_count=int(transaction_total),
            active_session_count=int(session_total),
            is_current_admin=user.id == admin.id,
        )
        for (
            user,
            account_total,
            category_total,
            transaction_total,
            session_total,
        ) in rows
    ]

    active_sessions = int(
        db.scalar(
            select(func.count(UserSession.id)).where(
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
        or 0
    )

    summary = AdminUserSummary(
        total=int(
            db.scalar(select(func.count(User.id))) or 0
        ),
        pending=_count_users_by_status(db, UserStatus.PENDING),
        active=_count_users_by_status(db, UserStatus.ACTIVE),
        rejected=_count_users_by_status(db, UserStatus.REJECTED),
        suspended=_count_users_by_status(db, UserStatus.SUSPENDED),
        admins=int(
            db.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.ADMIN
                )
            )
            or 0
        ),
        active_sessions=active_sessions,
    )

    return AdminUserListRead(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, math.ceil(total / page_size)),
        summary=summary,
    )


def update_user_status(
    db: Session,
    *,
    admin: User,
    user_id: UUID,
    payload: AdminStatusUpdate,
) -> AdminMessageRead:
    target = _get_user(db, user_id)

    _ensure_not_self(
        admin,
        target,
        "alterar o status da",
    )

    if target.status == payload.status:
        return AdminMessageRead(
            message=(
                "O usuário já está com status "
                f"{payload.status.value}."
            )
        )

    _protect_last_active_admin(
        db,
        target=target,
        next_status=payload.status,
    )

    previous_status = target.status
    target.status = payload.status

    revoked_count = 0

    if payload.status != UserStatus.ACTIVE:
        revoked_count = _revoke_active_sessions(
            db,
            user_id=target.id,
        )

    _audit(
        db,
        admin=admin,
        target=target,
        action=AdminAction.STATUS_CHANGED,
        metadata={
            "from": previous_status.value,
            "to": payload.status.value,
            "reason": payload.reason,
            "sessions_revoked": revoked_count,
        },
    )

    db.commit()

    return AdminMessageRead(
        message=(
            "Status atualizado para "
            f"{payload.status.value}."
        )
    )


def update_user_role(
    db: Session,
    *,
    admin: User,
    user_id: UUID,
    payload: AdminRoleUpdate,
) -> AdminMessageRead:
    target = _get_user(db, user_id)

    _ensure_not_self(
        admin,
        target,
        "alterar a função da",
    )

    if target.role == payload.role:
        return AdminMessageRead(
            message=(
                "O usuário já possui a função "
                f"{payload.role.value}."
            )
        )

    if (
        payload.role == UserRole.ADMIN
        and target.status != UserStatus.ACTIVE
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Apenas usuários ativos podem "
                "se tornar administradores."
            ),
        )

    _protect_last_active_admin(
        db,
        target=target,
        next_role=payload.role,
    )

    previous_role = target.role
    target.role = payload.role

    _audit(
        db,
        admin=admin,
        target=target,
        action=AdminAction.ROLE_CHANGED,
        metadata={
            "from": previous_role.value,
            "to": payload.role.value,
            "reason": payload.reason,
        },
    )

    db.commit()

    return AdminMessageRead(
        message=(
            "Função atualizada para "
            f"{payload.role.value}."
        )
    )


def reset_temporary_password(
    db: Session,
    *,
    admin: User,
    user_id: UUID,
) -> TemporaryPasswordRead:
    target = _get_user(db, user_id)

    _ensure_not_self(
        admin,
        target,
        "redefinir a senha da",
    )

    temporary_password = _generate_temporary_password()

    target.password_hash = hash_password(temporary_password)
    target.must_change_password = True

    revoked_count = _revoke_active_sessions(
        db,
        user_id=target.id,
    )

    _audit(
        db,
        admin=admin,
        target=target,
        action=AdminAction.TEMPORARY_PASSWORD_RESET,
        metadata={
            "sessions_revoked": revoked_count,
        },
    )

    db.commit()

    return TemporaryPasswordRead(
        user_id=target.id,
        temporary_password=temporary_password,
        must_change_password=True,
        sessions_revoked=revoked_count,
    )


def list_user_sessions(
    db: Session,
    *,
    user_id: UUID,
) -> AdminSessionListRead:
    _get_user(db, user_id)
    now = _now()

    sessions = list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.created_at.desc())
            .limit(100)
        )
    )

    items = [
        AdminSessionRead(
            id=session.id,
            device_name=session.device_name,
            created_at=session.created_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            is_active=(
                session.revoked_at is None
                and session.expires_at > now
            ),
        )
        for session in sessions
    ]

    return AdminSessionListRead(
        items=items,
        active_count=sum(
            1 for item in items if item.is_active
        ),
    )


def revoke_user_session(
    db: Session,
    *,
    admin: User,
    user_id: UUID,
    session_id: UUID,
) -> AdminMessageRead:
    target = _get_user(db, user_id)

    _ensure_not_self(
        admin,
        target,
        "encerrar sessões da",
    )

    session = db.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == target.id,
        )
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada.",
        )

    if (
        session.revoked_at is None
        and session.expires_at > _now()
    ):
        session.revoked_at = _now()

    _audit(
        db,
        admin=admin,
        target=target,
        action=AdminAction.SESSION_REVOKED,
        metadata={
            "session_id": str(session.id),
            "device_name": session.device_name,
        },
    )

    db.commit()

    return AdminMessageRead(
        message="Sessão encerrada."
    )


def revoke_all_user_sessions(
    db: Session,
    *,
    admin: User,
    user_id: UUID,
) -> AdminMessageRead:
    target = _get_user(db, user_id)

    _ensure_not_self(
        admin,
        target,
        "encerrar sessões da",
    )

    revoked_count = _revoke_active_sessions(
        db,
        user_id=target.id,
    )

    _audit(
        db,
        admin=admin,
        target=target,
        action=AdminAction.ALL_SESSIONS_REVOKED,
        metadata={
            "sessions_revoked": revoked_count,
        },
    )

    db.commit()

    return AdminMessageRead(
        message=(
            f"{revoked_count} "
            f"{'sessão encerrada' if revoked_count == 1 else 'sessões encerradas'}."
        )
    )


def list_audit_logs(
    db: Session,
    *,
    page: int,
    page_size: int,
    action: AdminAction | None,
    target_user_id: UUID | None,
) -> AdminAuditListRead:
    admin_alias = aliased(User)
    target_alias = aliased(User)

    conditions = []

    if action is not None:
        conditions.append(
            AdminAuditLog.action == action.value
        )

    if target_user_id is not None:
        conditions.append(
            AdminAuditLog.target_user_id == target_user_id
        )

    count_query = select(func.count(AdminAuditLog.id))

    if conditions:
        count_query = count_query.where(and_(*conditions))

    total = int(db.scalar(count_query) or 0)

    query = (
        select(
            AdminAuditLog,
            admin_alias.name.label("admin_name"),
            target_alias.name.label("target_name"),
        )
        .join(
            admin_alias,
            admin_alias.id == AdminAuditLog.admin_user_id,
        )
        .outerjoin(
            target_alias,
            target_alias.id == AdminAuditLog.target_user_id,
        )
    )

    if conditions:
        query = query.where(and_(*conditions))

    rows = db.execute(
        query
        .order_by(AdminAuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        AdminAuditRead(
            id=log.id,
            admin_user_id=log.admin_user_id,
            admin_name=admin_name,
            target_user_id=log.target_user_id,
            target_name=target_name,
            action=AdminAction(log.action),
            metadata=log.metadata_json,
            created_at=log.created_at,
        )
        for (
            log,
            admin_name,
            target_name,
        ) in rows
    ]

    return AdminAuditListRead(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, math.ceil(total / page_size)),
    )
