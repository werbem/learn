"""Dimension Router — maps analysis dimensions to source types.

Configurable rules for automatic source selection based on research dimensions.

Design:
  - Stateless: pure function mapping dimensions → source types
  - Configurable: rules dict can be updated at runtime
  - Future-proof: designed to accept LLM-suggested overrides later
  - Chinese-friendly: dimension names are fuzzy-matched (contains)

Rules priority:
  1. Exact keyword match
  2. Substring match on dimension name
  3. Fallback: web search

Usage:
    router = DimensionRouter()
    plan = router.build(analysis_scope=["用户画像", "核心功能对比"], keywords=[...])
    # plan.sources = ["web", "app_store", "social", "official"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.infrastructure.tools.research_source import SourceType


# ═══════════════════════════════════════════════════
#  Configuration — modify this to change routing rules
# ═══════════════════════════════════════════════════

# Dimension keyword → (primary source types, secondary source types)
# Keywords are matched case-insensitively as substring matches against
# the dimension name string.
#
# Design principle:
#   primary   = essential sources for this dimension (always called)
#   secondary = supplementary sources (called if available)

_DIMENSION_SOURCE_RULES: dict[str, tuple[list[str], list[str]]] = {

    # ── 用户体验 / UX ──
    "用户体验": (
        [SourceType.APP_STORE, SourceType.WEB],     # primary
        [SourceType.SOCIAL],                         # secondary
    ),
    "用户": (
        [SourceType.APP_STORE, SourceType.SOCIAL, SourceType.WEB],
        [],
    ),
    "ux": (
        [SourceType.APP_STORE, SourceType.WEB],
        [SourceType.SOCIAL],
    ),
    "界面": (
        [SourceType.APP_STORE, SourceType.WEB],
        [],
    ),
    "交互": (
        [SourceType.APP_STORE, SourceType.WEB],
        [],
    ),

    # ── 增长策略 / Growth ──
    "增长": (
        [SourceType.WEB, SourceType.NEWS],
        [SourceType.OFFICIAL],
    ),
    "运营": (
        [SourceType.WEB, SourceType.NEWS],
        [SourceType.OFFICIAL],
    ),
    "营销": (
        [SourceType.WEB, SourceType.NEWS, SourceType.SOCIAL],
        [],
    ),
    "获客": (
        [SourceType.WEB, SourceType.NEWS],
        [SourceType.APP_STORE],
    ),

    # ── 产品功能 / Features ──
    "功能": (
        [SourceType.OFFICIAL, SourceType.WEB],
        [SourceType.APP_STORE],
    ),
    "features": (
        [SourceType.OFFICIAL, SourceType.WEB],
        [],
    ),

    # ── 技术能力 / Technology ──
    "技术": (
        [SourceType.DEVELOPER, SourceType.OFFICIAL, SourceType.WEB],
        [],
    ),
    "架构": (
        [SourceType.DEVELOPER, SourceType.OFFICIAL],
        [],
    ),
    "ai": (
        [SourceType.WEB, SourceType.DEVELOPER],
        [SourceType.OFFICIAL],
    ),

    # ── 商业模式 / Business Model ──
    "商业": (
        [SourceType.WEB, SourceType.NEWS, SourceType.OFFICIAL],
        [],
    ),
    "盈利": (
        [SourceType.WEB, SourceType.NEWS],
        [],
    ),
    "定价": (
        [SourceType.OFFICIAL, SourceType.WEB],
        [SourceType.APP_STORE],
    ),
    "付费": (
        [SourceType.APP_STORE, SourceType.WEB],
        [],
    ),

    # ── 市场 / Market ──
    "市场": (
        [SourceType.WEB, SourceType.NEWS],
        [SourceType.OFFICIAL, SourceType.SOCIAL],
    ),
    "竞争": (
        [SourceType.WEB, SourceType.NEWS],
        [SourceType.OFFICIAL],
    ),
    "竞品": (
        [SourceType.WEB, SourceType.NEWS],
        [SourceType.OFFICIAL, SourceType.APP_STORE],
    ),

    # ── 产品定位 / Positioning ──
    "定位": (
        [SourceType.OFFICIAL, SourceType.WEB, SourceType.NEWS],
        [SourceType.SOCIAL],
    ),
    "品牌": (
        [SourceType.WEB, SourceType.SOCIAL, SourceType.NEWS],
        [],
    ),

    # ── 风险 / Risk ──
    "风险": (
        [SourceType.WEB, SourceType.NEWS],
        [],
    ),
    "合规": (
        [SourceType.WEB, SourceType.NEWS, SourceType.OFFICIAL],
        [],
    ),
    "监管": (
        [SourceType.WEB, SourceType.NEWS],
        [],
    ),
}


# Default source types when no dimension matches
_DEFAULT_PRIMARY = [SourceType.WEB]
_DEFAULT_SECONDARY: list[str] = []


# ═══════════════════════════════════════════════════
#  Execution Plan
# ═══════════════════════════════════════════════════

@dataclass
class SourceExecutionPlan:
    """Result of dimension-based routing.

    Contains the list of source types to query and associated keywords.
    """
    dimensions: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    objective: str = ""

    # Metadata for debugging
    dimension_mapping: dict = field(default_factory=dict)
    """dimension → list of source_types, showing which rule matched"""


# ═══════════════════════════════════════════════════
#  Dimension Router
# ═══════════════════════════════════════════════════

class DimensionRouter:
    """Maps research dimensions to source types using configurable rules.

    Matching algorithm:
      1. For each dimension string, scan _DIMENSION_SOURCE_RULES keys
      2. If the dimension string contains a rule key (case-insensitive),
         add the rule's primary source types
      3. Collect all matches, deduplicate source types
      4. If no matches, use default [web]
    """

    def __init__(self, rules: Optional[dict] = None):
        self._rules = dict(rules) if rules else dict(_DIMENSION_SOURCE_RULES)
        self._default_primary = list(_DEFAULT_PRIMARY)
        self._default_secondary = list(_DEFAULT_SECONDARY)

    @property
    def rules(self) -> dict:
        """Current rules config (read-only view)."""
        return dict(self._rules)

    def update_rules(self, rules: dict) -> None:
        """Merge new rules into the config. Existing keys are overwritten.

        Usage:
            router.update_rules({
                "用户": (["app_store", "social", "web"], []),
                "new_dimension": (["web"], ["social"]),
            })
        """
        self._rules.update(rules)

    def get_source_types(
        self,
        dimensions: list[str],
        include_primary: bool = True,
        include_secondary: bool = False,
    ) -> list[str]:
        """Get the set of source types for given dimensions.

        Args:
            dimensions: Analysis dimension names (from Planner)
            include_primary: Include primary sources
            include_secondary: Include secondary sources

        Returns:
            Deduplicated, ordered list of source type strings
        """
        if not dimensions:
            return list(self._default_primary)

        primary: set[str] = set()
        secondary: set[str] = set()

        for dim in dimensions:
            dim_lower = dim.lower()
            matched = False
            for keyword, (prim, sec) in self._rules.items():
                if keyword.lower() in dim_lower:
                    matched = True
                    primary.update(prim)
                    secondary.update(sec)

            if not matched:
                primary.update(self._default_primary)
                secondary.update(self._default_secondary)

        result: list[str] = []
        if include_primary:
            result.extend(sorted(primary))
        if include_secondary:
            result.extend(sorted(secondary - primary))  # no duplicates

        return result if result else list(self._default_primary)

    def build(
        self,
        dimensions: list[str],
        keywords: list[str],
        objective: str = "",
    ) -> SourceExecutionPlan:
        """Build a complete SourceExecutionPlan from research dimensions.

        Args:
            dimensions: Analysis dimension names
            keywords: Search keywords (from Planner)
            objective: Analysis objective description

        Returns:
            SourceExecutionPlan with resolved source types
        """
        if not dimensions:
            return SourceExecutionPlan(
                dimensions=[],
                source_types=list(self._default_primary),
                keywords=list(keywords),
                objective=objective,
                dimension_mapping={"default": list(self._default_primary)},
            )

        # Build dimension → sources mapping for debugging
        dim_mapping: dict = {}
        primary_all: set[str] = set()

        for dim in dimensions:
            dim_lower = dim.lower()
            matched = False
            for keyword, (prim, _sec) in self._rules.items():
                if keyword.lower() in dim_lower:
                    matched = True
                    prim_list = list(prim)
                    dim_mapping[dim] = prim_list
                    primary_all.update(prim_list)
            if not matched:
                dim_mapping[dim] = list(self._default_primary)
                primary_all.update(self._default_primary)

        # Collect secondary (non-overlapping)
        secondary_all: set[str] = set()
        for dim in dimensions:
            dim_lower = dim.lower()
            for keyword, (prim, sec) in self._rules.items():
                if keyword.lower() in dim_lower:
                    secondary_all.update(sec)
        secondary_all -= primary_all

        source_types = sorted(primary_all) + sorted(secondary_all)

        return SourceExecutionPlan(
            dimensions=list(dimensions),
            source_types=source_types,
            keywords=list(keywords),
            objective=objective,
            dimension_mapping=dim_mapping,
        )

    # ── LLM Dynamic Selection (Future) ──

    def build_with_llm_override(
        self,
        dimensions: list[str],
        keywords: list[str],
        objective: str,
        llm_suggested_sources: Optional[list[str]] = None,
    ) -> SourceExecutionPlan:
        """Build a plan, optionally merged with LLM-suggested source types.

        Future feature: an LLM can review the dimensions and suggest
        additional source types beyond the configured rules.

        Args:
            dimensions: Analysis dimension names
            keywords: Search keywords
            objective: Analysis objective
            llm_suggested_sources: Optional LLM-suggested source types to merge

        Returns:
            SourceExecutionPlan with merged source types
        """
        plan = self.build(dimensions, keywords, objective)

        if llm_suggested_sources:
            merged = set(plan.source_types) | set(llm_suggested_sources)
            plan.source_types = sorted(merged)

        return plan


# ── Singleton ──

dimension_router = DimensionRouter()
