"""Workflow domain service interface (port)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class WorkflowService(ABC):
    """Domain service interface for the workflow engine.

    The infrastructure layer implements this with LangGraph.
    """

    @abstractmethod
    async def execute(self, user_input: dict) -> dict:
        """Execute the full analysis workflow and return the final state."""
        ...

    @abstractmethod
    async def get_progress(self, task_id: str) -> dict:
        """Get current progress of a running workflow."""
        ...
