"""FastAPI app factory — middleware, routers, lifespan."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth,
    patients,
    clinicians,
    documents,
    medications,
    obligations,
    adherence,
    chat,
    feed,
    adr,
    appointments,
    notifications,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # startup: init DB pool, warm caches, etc.
    yield
    # shutdown: close connections


def create_app() -> FastAPI:
    application = FastAPI(
        title="MediAgent API",
        description="Multi-Agent Healthcare AI Platform",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = "/api/v1"
    application.include_router(auth.router, prefix=f"{api}/auth", tags=["Auth"])
    application.include_router(patients.router, prefix=f"{api}/patients", tags=["Patients"])
    application.include_router(clinicians.router, prefix=f"{api}/clinicians", tags=["Clinicians"])
    application.include_router(documents.router, prefix=f"{api}/documents", tags=["Documents"])
    application.include_router(medications.router, prefix=f"{api}/medications", tags=["Medications"])
    application.include_router(obligations.router, prefix=f"{api}/obligations", tags=["Obligations"])
    application.include_router(adherence.router, prefix=f"{api}/adherence", tags=["Adherence"])
    application.include_router(chat.router, prefix=f"{api}/chat", tags=["Chat"])
    application.include_router(feed.router, prefix=f"{api}/feed", tags=["Feed"])
    application.include_router(adr.router, prefix=f"{api}/adr", tags=["ADR"])
    application.include_router(appointments.router, prefix=f"{api}/appointments", tags=["Appointments"])
    application.include_router(notifications.router, prefix=f"{api}/notifications", tags=["Notifications"])

    @application.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": "mediagent-backend"}

    return application


app = create_app()
