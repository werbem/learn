"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    llm_ready = bool(settings.effective_api_key) or settings.llm_provider.value == "mock"
    return {
        "status": "ok",
        "version": "0.1.0",
        "service": "competitive-analysis-backend",
        "llm": {
            "provider": settings.llm_provider.value,
            "model": settings.effective_model,
            "ready": llm_ready,
            "mock": not bool(settings.effective_api_key),
        },
    }


@router.get("/health/ready")
async def readiness_check() -> dict:
    """Readiness probe — returns 200 when the service is ready to accept traffic."""
    return {"status": "ready"}
