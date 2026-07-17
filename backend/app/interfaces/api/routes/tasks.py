"""Tasks API — progress tracking & human-in-the-loop."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.application.dto.task_dto import (
    PhaseRecordDTO,
    TaskDecisionRequest,
    TaskProgressResponse,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

# ── In-memory store (Phase 1 mock) ──
_tasks: dict[str, dict] = {}


def _register_task(task_id: str) -> None:
    if task_id not in _tasks:
        _tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "current_agent": "",
            "progress": 0.0,
            "phase_history": [],
            "error_info": None,
            "created_at": datetime.utcnow(),
            "started_at": None,
            "completed_at": None,
        }


@router.get("/{task_id}/progress", response_model=TaskProgressResponse)
async def get_task_progress(task_id: UUID) -> TaskProgressResponse:
    """Get the current progress of an analysis task."""
    from app.infrastructure.workflow.graph import workflow_graph
    from app.interfaces.api.routes.reports import _tasks as report_tasks

    task_str = str(task_id)
    entry = report_tasks.get(task_str, {})
    state = entry.get("state")

    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")

    history = state.get("phase_history", [])
    return TaskProgressResponse(
        task_id=task_id,
        status=state.get("current_phase", "unknown"),
        current_agent=state.get("current_phase", ""),
        progress=state.get("progress", 0.0),
        phase_history=[
            PhaseRecordDTO(
                phase=h.get("phase", ""),
                entered_at=h.get("entered_at", datetime.utcnow().isoformat()),
                duration_ms=h.get("duration_ms", 0),
                status=h.get("status", "running"),
                error=h.get("error"),
            )
            for h in (history or [])
        ],
        created_at=datetime.utcnow(),
    )


@router.patch("/{task_id}/decision")
async def submit_human_decision(
    task_id: UUID,
    body: TaskDecisionRequest,
) -> dict:
    """Submit a human decision for a HITL checkpoint (Phase 2)."""
    _ = task_id, body
    raise HTTPException(status_code=501, detail="Human-in-the-Loop 将在 Phase 2 实现")
