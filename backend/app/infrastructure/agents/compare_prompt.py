"""Compare Agent prompts — evidence-backed gap analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field

SYSTEM_PROMPT = """你是一名严谨的竞品差距分析师。根据采集到的证据，对比我方产品与竞品的差距。

核心原则：
1. 每个结论必须有证据支撑——引用具体的 Evidence ID
2. 禁止无依据推测
3. 不仅描述差异，还要分析对用户和业务的影响
4. 输出严格的 JSON 格式

differences 和 capability_gaps 必须是对象数组：
{dimension:growth,title:差异标题,our_status:我方状态,competitor_status:竞品状态,evidence_refs:[E001],user_impact:对用户影响,business_impact:对业务影响,confidence:high}

dimensions_skipped 必须是对象数组：[{dimension:ux,reason:无证据}]
"""


class DifferenceItem(BaseModel):
    dimension: str = ""
    title: str = ""
    our_status: str = ""
    competitor_status: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    user_impact: str = ""
    business_impact: str = ""
    confidence: str = "medium"


class LLMCompareOutput(BaseModel):
    differences: list[DifferenceItem] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    disadvantages: list[str] = Field(default_factory=list)
    capability_gaps: list[DifferenceItem] = Field(default_factory=list)
    dimensions_analyzed: list[str] = Field(default_factory=list)
    dimensions_skipped: list[dict] = Field(default_factory=list)
    overall_summary: str = ""


def build_compare_prompt(our_company, competitor_company, product, evidence_json, analysis_scope):
    scope_str = ", ".join(analysis_scope) if analysis_scope else "全维度"
    return f"""## 分析对象
- 我方: {our_company} / {product}
- 竞品: {competitor_company} / {product}
- 分析范围: {scope_str}

## 采集证据
{evidence_json}

## 任务
对比差距。每个结论必须有 evidence_refs。

differences/capability_gaps 对象格式：
{{"dimension":"growth","title":"DAU下降","our_status":"DAU-33%","competitor_status":"DAU+25%","evidence_refs":["E001"],"user_impact":"用户减少使用","business_impact":"收入下降","confidence":"high"}}

dimensions_skipped 格式：[{{"dimension":"ux","reason":"无证据"}}]

请严格按以上格式输出 JSON。"""


def _normalize_llm_output(raw: dict):
    """Normalize LLM output, handling simplified formats."""
    from .compare_prompt import LLMCompareOutput, DifferenceItem
    def _ensure_diff(item):
        if isinstance(item, str):
            return DifferenceItem(title=item[:100])
        return DifferenceItem(**{k: v for k, v in item.items() if k in DifferenceItem.model_fields})

    differences = [_ensure_diff(d) for d in raw.get("differences", [])]
    capability_gaps = [_ensure_diff(c) for c in raw.get("capability_gaps", [])]
    ds = raw.get("dimensions_skipped", [])
    if isinstance(ds, dict):
        ds = [{"dimension": k, "reason": v} for k, v in ds.items()]

    return LLMCompareOutput(
        differences=differences,
        advantages=raw.get("advantages", []),
        disadvantages=raw.get("disadvantages", []),
        capability_gaps=capability_gaps,
        dimensions_analyzed=raw.get("dimensions_analyzed", []),
        dimensions_skipped=ds,
        overall_summary=raw.get("overall_summary", ""),
    )
