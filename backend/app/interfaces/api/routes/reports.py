"""Reports API — create & retrieve competitive analysis reports."""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

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

_reports: dict[str, dict] = {}
_tasks: dict[str, dict] = {}


@router.post("", response_model=ReportCreateResponse)
async def create_report(body: ReportCreateRequest) -> ReportCreateResponse:
    """Create a new competitive analysis report.

    Phase 2: Returns immediately. Workflow runs in background.
    """
    from app.infrastructure.workflow.graph import workflow_graph
    from app.infrastructure.workflow.stream import ensure_listener

    state = create_initial_state(body.model_dump())
    task_id_str = str(state["task_id"])

    _tasks[task_id_str] = {
        "task_id": task_id_str,
        "status": "pending",
        "state": state,
    }

    ensure_listener(task_id_str)

    async def _run_workflow():
        try:
            final_state = state
            async for chunk in workflow_graph.astream(state, stream_mode="updates"):
                # chunk is a dict like {"validate_input_node": {...}} or {"plan_node": {...}}
                for node_name, node_state in chunk.items():
                    final_state.update(node_state)
                    _tasks[task_id_str]["state"] = dict(final_state)
            _tasks[task_id_str]["status"] = "completed"

            report_doc = final_state.get("report_document", {})
            sections_data = report_doc.get("sections", []) if report_doc else []

            _reports[task_id_str] = ReportDetailResponse(
                id=UUID(final_state["task_id"]),
                task_id=UUID(final_state["task_id"]),
                our_company=body.our_company,
                competitor_company=body.competitor_company,
                product=body.product,
                objective=body.objective,
                markdown=report_doc.get("formats", {}).get("markdown"),
                html=report_doc.get("formats", {}).get("html"),
                word_url=report_doc.get("formats", {}).get("docx_url"),
                sections=[ReportSectionDTO(**s) for s in sections_data],
                total_word_count=report_doc.get("metadata", {}).get("total_word_count", 0),
                created_at=datetime.utcnow(),
            ).model_dump()
        except Exception as exc:
            import traceback
            _tasks[task_id_str]["status"] = "failed"
            _tasks[task_id_str]["error"] = f"{type(exc).__name__}: {exc}"
            print(f"[WORKFLOW ERROR] task={task_id_str}: {type(exc).__name__}: {exc}")
            traceback.print_exc()

    asyncio.create_task(_run_workflow())

    return ReportCreateResponse(
        task_id=state["task_id"],
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



@router.delete("/{task_id}")
async def delete_report(task_id: UUID) -> dict:
    """Delete a report and its task data."""
    key = str(task_id)
    deleted = False
    if key in _reports:
        del _reports[key]
        deleted = True
    if key in _tasks:
        del _tasks[key]
        deleted = True
    if not deleted:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"status": "deleted", "task_id": key}


@router.get("", response_model=ReportListResponse)
async def list_reports() -> ReportListResponse:
    """List all generated reports."""
    reports = list(_reports.values())
    return ReportListResponse(reports=reports, total=len(reports))
