"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "service": "competitive-analysis-backend",
    }


@router.get("/health/ready")
async def readiness_check() -> dict:
    """Readiness probe — returns 200 when the service is ready to accept traffic."""
    return {"status": "ready"}
