from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import (
    JSONResponse,
)
from starlette.middleware.base import (
    BaseHTTPMiddleware,
)
from starlette.middleware.gzip import (
    GZipMiddleware,
)


logger = logging.getLogger(
    "prumo.http"
)


class RequestContextMiddleware(
    BaseHTTPMiddleware,
):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ):
        request_id = (
            request.headers.get(
                "X-Request-ID",
            )
            or str(uuid4())
        )
        started_at = (
            time.perf_counter()
        )

        request.state.request_id = (
            request_id
        )

        response = await call_next(
            request
        )

        elapsed_ms = round(
            (
                time.perf_counter()
                - started_at
            )
            * 1000,
            2,
        )

        response.headers[
            "X-Request-ID"
        ] = request_id
        response.headers[
            "X-Process-Time-Ms"
        ] = str(elapsed_ms)
        response.headers[
            "X-Content-Type-Options"
        ] = "nosniff"
        response.headers[
            "X-Frame-Options"
        ] = "DENY"
        response.headers[
            "Referrer-Policy"
        ] = "strict-origin-when-cross-origin"
        response.headers[
            "Permissions-Policy"
        ] = (
            "camera=(), microphone=(), "
            "geolocation=()"
        )

        logger.info(
            "%s %s -> %s em %sms [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )

        return response


def _request_id(
    request: Request,
) -> str:
    return getattr(
        request.state,
        "request_id",
        str(uuid4()),
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id":
                _request_id(request),
        },
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        content={
            "detail":
                "Os dados enviados "
                "não são válidos.",
            "errors": exc.errors(),
            "request_id":
                _request_id(request),
        },
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    request_id = _request_id(
        request
    )

    logger.exception(
        "Erro não tratado [%s]",
        request_id,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail":
                "Ocorreu um erro interno. "
                "Tente novamente.",
            "request_id":
                request_id,
        },
    )


def configure_http_quality(
    application: FastAPI,
) -> None:
    application.add_middleware(
        GZipMiddleware,
        minimum_size=1000,
    )
    application.add_middleware(
        RequestContextMiddleware,
    )

    application.add_exception_handler(
        HTTPException,
        http_exception_handler,
    )
    application.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    application.add_exception_handler(
        Exception,
        unexpected_exception_handler,
    )
