"""Compare Agent — LLM-powered evidence-backed gap analysis."""

from __future__ import annotations

import json
import re

from app.application.dto.agent_dto import (
    CompareInput, CompareOutput, FeatureItem, GapAnalysis, GapItem,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent
from app.infrastructure.agents.compare_prompt import (
    SYSTEM_PROMPT, build_compare_prompt, build_cluster_compare_prompt, _normalize_llm_output,
)
from app.infrastructure.llm.client import llm_client


class CompareAgent(BaseAgent[CompareInput, CompareOutput]):

    @property
    def agent_name(self) -> str:
        return "compare"

    @property
    def phase(self) -> Phase:
        return Phase.COMPARING

    async def arun(self, ctx: AgentContext, input_data: CompareInput) -> AgentResult:
        evidence_items = sorted(
            input_data.evidence_bundle.evidence_items,
            key=lambda e: {"high": 0, "medium": 1, "low": 2, "estimated": 3}.get(e.confidence, 3),
        )[:12]

        clusters = input_data.evidence_clusters or []

        if not evidence_items and not clusters:
            return AgentResult(success=True, output=CompareOutput(
                gap_analysis=GapAnalysis(),
                evidence_references_count=0,
            ), phase_record={"phase": Phase.COMPARING.value, "status": "no_evidence"})

        evidence_json = json.dumps([
            {"id": e.id, "title": e.title, "source": e.source, "url": e.url,
             "date": e.date, "dimension": e.category, "summary": e.content[:300],
             "confidence": e.confidence}
            for e in evidence_items
        ], ensure_ascii=False, indent=2)

        clusters_json = json.dumps(clusters, ensure_ascii=False, indent=2)

        # Use cluster-aware prompt when clusters available, else legacy
        if clusters:
            user_prompt = build_cluster_compare_prompt(
                our_company=input_data.our_company,
                competitor_company=input_data.competitor_company,
                product=input_data.product,
                clusters_json=clusters_json,
                evidence_json=evidence_json,
                analysis_scope=input_data.analysis_scope,
            )
        else:
            user_prompt = build_compare_prompt(
                our_company=input_data.our_company,
                competitor_company=input_data.competitor_company,
                product=input_data.product,
                evidence_json=evidence_json,
                analysis_scope=input_data.analysis_scope,
            )

        try:
            result = await llm_client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=None,
                temperature=0.4,
            )
        except Exception:
            return AgentResult(success=False, output=CompareOutput(
                gap_analysis=GapAnalysis(), evidence_references_count=0,
            ), phase_record={"phase": Phase.COMPARING.value, "status": "llm_error"})

        # Parse JSON directly from LLM response
        parsed = None
        raw_text = (result.content or "").strip()
        if raw_text:
            # Strip markdown fences
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0]
            try:
                m = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if m:
                    data = json.loads(m.group())
                    if isinstance(data, dict) and data.get("differences"):
                        parsed = _normalize_llm_output(data)
            except (json.JSONDecodeError, Exception):
                parsed = None

        if not parsed or not parsed.differences:
            return AgentResult(success=True, output=CompareOutput(
                gap_analysis=GapAnalysis(),
                evidence_references_count=len(evidence_items),
            ), phase_record={
                "phase": Phase.COMPARING.value, "status": "completed",
                "llm_generated": False, "note": "LLM returned empty results",
            })

        gap = self._build_gap_analysis(parsed, evidence_items)

        all_refs = set()
        for d in parsed.differences:
            all_refs.update(d.evidence_refs)
        for cg in parsed.capability_gaps:
            all_refs.update(cg.evidence_refs)

        return AgentResult(success=True, output=CompareOutput(
            gap_analysis=gap,
            dimensions_analyzed=parsed.dimensions_analyzed,
            dimensions_skipped=[d.get("dimension", "") for d in parsed.dimensions_skipped],
            evidence_references_count=len(all_refs),
        ), phase_record={
            "phase": Phase.COMPARING.value, "status": "completed",
            "llm_generated": True,
            "differences_count": len(parsed.differences),
            "capability_gaps_count": len(parsed.capability_gaps),
        })

    def _build_gap_analysis(self, parsed, _evidence_items) -> GapAnalysis:
        fm = []
        for d in parsed.differences:
            cluster_refs = getattr(d, 'cluster_refs', []) or []
            fm.append(FeatureItem(
                category=d.dimension, feature_name=d.title,
                our_coverage=d.our_status, competitor_coverage=d.competitor_status,
                differentiator=True, evidence_refs=d.evidence_refs,
                cluster_refs=cluster_refs,
            ).model_dump())

        pos = {}
        pos_diffs = [d for d in parsed.differences if d.dimension == "positioning"]
        if pos_diffs:
            p = pos_diffs[0]
            pos = {"our_positioning": p.our_status, "competitor_positioning": p.competitor_status}

        return GapAnalysis(
            positioning=pos,
            features={"feature_matrix": fm, "overall_summary": parsed.overall_summary},
            gaps={
                "competitive_advantages": [GapItem(description=a, impact="medium").model_dump() for a in parsed.advantages],
                "competitive_disadvantages": [GapItem(description=d, impact="high").model_dump() for d in parsed.disadvantages],
                "capability_gaps": [GapItem(
                    dimension=cg.dimension,
                    description=f"{cg.title}: 我={cg.our_status} vs 竞={cg.competitor_status}. 用户:{cg.user_impact}. 业务:{cg.business_impact}",
                    evidence_refs=cg.evidence_refs,
                    cluster_refs=getattr(cg, "cluster_refs", []) or [],
                    impact="high",
                ).model_dump() for cg in parsed.capability_gaps],
            },
            evidence_references=sorted(set(ref for d in parsed.differences for ref in d.evidence_refs)),
        )
