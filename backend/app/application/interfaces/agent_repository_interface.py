"""Agent repository interface (port) — skeleton."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class AgentRepositoryInterface(ABC):
    """Interface for persisting agent execution results."""

    @abstractmethod
    async def save_agent_result(
        self,
        task_id: UUID,
        agent_name: str,
        input_snapshot: dict,
        output_snapshot: dict,
        duration_ms: int,
        success: bool,
        error: str | None,
    ) -> None:
        ...


class ReportRepositoryInterface(ABC):
    """Interface for persisting reports."""

    @abstractmethod
    async def save_report(self, report: dict) -> None:
        ...
