"""LLM client abstraction — mock implementation only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel

from app.config.settings import settings


@dataclass
class LLMResponse:
    content: str
    parsed: Optional[BaseModel] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = "mock"
    duration_ms: int = 0


class LLMClient:
    """Mock LLM client.

    In Phase 1 this returns canned responses.
    Replace with OpenAI / Anthropic client in Phase 2.
    """

    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.model = settings.llm_model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Generate a response using the configured LLM provider.

        MOCK: returns a placeholder message with empty parsed model.
        """
        start = datetime.now()

        _ = system_prompt, user_prompt, temperature

        content = (
            f"[MOCK {self.provider.value}/{self.model}] "
            f"Received: {user_prompt[:60]}..."
        )

        parsed: Optional[BaseModel] = None
        if response_model:
            parsed = response_model()

        elapsed = int((datetime.now() - start).total_seconds() * 1000)

        return LLMResponse(
            content=content,
            parsed=parsed,
            prompt_tokens=128,
            completion_tokens=64,
            model=f"mock/{self.model}",
            duration_ms=elapsed,
        )

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        """Stream tokens from the LLM.

        MOCK: yields the full response as a single chunk.
        """
        yield (
            f"[MOCK STREAM] This is a simulated streaming response for: "
            f"{user_prompt[:40]}..."
        )


llm_client = LLMClient()
