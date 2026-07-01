from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import (
    get_current_user,
)
from app.models.entities import User
from app.onboarding_schemas import (
    OnboardingMessageRead,
    OnboardingProgressUpdate,
    OnboardingRead,
)
from app.onboarding_service import (
    complete_onboarding,
    get_onboarding,
    restart_onboarding,
    save_progress,
    skip_onboarding,
)


router = APIRouter(
    prefix="/onboarding",
    tags=["Onboarding"],
)


@router.get(
    "",
    response_model=OnboardingRead,
)
def read_onboarding(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return get_onboarding(
        db,
        user_id=user.id,
    )


@router.put(
    "/progress",
    response_model=OnboardingRead,
)
def put_onboarding_progress(
    payload:
        OnboardingProgressUpdate,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return save_progress(
        db,
        user_id=user.id,
        payload=payload,
    )


@router.post(
    "/complete",
    response_model=(
        OnboardingMessageRead
    ),
)
def post_complete_onboarding(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return complete_onboarding(
        db,
        user_id=user.id,
    )


@router.post(
    "/skip",
    response_model=(
        OnboardingMessageRead
    ),
)
def post_skip_onboarding(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return skip_onboarding(
        db,
        user_id=user.id,
    )


@router.post(
    "/restart",
    response_model=(
        OnboardingMessageRead
    ),
)
def post_restart_onboarding(
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return restart_onboarding(
        db,
        user_id=user.id,
    )
