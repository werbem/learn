"""Task application service — progress tracking (skeleton)."""

from __future__ import annotations

from uuid import UUID

from app.application.dto.task_dto import TaskDecisionRequest, TaskProgressResponse


class TaskService:
    """Application service for task progress tracking.

    Phase 1: stub. Real implementation will query the workflow state
    from the database via the persistence repository.
    """

    async def get_progress(self, task_id: UUID) -> TaskProgressResponse:
        raise NotImplementedError("Phase 2")

    async def submit_decision(self, task_id: UUID, decision: TaskDecisionRequest) -> dict:
        raise NotImplementedError("Phase 2 — Human-in-the-Loop")
