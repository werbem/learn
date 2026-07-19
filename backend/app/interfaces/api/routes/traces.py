"""Traces API — query analysis trace records."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.infrastructure.trace import trace_collector
from app.infrastructure.trace.diagnosis import DiagnosisEngine

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("")
async def list_traces(
    task_id: str | None = Query(None, description="Filter by task ID"),
    stage: str | None = Query(None, description="Filter by stage"),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """List all traces, optionally filtered by task_id or stage."""
    if stage:
        traces = trace_collector.get_by_stage(stage)
        if task_id:
            traces = [t for t in traces if t.task_id == task_id]
        return {
            "traces": [t.to_dict() for t in traces[:limit]],
            "total": len(traces),
        }

    traces = trace_collector.get_all(task_id=task_id, limit=limit)
    return {"traces": traces, "total": len(traces)}


@router.get("/stats")
async def trace_stats() -> dict:
    """Get overall trace statistics. MUST be defined BEFORE /{task_id}."""
    return {
        "total_traces": trace_collector.total_count,
        "active_traces": len(trace_collector.get_active()),
    }


@router.get("/{task_id}/diagnosis")
async def get_task_diagnosis(task_id: UUID) -> dict:
    """Get AI-powered failure diagnosis for a task."""
    engine = DiagnosisEngine(trace_collector)
    diagnosis = engine.diagnose(str(task_id))
    return diagnosis.to_dict()


@router.get("/{task_id}")
async def get_task_traces(
    task_id: UUID,
    stage: str | None = Query(None, description="Filter by stage"),
    include_failed_only: bool = Query(False, description="Only show failed traces"),
) -> dict:
    """Get all traces for a specific task, with optional filters."""
    traces = trace_collector.get_by_task(str(task_id))

    if stage:
        traces = [t for t in traces if t.stage == stage]
    if include_failed_only:
        traces = [t for t in traces if t.status.value == "FAILED"]

    traces = sorted(traces, key=lambda t: t.start_time)
    return {
        "task_id": str(task_id),
        "traces": [t.to_dict() for t in traces],
        "total": len(traces),
    }


@router.get("/{task_id}/summary")
async def get_task_trace_summary(task_id: UUID) -> dict:
    """Get a summary view of all traces for a task."""
    return trace_collector.get_summary(str(task_id))


@router.get("/{task_id}/failed")
async def get_task_failed_traces(task_id: UUID) -> dict:
    """Get only failed traces for a task."""
    failed = trace_collector.get_failed(str(task_id))
    return {
        "task_id": str(task_id),
        "failed_count": len(failed),
        "traces": [t.to_dict() for t in sorted(failed, key=lambda t: t.start_time)],
    }


@router.delete("/{task_id}")
async def clear_task_traces(task_id: UUID) -> dict:
    """Clear all traces for a specific task."""
    removed = trace_collector.clear(str(task_id))
    return {"status": "cleared", "task_id": str(task_id), "removed": removed}
