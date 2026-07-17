"""Report aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class ReportSection:
    title: str
    content: str
    order: int
    word_count: int = 0

    def __post_init__(self) -> None:
        if not self.word_count:
            self.word_count = len(self.content)


@dataclass
class ReportFormats:
    markdown: Optional[str] = None
    html: Optional[str] = None
    word_url: Optional[str] = None


@dataclass
class ReportMetadata:
    total_word_count: int = 0
    sources_count: int = 0
    template_used: str = "v1"
    generated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Report:
    id: UUID = field(default_factory=uuid4)
    task_id: UUID = field(default_factory=uuid4)
    our_company: str = ""
    competitor_company: str = ""
    product: str = ""
    objective: str = ""
    sections: list[ReportSection] = field(default_factory=list)
    formats: ReportFormats = field(default_factory=ReportFormats)
    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
