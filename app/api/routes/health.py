from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.settings import settings


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get(
    "",
    response_model=HealthResponse,
    summary="Verificar disponibilidade da API",
)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )