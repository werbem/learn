"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.infrastructure.persistence.database import db_manager
from app.interfaces.api.routes.health import router as health_router
from app.interfaces.api.routes.reports import router as reports_router
from app.interfaces.api.routes.tasks import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    """Application lifespan — startup & shutdown."""
    # Startup
    await db_manager.initialize()
    yield
    # Shutdown
    await db_manager.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI Competitive Analysis Assistant Backend",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(health_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")

    return app
