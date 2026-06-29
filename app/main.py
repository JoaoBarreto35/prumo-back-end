from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.router import api_router
from app.core.settings import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services import ensure_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        ensure_admin(session)

    yield

    engine.dispose()


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        description="API completa do Prumo.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=(
            r"^https://.*\."
            r"(local-corp\.webcontainer\.io|webcontainer-api\.io)$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(
        api_router,
        prefix=settings.api_prefix,
    )

    @application.get("/", tags=["Root"])
    def root() -> dict[str, str]:
        return {
            "message": "Prumo API está funcionando.",
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
        }

    return application


app = create_application()
