"""Pydantic schemas for the Task API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProgressEventSchema(BaseModel):
    """A single streaming event pushed to the client."""
    type: str
    phase: str
    data: Optional[dict] = None
    timestamp: str


class TaskProgressSchema(BaseModel):
    task_id: UUID
    status: str
    progress: float = Field(..., ge=0.0, le=100.0)
    current_agent: str = ""
    estimated_remaining_seconds: Optional[int] = None
