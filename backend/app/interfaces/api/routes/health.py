"""Health check endpoint."""

from __future__ import annotations

import os

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

@router.get("/health/demo")
async def demo_status() -> dict:
    """Demo mode status — 前端展示是否为 Demo 模式。

    Demo 触发条件:
      1. DEMO_MODE=true (显式开启)
      2. OPENAI_API_KEY 未配置时自动回退
    """
    from app.config.settings import settings
    demo_on = settings.demo_mode
    explicit = os.getenv("DEMO_MODE", "").lower() == "true"
    return {
        "demo_mode": demo_on,
        "reason": (
            "DEMO_MODE=true (explicit)"
            if explicit
            else "OPENAI_API_KEY not configured (auto-fallback)"
            if demo_on
            else "not in demo mode"
        ),
        "demo_case": "抖音 vs 快手" if demo_on else None,
    }
