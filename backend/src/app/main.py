"""FastAPI app factory — middleware, routers, lifespan, exception handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients.supabase import get_admin_client
from app.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.routers import (
    adherence,
    appointments,
    auth,
    chat,
    clinicians,
    clinics,
    cron,
    documents,
    feed,
    medications,
    mfa,
    notifications,
    obligations,
    patients,
    reminders,
    smart,
    staff,
    voice,
)
from app.services.a2a_retry_worker import A2ARetryWorker

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry before the FastAPI app is created."""
    if not settings.backend_sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.backend_sentry_dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release or None,
        debug=settings.sentry_debug,
        send_default_pii=False,
        traces_sample_rate=1.0 if settings.environment == "development" else 0.0,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Startup / shutdown hooks.

    Startup:  Keep external client initialization lazy so request-scoped
              access paths can create fresh clients when needed.
    Shutdown: Nothing to clean up — Supabase SDK handles it.
    """
    logger.info("Starting MediAgent backend")

    retry_worker: A2ARetryWorker | None = None
    if settings.a2a_retry_worker_enabled:
        retry_worker = A2ARetryWorker(
            db=get_admin_client(),
            poll_interval_seconds=settings.a2a_retry_poll_seconds,
            batch_size=settings.a2a_retry_batch_size,
        )
        retry_worker.start()
        logger.info("A2A retry worker enabled")

    yield  # app is running

    if retry_worker:
        await retry_worker.stop()

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
    application.include_router(cron.router, prefix=f"{api}/cron", tags=["Cron"])
    application.include_router(
        appointments.router, prefix=f"{api}/appointments", tags=["Appointments"]
    )
    application.include_router(
        notifications.router, prefix=f"{api}/notifications", tags=["Notifications"]
    )
    application.include_router(reminders.router, prefix=f"{api}/reminders", tags=["Reminders"])
    application.include_router(staff.router, prefix=f"{api}/staff", tags=["Staff"])
    application.include_router(smart.router, prefix=f"{api}/smart", tags=["SMART on FHIR"])
    application.add_api_websocket_route("/ws/chat/{patient_id}", chat.chat_websocket_endpoint)
    application.add_api_websocket_route("/ws/voice/{patient_id}", voice.voice_websocket_endpoint)

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


init_sentry()
app = create_app()
