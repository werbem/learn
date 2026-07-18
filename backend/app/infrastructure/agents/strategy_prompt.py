"""Strategy Agent prompts — LLM-powered strategic analysis.

Generates SWOT, opportunities, risks, recommendations, and roadmap
based on evidence and gap analysis from previous agents.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

SYSTEM_PROMPT = """你是一名资深的产品战略分析师。根据竞品差距分析和采集到的证据，制定产品战略。

核心原则：
1. 每个结论必须有 evidence_refs（引用具体 Evidence ID）
2. 禁止编造不存在的数据
3. 如果证据不足以支撑某个结论，标注 confidence="low" 或放入 missing_information
4. SWOT 必须具体，不能泛泛而谈

输出 JSON 结构：
{
  "swot": {
    "strengths": [{"conclusion":"结论", "evidence_refs":["E001"], "confidence":"high"}],
    "weaknesses": [...],
    "opportunities": [...],
    "threats": [...]
  },
  "opportunities": [{
    "title":"机会标题", "description":"包含问题背景、机会来源、用户价值、业务价值",
    "impact":"high/medium/low", "effort":"high/medium/low",
    "alignment_with_objective":5,
    "evidence_refs":["E002"], "confidence":"high"
  }],
  "risks": [{
    "title":"风险标题", "description":"风险描述",
    "probability":"high/medium/low", "impact":"high/medium/low",
    "mitigation":"缓解措施",
    "evidence_refs":["E003"]
  }],
  "recommendations": [{
    "action":"行动标题", "rationale":"理由",
    "expected_value":"预期价值描述",
    "priority":"p1/p2/p3", "timeline":"immediate/short_term/long_term",
    "evidence_refs":["E001"], "kpi":"可选KPI"
  }],
  "roadmap": {
    "short_term": [{"action":"行动", "objective":"目标", "priority":"p1", "related_evidence":["E001"]}],
    "medium_term": [...],
    "long_term": [...]
  },
  "overall_confidence": "high/medium/low"
}
"""


class LLMSWOTItem(BaseModel):
    conclusion: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: str = "medium"


class LLMSWOT(BaseModel):
    strengths: list[LLMSWOTItem] = Field(default_factory=list)
    weaknesses: list[LLMSWOTItem] = Field(default_factory=list)
    opportunities: list[LLMSWOTItem] = Field(default_factory=list)
    threats: list[LLMSWOTItem] = Field(default_factory=list)


class LLMOpportunity(BaseModel):
    title: str = ""
    description: str = ""
    impact: str = "medium"
    effort: str = "medium"
    alignment_with_objective: int = 3
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: str = "medium"


class LLMRisk(BaseModel):
    title: str = ""
    description: str = ""
    probability: str = "medium"
    impact: str = "medium"
    mitigation: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class LLMRecommendation(BaseModel):
    action: str = ""
    rationale: str = ""
    expected_value: str = ""
    priority: str = "p2"
    timeline: str = "short_term"
    evidence_refs: list[str] = Field(default_factory=list)
    kpi: str = ""


class LLMRoadmapAction(BaseModel):
    action: str = ""
    objective: str = ""
    priority: str = "p1"
    related_evidence: list[str] = Field(default_factory=list)


class LLMRoadmap(BaseModel):
    short_term: list[LLMRoadmapAction] = Field(default_factory=list)
    medium_term: list[LLMRoadmapAction] = Field(default_factory=list)
    long_term: list[LLMRoadmapAction] = Field(default_factory=list)


class LLMStrategyOutput(BaseModel):
    swot: LLMSWOT = Field(default_factory=LLMSWOT)
    opportunities: list[LLMOpportunity] = Field(default_factory=list)
    risks: list[LLMRisk] = Field(default_factory=list)
    recommendations: list[LLMRecommendation] = Field(default_factory=list)
    roadmap: LLMRoadmap = Field(default_factory=LLMRoadmap)
    overall_confidence: str = "medium"


def _normalize_strategy_output(raw: dict) -> LLMStrategyOutput:
    """Normalize raw LLM JSON output to LLMStrategyOutput."""
    def _swot_items(lst):
        if not lst:
            return []
        return [
            LLMSWOTItem(**{k: v for k, v in (item if isinstance(item, dict) else {}).items()
                          if k in LLMSWOTItem.model_fields})
            for item in lst if isinstance(item, dict)
        ]

    swot_raw = raw.get("swot", {}) or {}
    return LLMStrategyOutput(
        swot=LLMSWOT(
            strengths=_swot_items(swot_raw.get("strengths", [])),
            weaknesses=_swot_items(swot_raw.get("weaknesses", [])),
            opportunities=_swot_items(swot_raw.get("opportunities", [])),
            threats=_swot_items(swot_raw.get("threats", [])),
        ),
        opportunities=[
            LLMOpportunity(**{k: v for k, v in (o if isinstance(o, dict) else {}).items()
                           if k in LLMOpportunity.model_fields})
            for o in raw.get("opportunities", []) if isinstance(o, dict)
        ],
        risks=[
            LLMRisk(**{k: v for k, v in (r if isinstance(r, dict) else {}).items()
                     if k in LLMRisk.model_fields})
            for r in raw.get("risks", []) if isinstance(r, dict)
        ],
        recommendations=[
            LLMRecommendation(**{k: v for k, v in (r if isinstance(r, dict) else {}).items()
                              if k in LLMRecommendation.model_fields})
            for r in raw.get("recommendations", []) if isinstance(r, dict)
        ],
        roadmap=LLMRoadmap(
            short_term=_roadmap_actions(raw, "short_term"),
            medium_term=_roadmap_actions(raw, "medium_term"),
            long_term=_roadmap_actions(raw, "long_term"),
        ),
        overall_confidence=raw.get("overall_confidence", "medium"),
    )


def _roadmap_actions(raw: dict, key: str) -> list[LLMRoadmapAction]:
    roadmap_raw = raw.get("roadmap", {}) or {}
    items = roadmap_raw.get(key, [])
    if not items:
        return []
    return [
        LLMRoadmapAction(**{k: v for k, v in (a if isinstance(a, dict) else {}).items()
                          if k in LLMRoadmapAction.model_fields})
        for a in items if isinstance(a, dict)
    ]


def build_strategy_prompt(
    objective: str,
    product: str,
    gap_summary: str,
    evidence_json: str,
) -> str:
    """Build the strategy prompt from gap analysis and evidence."""
    return f"""## 分析目标
- 目标: {objective}
- 产品: {product}

## 差距分析摘要
{gap_summary}

## 采集证据
{evidence_json}

## 任务
请根据以上信息，制定产品战略。

要求：
1. SWOT 每项至少有 2 条，每个结论必须有 evidence_refs
2. opportunities 描述必须包含：问题背景、机会来源、用户价值、业务价值
3. recommendations 每项必须包含 expected_value（预期价值描述）
4. roadmap 按 short_term(0-3月)/medium_term(3-6月)/long_term(6-12月) 划分
5. 禁止编造不存在的数据
6. 如果某方面证据不足，confidence 标注为 "low"
7. 严格按 JSON 格式输出，不要输出其他内容"""
