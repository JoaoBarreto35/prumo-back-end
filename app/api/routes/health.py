from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import settings
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database: Literal["ok", "error"]


@router.get("", response_model=HealthResponse)
def health_check():
    database: Literal["ok", "error"] = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database = "error"

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        database=database,
    )
