"""FastAPI app factory — middleware, routers, lifespan, exception handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.routers import (
    adherence,
    adr,
    appointments,
    auth,
    chat,
    clinicians,
    clinics,
    documents,
    feed,
    medications,
    mfa,
    notifications,
    obligations,
    patients,
    staff,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup / shutdown hooks.

    Startup:  Keep external client initialization lazy so request-scoped
              access paths can create fresh clients when needed.
    Shutdown: Nothing to clean up — Supabase SDK handles it.
    """
    logger.info("Starting MediAgent backend")

    yield  # app is running

    logger.info("Shutting down MediAgent backend")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""

    application = FastAPI(
        title="MediAgent API",
        description=(
            "Multi-Agent Healthcare AI Platform — Patient Portal + Clinician Portal backend."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware ───────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ──────────────────────────────
    register_exception_handlers(application)

    # ── Routers ─────────────────────────────────────────
    api = "/api/v1"
    application.include_router(auth.router, prefix=f"{api}/auth", tags=["Auth"])
    application.include_router(mfa.router, prefix=f"{api}/auth/mfa", tags=["MFA"])
    application.include_router(clinics.router, prefix=f"{api}/clinics", tags=["Clinics"])
    application.include_router(patients.router, prefix=f"{api}/patients", tags=["Patients"])
    application.include_router(clinicians.router, prefix=f"{api}/clinicians", tags=["Clinicians"])
    application.include_router(documents.router, prefix=f"{api}/documents", tags=["Documents"])
    application.include_router(
        medications.router, prefix=f"{api}/medications", tags=["Medications"]
    )
    application.include_router(
        obligations.router, prefix=f"{api}/obligations", tags=["Obligations"]
    )
    application.include_router(adherence.router, prefix=f"{api}/adherence", tags=["Adherence"])
    application.include_router(chat.router, prefix=f"{api}/chat", tags=["Chat"])
    application.include_router(feed.router, prefix=f"{api}/feed", tags=["Feed"])
    application.include_router(adr.router, prefix=f"{api}/adr", tags=["ADR"])
    application.include_router(
        appointments.router, prefix=f"{api}/appointments", tags=["Appointments"]
    )
    application.include_router(
        notifications.router, prefix=f"{api}/notifications", tags=["Notifications"]
    )
    application.include_router(staff.router, prefix=f"{api}/staff", tags=["Staff"])

    # ── Health Check ────────────────────────────────────
    @application.get("/health", tags=["Health"])
    async def health_check() -> Any:
        """Health check endpoint for Cloud Run and monitoring.

        Returns service status and name for load balancer health checks.
        """
        return {"status": "healthy", "service": "mediagent-backend"}

    @application.get("/version", tags=["Health"])
    async def version() -> Any:
        """API version endpoint."""
        return {"version": "0.1.0", "service": "mediagent-backend"}

    return application


app = create_app()
