from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import (
    CORSMiddleware,
)

import app.models  # noqa: F401
from app.api.router import api_router
from app.core.observability import (
    configure_http_quality,
)
from app.core.settings import settings
from app.db.base import Base
from app.db.session import (
    SessionLocal,
    engine,
)
from app.services import ensure_admin


logging.basicConfig(
    level=(
        logging.DEBUG
        if settings.debug
        else logging.INFO
    ),
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    ),
)


@asynccontextmanager
async def lifespan(
    _: FastAPI,
):
    Base.metadata.create_all(
        bind=engine
    )

    with SessionLocal() as session:
        ensure_admin(session)

    yield

    engine.dispose()


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        description=(
            "API completa do Prumo."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=(
            settings.allowed_origins
        ),
        allow_origin_regex=(
            r"^https://.*\."
            r"(local-corp\.webcontainer\.io|"
            r"webcontainer-api\.io)$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-Process-Time-Ms",
        ],
    )

    configure_http_quality(
        application
    )

    application.include_router(
        api_router,
        prefix=settings.api_prefix,
    )

    @application.get(
        "/",
        tags=["Root"],
    )
    def root() -> dict[
        str,
        str,
    ]:
        return {
            "message":
                "Prumo API está funcionando.",
            "version":
                settings.app_version,
            "docs": "/docs",
            "health":
                f"{settings.api_prefix}/health",
        }

    return application


app = create_application()
