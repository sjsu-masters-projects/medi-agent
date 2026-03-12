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

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

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


async def _catch_all_handler(_: Request, exc: MediAgentError) -> JSONResponse:
    """Fallback for any MediAgentError subclass we haven't explicitly handled."""
    logger.error("Unhandled app error: [%s] %s", exc.code, exc.message)
    return _error_response(500, exc.code, exc.message)


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
    app.add_exception_handler(PydanticValidationError, _pydantic_handler)  # type: ignore[arg-type]
    app.add_exception_handler(MediAgentError, _catch_all_handler)  # type: ignore[arg-type]
