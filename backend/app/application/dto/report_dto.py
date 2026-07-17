"""Report DTOs — request/response."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReportCreateRequest(BaseModel):
    our_company: str = Field(..., min_length=1, description="我方公司名称")
    competitor_company: str = Field(..., min_length=1, description="竞品公司名称")
    product: str = Field(..., min_length=1, description="比对产品名称")
    objective: str = Field(
        ...,
        pattern=r"^(product_improvement|go_to_market|investment_due_diligence|"
                r"competitive_defense|positioning_switch|partnership_evaluation|"
                r"feature_benchmark)$",
    )
    optional: Optional[dict] = Field(default=None, description="可选上下文")


class ReportCreateResponse(BaseModel):
    task_id: UUID
    status: str = "pending"
    message: str = "分析任务已创建"


class ReportSectionDTO(BaseModel):
    title: str
    content: str
    order: int
    word_count: int


class ReportDetailResponse(BaseModel):
    id: UUID
    task_id: UUID
    our_company: str
    competitor_company: str
    product: str
    objective: str
    markdown: Optional[str] = None
    html: Optional[str] = None
    word_url: Optional[str] = None
    sections: list[ReportSectionDTO] = Field(default_factory=list)
    total_word_count: int = 0
    generated_at: Optional[datetime] = None
    created_at: datetime


class ReportListResponse(BaseModel):
    reports: list[ReportDetailResponse]
    total: int
