"""Inicialización HTTP común, sin acceso a datos ni carga de datos iniciales."""

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def _database_failure(error: BaseException) -> SQLAlchemyError | None:
    """Find the store failure preserved by the API's exception chain."""
    visited = set()
    while error is not None and id(error) not in visited:
        visited.add(id(error))
        if isinstance(error, SQLAlchemyError):
            return error
        error = error.__cause__ or error.__context__
    return None


def create_app(component: str) -> FastAPI:
    app = FastAPI(title=f"Foodie API — {component}", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def report_http_failure(request: Request, error: HTTPException):
        failure = _database_failure(error) if error.status_code >= 500 else None
        if failure is not None:
            original = getattr(failure, "orig", None)
            sqlstate = getattr(original, "sqlstate", None)
            if not isinstance(sqlstate, str) or not re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
                sqlstate = "unknown"
            # Solo metadatos: la ruta usa marcadores, nunca valores del usuario.
            # No registrar SQL, parámetros, mensajes de excepción ni traceback.
            route = getattr(request.scope.get("route"), "path", "<unmatched>")
            logger.warning(
                "Database request failed: component=%s operation=%s %s error=%s sqlstate=%s",
                component, request.method, route, type(failure).__name__, sqlstate,
            )
        return await http_exception_handler(request, error)

    @app.get("/healthz", tags=["health"])
    def healthz():
        # Conservar el contrato que utiliza el frontend docente del monolito.
        return {"status": "ok"}

    @app.get("/api/healthz", tags=["health"])
    def component_healthz():
        return {"status": "ok", "component": component}

    return app
