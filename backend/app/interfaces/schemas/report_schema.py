"""Pydantic schemas for the Report API.

These mirror the DTO layer but are interface-specific (HTTP).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReportOutputSchema(BaseModel):
    """Schema-compliant report response (maps to OpenAPI docs)."""
    id: UUID
    task_id: UUID
    our_company: str
    competitor_company: str
    product: str
    objective: str
    status: str = "completed"
    sections: list[dict] = Field(default_factory=list)
    markdown: Optional[str] = None
    html: Optional[str] = None
    word_url: Optional[str] = None
    total_word_count: int = 0
    generated_at: Optional[datetime] = None


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
    suggestion: Optional[str] = None
