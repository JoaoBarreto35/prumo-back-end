from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import PlanningScenario, User
from app.planning_schemas import (
    PlanningScenarioActiveUpdate,
    PlanningScenarioRead,
    PlanningScenarioWrite,
)


router = APIRouter(
    prefix="/planning/scenarios",
    tags=["Planning"],
)


def get_owned_scenario(
    db: Session,
    *,
    scenario_id: UUID,
    user_id: UUID,
) -> PlanningScenario:
    scenario = db.scalar(
        select(PlanningScenario).where(
            PlanningScenario.id == scenario_id,
            PlanningScenario.user_id == user_id,
        )
    )

    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cenário de planejamento não encontrado.",
        )

    return scenario


@router.get(
    "",
    response_model=list[PlanningScenarioRead],
)
def list_scenarios(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(PlanningScenario)
        .where(PlanningScenario.user_id == user.id)
        .order_by(
            PlanningScenario.is_active.desc(),
            PlanningScenario.start_date.asc(),
            PlanningScenario.created_at.desc(),
        )
    ).all()


@router.post(
    "",
    response_model=PlanningScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scenario(
    payload: PlanningScenarioWrite,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scenario = PlanningScenario(
        user_id=user.id,
        **payload.model_dump(),
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.put(
    "/{scenario_id}",
    response_model=PlanningScenarioRead,
)
def update_scenario(
    scenario_id: UUID,
    payload: PlanningScenarioWrite,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scenario = get_owned_scenario(
        db,
        scenario_id=scenario_id,
        user_id=user.id,
    )

    for field, value in payload.model_dump().items():
        setattr(scenario, field, value)

    db.commit()
    db.refresh(scenario)
    return scenario


@router.patch(
    "/{scenario_id}/active",
    response_model=PlanningScenarioRead,
)
def update_scenario_active(
    scenario_id: UUID,
    payload: PlanningScenarioActiveUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scenario = get_owned_scenario(
        db,
        scenario_id=scenario_id,
        user_id=user.id,
    )
    scenario.is_active = payload.is_active
    db.commit()
    db.refresh(scenario)
    return scenario


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scenario(
    scenario_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scenario = get_owned_scenario(
        db,
        scenario_id=scenario_id,
        user_id=user.id,
    )
    db.delete(scenario)
    db.commit()
