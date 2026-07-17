"""Abstract base class for all Agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.config.constants import ErrorCategory, Phase

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass
class AgentContext:
    """Runtime context passed to every agent invocation."""
    task_id: str
    current_phase: Phase
    retry_count: int = 0
    started_at: datetime = datetime.now()


@dataclass
class AgentResult:
    """Standardized result wrapper for every agent."""
    success: bool
    output: Any = None
    error: dict | None = None
    duration_ms: int = 0
    phase_record: dict | None = None


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """Abstract base agent.

    Every agent must implement:
      - agent_name    → unique identifier
      - phase         → the Phase this agent represents
      - arun()        → async execution entry point
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique agent identifier, e.g. 'gate', 'planner'."""
        ...

    @property
    @abstractmethod
    def phase(self) -> Phase:
        """The Phase this agent corresponds to."""
        ...

    @abstractmethod
    async def arun(
        self,
        ctx: AgentContext,
        input_data: InputT,
    ) -> AgentResult:
        """Execute the agent's core logic.

        Implementations should:
          1. Validate input
          2. Call LLM / Tools (or return mock data)
          3. Return structured output
          4. Handle errors gracefully via AgentResult
        """
        ...

    async def aexecute(
        self,
        ctx: AgentContext,
        input_data: InputT,
    ) -> AgentResult:
        """Wrapper with timing, error boundary, and phase tracking."""
        start = datetime.now()
        try:
            result = await self.arun(ctx, input_data)
            result.duration_ms = int(
                (datetime.now() - start).total_seconds() * 1000
            )
            result.phase_record = {
                "phase": self.phase.value,
                "entered_at": start.isoformat(),
                "duration_ms": result.duration_ms,
                "status": "completed" if result.success else "failed",
            }
            return result
        except Exception as exc:
            elapsed = int((datetime.now() - start).total_seconds() * 1000)
            return AgentResult(
                success=False,
                error={
                    "code": ErrorCategory.LLM_ERROR.value,
                    "message": str(exc),
                    "node": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "retryable": True,
                },
                duration_ms=elapsed,
                phase_record={
                    "phase": self.phase.value,
                    "entered_at": start.isoformat(),
                    "duration_ms": elapsed,
                    "status": "failed",
                    "error": {"code": ErrorCategory.LLM_ERROR.value, "message": str(exc)},
                },
            )
