"""Global exception handlers — maps custom exceptions to HTTP responses.

Registered in `main.py` via `register_exception_handlers(app)`.

Every error response follows a consistent shape:
    {
        "error": {
            "code": "NOT_FOUND",
            "message": "Patient 'abc-123' not found"
        }
    }
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
    MediAgentError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Build a uniform error response."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


# ── Handlers ────────────────────────────────────────────────


async def _not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return _error_response(404, exc.code, exc.message)


async def _auth_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    return _error_response(401, exc.code, exc.message)


async def _forbidden_handler(_: Request, exc: AuthorizationError) -> JSONResponse:
    return _error_response(403, exc.code, exc.message)


async def _validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return _error_response(422, exc.code, exc.message)


async def _external_service_handler(_: Request, exc: ExternalServiceError) -> JSONResponse:
    logger.error("External service failure: %s", exc.message)
    return _error_response(502, exc.code, exc.message)


async def _pydantic_handler(_: Request, exc: PydanticValidationError) -> JSONResponse:
    """Catch Pydantic schema validation errors that slip past FastAPI."""
    return _error_response(
        422,
        "VALIDATION_ERROR",
        str(exc.errors()[0]["msg"]) if exc.errors() else "Invalid input",
    )


def _extract_validation_message(errors: Sequence[Any]) -> str:
    if not errors:
        return "Invalid input"

    first_error = errors[0]
    if not isinstance(first_error, dict):
        return "Invalid input"

    msg = str(first_error.get("msg") or "Invalid input")
    location = first_error.get("loc")
    if isinstance(location, list | tuple):
        field_parts = [
            str(part)
            for part in location
            if isinstance(part, str | int) and str(part) not in {"body", "query", "path", "header"}
        ]
        if field_parts:
            return f"{'.'.join(field_parts)}: {msg}"

    return msg


async def _request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Normalize FastAPI request validation errors to the standard envelope."""
    return _error_response(422, "VALIDATION_ERROR", _extract_validation_message(exc.errors()))


def _http_status_to_error_code(status_code: int) -> str:
    if status_code == 400:
        return "BAD_REQUEST"
    if status_code == 401:
        return "AUTHENTICATION_ERROR"
    if status_code == 403:
        return "AUTHORIZATION_ERROR"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 422:
        return "VALIDATION_ERROR"
    return "HTTP_ERROR"


async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalize explicit HTTPException raises and framework HTTP errors."""
    message = str(exc.detail) if exc.detail else HTTPStatus(exc.status_code).phrase
    return _error_response(exc.status_code, _http_status_to_error_code(exc.status_code), message)


async def _catch_all_handler(_: Request, exc: MediAgentError) -> JSONResponse:
    """Fallback for any MediAgentError subclass we haven't explicitly handled."""
    logger.error("Unhandled app error: [%s] %s", exc.code, exc.message)
    return _error_response(500, exc.code, exc.message)


async def _unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions so logs include a traceback and request context."""
    logger.exception(
        "Unhandled exception at %s %s",
        request.method,
        request.url.path,
    )
    return _error_response(500, "INTERNAL_ERROR", "Internal server error")


# ── Registration ────────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Register all handlers on the FastAPI app.

    Order matters — more specific exceptions MUST come before
    the generic MediAgentError catch-all.
    """
    app.add_exception_handler(NotFoundError, _not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AuthenticationError, _auth_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AuthorizationError, _forbidden_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ExternalServiceError, _external_service_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(PydanticValidationError, _pydantic_handler)  # type: ignore[arg-type]
    app.add_exception_handler(MediAgentError, _catch_all_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unexpected_exception_handler)  # type: ignore[arg-type]
