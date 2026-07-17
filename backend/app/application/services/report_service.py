"""Report application service — use case orchestration (skeleton)."""

from __future__ import annotations

from uuid import UUID

from app.application.dto.report_dto import (
    ReportCreateRequest,
    ReportCreateResponse,
    ReportDetailResponse,
    ReportListResponse,
)
from app.domain.entities.report import Report
from app.domain.entities.task import Task


class ReportService:
    """Application service for report use cases.

    In Phase 1 this is a pass-through. Real orchestration logic
    will connect the API layer to domain services in Phase 2.
    """

    async def create_report(self, request: ReportCreateRequest) -> ReportCreateResponse:
        """Create a new analysis task and return immediately."""
        task = Task()
        report = Report(
            task_id=task.id,
            our_company=request.our_company,
            competitor_company=request.competitor_company,
            product=request.product,
            objective=request.objective,
        )
        _ = report  # Will be persisted in Phase 2
        return ReportCreateResponse(
            task_id=task.id,
            status="pending",
            message="分析任务已创建",
        )

    async def get_report(self, task_id: UUID) -> ReportDetailResponse:
        """Retrieve report by task ID."""
        raise NotImplementedError("Phase 2")

    async def list_reports(self) -> ReportListResponse:
        """List all reports."""
        raise NotImplementedError("Phase 2")
