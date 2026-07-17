"""Evidence value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from app.config.constants import Confidence, SourceType


@dataclass
class EvidenceItem:
    id: UUID = field(default_factory=uuid4)
    source: str = ""
    source_type: SourceType = SourceType.WEB
    content: str = ""
    confidence: Confidence = Confidence.ESTIMATED
    category: str = ""
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    raw_data: Optional[dict] = None


@dataclass
class SourceReport:
    type: SourceType = SourceType.WEB
    url: str = ""
    status: str = "pending"  # success | rate_limited | blocked | no_data
    items_found: int = 0


@dataclass
class CompanyInfo:
    name: str = ""
    description: str = ""
    positioning: str = ""
    business_model: str = ""
    market_focus: str = ""
    funding_stage: str = ""
    data_quality: str = "no_data"


@dataclass
class ProductInfo:
    name: str = ""
    category: str = ""
    description: str = ""
    key_features: list[str] = field(default_factory=list)
    target_users: str = ""
    platforms: list[str] = field(default_factory=list)
    pricing: str = ""
    data_quality: str = "no_data"


@dataclass
class EvidenceBundle:
    our_company: CompanyInfo = field(default_factory=CompanyInfo)
    competitor_company: CompanyInfo = field(default_factory=CompanyInfo)
    our_product: ProductInfo = field(default_factory=ProductInfo)
    competitor_product: ProductInfo = field(default_factory=ProductInfo)
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    news: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)
    market: list[dict] = field(default_factory=list)
    sources_used: list[SourceReport] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)
    quality_score: dict = field(default_factory=lambda: {
        "overall": 0, "coverage": 0, "freshness": 0,
    })
