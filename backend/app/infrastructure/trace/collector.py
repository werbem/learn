"""TraceCollector — in-memory trace store with query API."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from app.infrastructure.trace.model import AnalysisTrace, TraceStatus


class TraceCollector:
    """Singleton trace collector.

    Collects all AnalysisTrace records in memory.
    Supports:
      - start_trace / end_trace for lifecycle management
      - query by task_id, stage, agent_name, status
      - JSON export
    """

    def __init__(self):
        self._traces: list[AnalysisTrace] = []
        # Active (running) traces keyed by trace_id
        self._active: dict[str, AnalysisTrace] = {}

    # ── Lifecycle ──

    def start_trace(
        self,
        task_id: str,
        stage: str,
        agent_name: str = "",
        input_summary: str = "",
        metadata: dict | None = None,
    ) -> AnalysisTrace:
        """Begin a new trace record. Returns the trace for later updates."""
        trace = AnalysisTrace(
            trace_id=str(uuid.uuid4()),
            task_id=task_id,
            stage=stage,
            agent_name=agent_name,
            status=TraceStatus.RUNNING,
            input_summary=input_summary[:500],
            metadata=metadata or {},
        )
        trace.mark_start()
        self._active[trace.trace_id] = trace
        self._traces.append(trace)
        return trace

    def end_trace(
        self,
        trace: AnalysisTrace,
        success: bool,
        output_summary: str = "",
        error: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Finalize a trace record."""
        if success:
            trace.mark_success(output_summary, metadata)
        else:
            trace.mark_failure(error or "Unknown error", output_summary)
        self._active.pop(trace.trace_id, None)

    def record_trace(
        self,
        task_id: str,
        stage: str,
        agent_name: str = "",
        status: TraceStatus = TraceStatus.SUCCESS,
        input_summary: str = "",
        output_summary: str = "",
        error: str | None = None,
        duration_ms: int = 0,
        metadata: dict | None = None,
    ) -> AnalysisTrace:
        """Record a one-shot trace (already completed)."""
        trace = AnalysisTrace(
            trace_id=str(uuid.uuid4()),
            task_id=task_id,
            stage=stage,
            agent_name=agent_name,
            status=status,
            input_summary=input_summary[:500],
            output_summary=output_summary[:500],
            error=error,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        if status == TraceStatus.SUCCESS:
            trace.status = TraceStatus.SUCCESS
        elif status == TraceStatus.FAILED:
            trace.status = TraceStatus.FAILED
        trace.start_time = datetime.now(timezone.utc)
        trace.end_time = datetime.now(timezone.utc)
        trace.duration_ms = duration_ms
        self._traces.append(trace)
        return trace

    # ── Query ──

    def get_by_task(self, task_id: str) -> list[AnalysisTrace]:
        """Get all traces for a specific task."""
        return [t for t in self._traces if t.task_id == task_id]

    def get_by_stage(self, stage: str) -> list[AnalysisTrace]:
        """Get all traces for a specific stage."""
        return [t for t in self._traces if t.stage == stage]

    def get_failed(self, task_id: str | None = None) -> list[AnalysisTrace]:
        """Get all failed traces, optionally filtered by task."""
        failed = [t for t in self._traces if t.status == TraceStatus.FAILED]
        if task_id:
            failed = [t for t in failed if t.task_id == task_id]
        return failed

    def get_active(self) -> list[AnalysisTrace]:
        """Get all currently running traces."""
        return list(self._active.values())

    def get_all(self, task_id: str | None = None, limit: int = 200) -> list[dict]:
        """Get all traces as dicts, newest first."""
        traces = self._traces
        if task_id:
            traces = [t for t in traces if t.task_id == task_id]
        traces = sorted(traces, key=lambda t: t.start_time, reverse=True)
        return [t.to_dict() for t in traces[:limit]]

    # ── Summary ──

    def get_summary(self, task_id: str) -> dict:
        """Get a summary of all traces for a task."""
        traces = self.get_by_task(task_id)
        stages = defaultdict(list)
        for t in traces:
            stages[t.stage].append(t)

        stage_summary = {}
        for stage, stage_traces in stages.items():
            failed = [t for t in stage_traces if t.status == TraceStatus.FAILED]
            succeeded = [t for t in stage_traces if t.status == TraceStatus.SUCCESS]
            total_ms = sum(t.duration_ms for t in stage_traces)
            stage_summary[stage] = {
                "count": len(stage_traces),
                "failed": len(failed),
                "succeeded": len(succeeded),
                "total_duration_ms": total_ms,
                "errors": [t.error for t in failed if t.error],
            }

        all_failed = self.get_failed(task_id)
        return {
            "task_id": task_id,
            "total_traces": len(traces),
            "failed_count": len(all_failed),
            "failed_stages": [t.stage for t in all_failed],
            "stages": stage_summary,
        }

    # ── Maintenance ──

    def clear(self, task_id: str | None = None) -> int:
        """Clear traces, optionally for a specific task. Returns count removed."""
        if task_id:
            before = len(self._traces)
            self._traces = [t for t in self._traces if t.task_id != task_id]
            return before - len(self._traces)
        count = len(self._traces)
        self._traces.clear()
        self._active.clear()
        return count

    @property
    def total_count(self) -> int:
        return len(self._traces)


# Singleton
trace_collector = TraceCollector()
