from __future__ import annotations

import json
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

from app.models.entities import (
    Account,
    Category,
    Transaction,
)
from app.onboarding_models import (
    UserOnboardingState,
)
from app.onboarding_schemas import (
    OnboardingMessageRead,
    OnboardingProgressUpdate,
    OnboardingRead,
    OnboardingStatus,
)


MAX_DRAFT_BYTES = 100_000


def _now() -> datetime:
    return datetime.now(UTC)


def _state(
    db: Session,
    *,
    user_id: UUID,
) -> UserOnboardingState | None:
    return db.scalar(
        select(
            UserOnboardingState
        ).where(
            UserOnboardingState.user_id
            == user_id
        )
    )


def _counts(
    db: Session,
    *,
    user_id: UUID,
) -> tuple[int, int, int]:
    account_count = int(
        db.scalar(
            select(
                func.count(Account.id)
            ).where(
                Account.user_id
                == user_id,
                Account.is_active
                .is_(True),
            )
        )
        or 0
    )

    category_count = int(
        db.scalar(
            select(
                func.count(Category.id)
            ).where(
                Category.user_id
                == user_id,
                Category.is_active
                .is_(True),
            )
        )
        or 0
    )

    transaction_count = int(
        db.scalar(
            select(
                func.count(
                    Transaction.id
                )
            ).where(
                Transaction.user_id
                == user_id
            )
        )
        or 0
    )

    return (
        account_count,
        category_count,
        transaction_count,
    )


def _get_or_create(
    db: Session,
    *,
    user_id: UUID,
) -> UserOnboardingState:
    state = _state(
        db,
        user_id=user_id,
    )

    if state is not None:
        return state

    (
        _,
        _,
        transaction_count,
    ) = _counts(
        db,
        user_id=user_id,
    )

    now = _now()

    if transaction_count > 0:
        state = UserOnboardingState(
            user_id=user_id,
            status=(
                OnboardingStatus
                .COMPLETED.value
            ),
            current_step=6,
            completed_steps=[
                "welcome",
                "account",
                "categories",
                "income",
                "expenses",
                "tour",
            ],
            draft={},
            auto_completed=True,
            started_at=now,
            completed_at=now,
        )
    else:
        state = UserOnboardingState(
            user_id=user_id,
            status=(
                OnboardingStatus
                .NOT_STARTED.value
            ),
            current_step=1,
            completed_steps=[],
            draft={},
            auto_completed=False,
        )

    db.add(state)
    db.commit()
    db.refresh(state)

    return state


def _serialize(
    db: Session,
    *,
    user_id: UUID,
    state:
        UserOnboardingState,
) -> OnboardingRead:
    (
        account_count,
        category_count,
        transaction_count,
    ) = _counts(
        db,
        user_id=user_id,
    )

    onboarding_status = (
        OnboardingStatus(
            state.status
        )
    )

    return OnboardingRead(
        status=onboarding_status,
        current_step=(
            state.current_step
        ),
        completed_steps=list(
            state.completed_steps
            or []
        ),
        draft=dict(
            state.draft
            or {}
        ),
        account_count=account_count,
        category_count=(
            category_count
        ),
        transaction_count=(
            transaction_count
        ),
        auto_completed=(
            state.auto_completed
        ),
        needs_onboarding=(
            onboarding_status
            not in {
                OnboardingStatus
                .COMPLETED,
                OnboardingStatus
                .SKIPPED,
            }
        ),
        started_at=(
            state.started_at
        ),
        completed_at=(
            state.completed_at
        ),
        skipped_at=(
            state.skipped_at
        ),
    )


def get_onboarding(
    db: Session,
    *,
    user_id: UUID,
) -> OnboardingRead:
    state = _get_or_create(
        db,
        user_id=user_id,
    )

    return _serialize(
        db,
        user_id=user_id,
        state=state,
    )


def save_progress(
    db: Session,
    *,
    user_id: UUID,
    payload:
        OnboardingProgressUpdate,
) -> OnboardingRead:
    state = _get_or_create(
        db,
        user_id=user_id,
    )

    if state.status in {
        OnboardingStatus
        .COMPLETED.value,
        OnboardingStatus
        .SKIPPED.value,
    }:
        return _serialize(
            db,
            user_id=user_id,
            state=state,
        )

    encoded = json.dumps(
        payload.draft,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    if len(encoded) > MAX_DRAFT_BYTES:
        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=(
                "O rascunho do onboarding "
                "ficou grande demais."
            ),
        )

    now = _now()

    state.status = (
        OnboardingStatus
        .IN_PROGRESS.value
    )
    state.current_step = (
        payload.current_step
    )
    state.completed_steps = (
        payload.completed_steps
    )
    state.draft = payload.draft

    if state.started_at is None:
        state.started_at = now

    db.commit()
    db.refresh(state)

    return _serialize(
        db,
        user_id=user_id,
        state=state,
    )


def complete_onboarding(
    db: Session,
    *,
    user_id: UUID,
) -> OnboardingMessageRead:
    state = _get_or_create(
        db,
        user_id=user_id,
    )

    now = _now()

    state.status = (
        OnboardingStatus
        .COMPLETED.value
    )
    state.current_step = 6
    state.completed_steps = [
        "welcome",
        "account",
        "categories",
        "income",
        "expenses",
        "tour",
    ]
    state.completed_at = now
    state.skipped_at = None

    if state.started_at is None:
        state.started_at = now

    db.commit()
    db.refresh(state)

    return OnboardingMessageRead(
        message=(
            "Onboarding concluído. "
            "O Prumo está pronto para uso."
        ),
        onboarding=_serialize(
            db,
            user_id=user_id,
            state=state,
        ),
    )


def skip_onboarding(
    db: Session,
    *,
    user_id: UUID,
) -> OnboardingMessageRead:
    state = _get_or_create(
        db,
        user_id=user_id,
    )

    now = _now()

    state.status = (
        OnboardingStatus
        .SKIPPED.value
    )
    state.skipped_at = now

    if state.started_at is None:
        state.started_at = now

    db.commit()
    db.refresh(state)

    return OnboardingMessageRead(
        message=(
            "Onboarding pulado. "
            "Você pode retomá-lo em "
            "Configurações."
        ),
        onboarding=_serialize(
            db,
            user_id=user_id,
            state=state,
        ),
    )


def restart_onboarding(
    db: Session,
    *,
    user_id: UUID,
) -> OnboardingMessageRead:
    state = _get_or_create(
        db,
        user_id=user_id,
    )

    state.status = (
        OnboardingStatus
        .IN_PROGRESS.value
    )
    state.current_step = 1
    state.completed_steps = []
    state.draft = {}
    state.auto_completed = False
    state.started_at = _now()
    state.completed_at = None
    state.skipped_at = None

    db.commit()
    db.refresh(state)

    return OnboardingMessageRead(
        message=(
            "Onboarding reiniciado."
        ),
        onboarding=_serialize(
            db,
            user_id=user_id,
            state=state,
        ),
    )
