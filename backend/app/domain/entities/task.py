"""Task entity — represents an analysis workflow execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from app.config.constants import Phase


@dataclass
class PhaseRecord:
    phase: Phase
    entered_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0
    status: str = "running"  # running | completed | failed | skipped
    error: Optional[dict] = None


@dataclass
class Task:
    id: UUID = field(default_factory=uuid4)
    report_id: Optional[UUID] = None
    status: Phase = Phase.INITIALIZED
    current_agent: str = ""
    progress: float = 0.0
    phase_history: list[PhaseRecord] = field(default_factory=list)
    error_info: Optional[dict] = None
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
