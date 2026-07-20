"""Insight Agent — Fact/Observation/Hypothesis from EvidenceClusters + GapAnalysis.

Flow:
  1. Receive EvidenceClusters + Compare GapAnalysis
  2. LLM generates structured insights (Fact/Observation/Hypothesis)
  3. Each insight references cluster + evidence

Rules:
  - No evidence = no insight (never fabricate)
  - Fact must have direct evidence_refs
  - Hypothesis must be clearly labeled + confidence scored
"""

from __future__ import annotations

import json
import re

from app.application.dto.agent_dto import (
    InsightInput, InsightOutput, ProductInsight,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent
from app.infrastructure.agents.insight_prompt import (
    SYSTEM_PROMPT, build_insight_prompt, LLMInsightOutput,
)
from app.infrastructure.llm.client import llm_client


class InsightAgent(BaseAgent[InsightInput, InsightOutput]):

    @property
    def agent_name(self) -> str:
        return "insight"

    @property
    def phase(self) -> Phase:
        return Phase.INSIGHTING

    async def arun(self, ctx: AgentContext, input_data: InsightInput) -> AgentResult:
        clusters = input_data.evidence_clusters or []
        gaps = input_data.gap_analysis or {}

        if not clusters and not gaps.get("gaps", {}).get("capability_gaps", []):
            return AgentResult(success=True, output=InsightOutput(
                insights=[], summary="证据不足，无法生成洞察",
            ), phase_record={"phase": "insighting", "status": "no_data"})

        clusters_json = json.dumps(clusters, ensure_ascii=False, indent=2)
        gaps_json = json.dumps(gaps, ensure_ascii=False, indent=2)

        objective = input_data.objective or (
            f"分析 {input_data.competitor_company} 的 {input_data.product}"
        )

        try:
            result = await llm_client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_insight_prompt(
                    our_company=input_data.our_company,
                    competitor_company=input_data.competitor_company,
                    product=input_data.product,
                    objective=objective,
                    clusters_json=clusters_json,
                    gaps_json=gaps_json,
                ),
                response_model=None,
                temperature=0.4,
            )
        except Exception:
            return AgentResult(success=False, output=InsightOutput(),
                error="LLM调用失败",
                phase_record={"phase": "insighting", "status": "llm_error"})

        parsed = self._parse_insights(result.content or "")

        if not parsed or not parsed.insights:
            return AgentResult(success=True, output=InsightOutput(
                insights=[], summary="LLM未生成洞察",
            ), phase_record={"phase": "insighting", "status": "completed", "insight_count": 0})

        insights = []
        for item in parsed.insights:
            insights.append(ProductInsight(
                title=item.title,
                type=item.type,
                description=item.description,
                evidence_refs=item.evidence_refs,
                cluster_refs=item.cluster_refs,
                confidence=item.confidence,
                impact=item.impact,
                dimension=item.dimension,
            ))

        facts = sum(1 for i in insights if i.type == "fact")
        obs = sum(1 for i in insights if i.type == "observation")
        hyps = sum(1 for i in insights if i.type == "hypothesis")

        return AgentResult(success=True, output=InsightOutput(
            insights=insights,
            fact_count=facts,
            observation_count=obs,
            hypothesis_count=hyps,
            summary=parsed.summary,
        ), phase_record={
            "phase": "insighting", "status": "completed",
            "insight_count": len(insights),
            "fact_count": facts, "observation_count": obs, "hypothesis_count": hyps,
        })

    @staticmethod
    def _parse_insights(raw: str):
        """Parse LLM JSON response."""
        raw = raw.strip()

        # Strip ```json fences
        code_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
        if code_match:
            raw = code_match.group(1).strip()

        try:
            data = json.loads(raw)
            return LLMInsightOutput(
                insights=[InsightAgent._norm_item(i) for i in data.get("insights", [])],
                summary=data.get("summary", ""),
            )
        except (json.JSONDecodeError, Exception):
            pass

        # Fallback: regex extract JSON
        json_match = re.search(r'\{.*"insights".*\}', raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return LLMInsightOutput(
                    insights=[InsightAgent._norm_item(i) for i in data.get("insights", [])],
                    summary=data.get("summary", ""),
                )
            except (json.JSONDecodeError, Exception):
                pass

        return None

    @staticmethod
    def _norm_item(item: dict):
        from app.infrastructure.agents.insight_prompt import InsightItem
        if isinstance(item, str):
            return InsightItem(title=item[:100], type="fact")
        return InsightItem(**{
            k: v for k, v in item.items()
            if k in InsightItem.model_fields
        })


# ── Singleton ──
insight_agent = InsightAgent()
