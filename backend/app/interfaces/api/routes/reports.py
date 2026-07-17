"""Reports API — create & retrieve competitive analysis reports."""

from __future__ import annotations

from uuid import UUID

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.application.dto.report_dto import (
    ReportCreateRequest,
    ReportCreateResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportSectionDTO,
)
from app.infrastructure.workflow.state import create_initial_state

router = APIRouter(prefix="/reports", tags=["reports"])

# ── In-memory store (Phase 1 mock) ──
_reports: dict[str, dict] = {}
_tasks: dict[str, dict] = {}


@router.post("", response_model=ReportCreateResponse)
async def create_report(body: ReportCreateRequest) -> ReportCreateResponse:
    """Create a new competitive analysis report.

    Phase 1: Creates the task and returns immediately.
    Phase 2: Will invoke the LangGraph workflow.
    """
    from app.infrastructure.workflow.graph import workflow_graph

    state = create_initial_state(body.model_dump())

    _tasks[str(state["task_id"])] = {
        "task_id": str(state["task_id"]),
        "status": "pending",
        "state": state,
    }

    # Phase 1: Run the graph synchronously for demo purposes.
    try:
        final_state = await workflow_graph.ainvoke(state)
        _tasks[str(state["task_id"])]["state"] = final_state

        report_doc = final_state.get("report_document", {})
        sections_data = report_doc.get("sections", []) if report_doc else []

        _reports[str(state["task_id"])] = ReportDetailResponse(
            id=UUID(final_state["task_id"]),
            task_id=UUID(final_state["task_id"]),
            our_company=body.our_company,
            competitor_company=body.competitor_company,
            product=body.product,
            objective=body.objective,
            markdown=final_state.get("final_report", {}).get("markdown"),
            html=final_state.get("final_report", {}).get("html"),
            sections=[
                ReportSectionDTO(**s) for s in sections_data
            ],
            created_at=datetime.utcnow(),
            total_word_count=report_doc.get("metadata", {}).get("total_word_count", 0),
        ).model_dump()

        _tasks[str(state["task_id"])]["status"] = "completed"
    except Exception as exc:
        _tasks[str(state["task_id"])]["status"] = "failed"
        _tasks[str(state["task_id"])]["error"] = str(exc)

    return ReportCreateResponse(
        task_id=state["task_id"],  # type: ignore[arg-type]
        status="pending",
        message="分析任务已创建",
    )


@router.get("/{task_id}", response_model=ReportDetailResponse)
async def get_report(task_id: UUID) -> ReportDetailResponse:
    """Get the final report by task ID."""
    report = _reports.get(str(task_id))
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在或尚未生成完成")
    return ReportDetailResponse(**report)


@router.get("", response_model=ReportListResponse)
async def list_reports() -> ReportListResponse:
    """List all generated reports (Phase 1 mock)."""
    reports = list(_reports.values())
    return ReportListResponse(reports=reports, total=len(reports))
