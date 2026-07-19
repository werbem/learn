"""AnalysisTrace data model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TraceStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class AnalysisTrace:
    """Unified trace record for an AI workflow stage.

    One trace per stage execution, linked by task_id.
    """

    trace_id: str
    task_id: str

    stage: str
    """One of: api | workflow | agent | search_tool | llm_client | result"""

    agent_name: str = ""
    """Agent name (for stage=agent), e.g. 'gate', 'planner'; empty otherwise"""

    status: TraceStatus = TraceStatus.PENDING

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_ms: int = 0

    input_summary: str = ""
    output_summary: str = ""

    error: Optional[str] = None

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extra data per stage, e.g.:
       - llm_client: {provider, model, prompt_tokens, completion_tokens, latency_ms}
       - search_tool: {source, query, result_count, error}
       - api: {method, path, params}
       - result: {word_count, section_count, schema_valid, ...}
    """

    def mark_start(self) -> None:
        self.status = TraceStatus.RUNNING
        self.start_time = datetime.now(timezone.utc)

    def mark_success(self, output_summary: str = "", metadata: dict | None = None) -> None:
        self.status = TraceStatus.SUCCESS
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        self.output_summary = output_summary[:500]
        if metadata:
            self.metadata.update(metadata)

    def mark_failure(self, error: str, output_summary: str = "") -> None:
        self.status = TraceStatus.FAILED
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        self.error = error[:1000]
        self.output_summary = output_summary[:500]

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "stage": self.stage,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "error": self.error,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str, indent=indent)
