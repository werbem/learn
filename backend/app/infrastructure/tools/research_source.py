"""Research Source unified interface.

Defines:
  - EvidenceItem:  unified evidence schema for all sources
  - SourceResult:  standardized search result container
  - ResearchSource:  abstract base class for all research data sources

All sources MUST implement ResearchSource and return SourceResult.
This ensures downstream agents (Compare, Strategy, Report) receive
uniform evidence regardless of the source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4


# ── SourceType Enum (mirrors constants.py for tool-layer use) ──

class SourceType:
    WEB = "web"
    APP_STORE = "app_store"
    SOCIAL = "social"
    OFFICIAL = "official"
    DEVELOPER = "developer"
    NEWS = "news"


# ── Unified Evidence Item ──

@dataclass
class EvidenceItem:
    """Unified evidence structure returned by all ResearchSources.

    Every source produces evidence in this exact format.
    The Research Agent later enriches with LLM classification.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    source_type: str = ""       # web | app_store | social | official | developer | news
    source_name: str = ""       # Tavily | Apple App Store | 知乎 | GitHub 等
    title: str = ""
    url: str = ""               # 必须有真实 URL，禁止编造
    content: str = ""
    published_date: str = ""    # YYYY-MM-DD 或空
    author: str = ""
    metrics: dict = field(default_factory=dict)    # 评分/下载量/star 等
    dimension: str = ""         # 分析维度，由 LLM 分类阶段填充
    confidence: str = "medium"  # high | medium | low | estimated
    sentiment: str = "neutral"  # positive | negative | neutral
    quality_score: dict = field(default_factory=dict)  # EvidenceQualityScore as dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "published_date": self.published_date,
            "author": self.author,
            "metrics": self.metrics,
            "dimension": self.dimension,
            "confidence": self.confidence,
            "sentiment": self.sentiment,
            "quality_score": self.quality_score,
        }


# ── Standardized Search Result ──

@dataclass
class SourceResult:
    """Standardized result from a single ResearchSource search."""
    items: list[EvidenceItem] = field(default_factory=list)
    source_type: str = ""
    source_name: str = ""
    status: str = "success"     # success | no_data | error | no_api_key
    error: Optional[str] = None
    total_found: int = 0
    duration_ms: int = 0

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0 or self.status in ("no_data", "no_api_key")


# ── Abstract Source Interface ──

class ResearchSource(ABC):
    """Abstract base class for all research data sources.

    Every source (Tavily, App Store, Zhihu, GitHub, etc.) must:
      1. Set `name` and `source_type` class attributes
      2. Implement `search(query, context)` returning SourceResult

    The Research Agent uses this interface to dispatch searches
    without knowing the underlying implementation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name, e.g. 'Tavily Web Search'."""
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Source type constant, e.g. SourceType.WEB, SourceType.APP_STORE."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        context: Optional[dict] = None,
    ) -> SourceResult:
        """Execute a search and return standardized results.

        Args:
            query: Search query string
            context: Optional context dict with task metadata
                     (task_id, objective, company names, etc.)

        Returns:
            SourceResult with items in unified EvidenceItem format.
            If no results found, return SourceResult with items=[] and
            status='no_data' (never return fake/mock data).
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' type='{self.source_type}'>"
