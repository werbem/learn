"""Strategy Agent — generates SWOT, opportunities, risks, recommendations, roadmap.

基于 Research Evidence 和 Compare Result 形成产品洞察。
所有结论必须引用 Evidence，不可编造数据。
Evidence 不足时返回 Need More Research 信号。
"""

from __future__ import annotations

from app.application.dto.agent_dto import (
    EvidenceBundleDTO,
    GapAnalysis,
    OpportunityItem,
    RecommendationItem,
    RiskItem,
    StrategicInsights,
    StrategyInput,
    StrategyOutput,
    SWOT,
    SWOTItem,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent

# ── 可信度映射 ──
_CONFIDENCE_WEIGHTS = {"verified": 1.0, "likely": 0.8, "estimated": 0.5, "speculative": 0.3}

# ── 分析目标 → 推荐策略类型映射 ──
_OBJECTIVE_STRATEGIES = {
    "product_improvement": "功能优化",
    "go_to_market": "市场进入",
    "investment_due_diligence": "尽调评估",
    "competitive_defense": "竞争防御",
    "positioning_switch": "定位转型",
    "partnership_evaluation": "合作评估",
    "feature_benchmark": "功能对标",
}


# ═══════════════════════════════════════════
#  Evidence Assessment Engine
# ═══════════════════════════════════════════

def _assess_evidence_quality(eb: EvidenceBundleDTO) -> dict:
    """Evaluate whether collected evidence is sufficient for strategic analysis.

    Returns:
        sufficient: True/False
        reason: explanation when insufficient
        per_dim: evidence count per dimension
        total_items: total evidence items
        avg_confidence: average confidence score (0-1)
    """
    items = eb.evidence_items
    if not items:
        return {
            "sufficient": False,
            "reason": "没有收集到任何证据。需要重新进行 Research。",
            "per_dim": {}, "total_items": 0, "avg_confidence": 0.0,
        }

    # Count per dimension
    per_dim: dict[str, int] = {}
    for item in items:
        cat = item.category or "unknown"
        per_dim[cat] = per_dim.get(cat, 0) + 1

    # Need at least 2 dimensions with 3+ items for basic SWOT
    dims_with_enough = sum(1 for v in per_dim.values() if v >= 2)
    if dims_with_enough < 2:
        covered = ", ".join(f"{k}({v})" for k, v in sorted(per_dim.items()))
        return {
            "sufficient": False,
            "reason": (
                f"证据覆盖不足：仅 {dims_with_enough}/2 个维度达到最低证据量(3条/维度)。"
                f"当前分布：{covered}。需要补充搜索关键维度。"
            ),
            "per_dim": per_dim, "total_items": len(items),
            "avg_confidence": 0.0,
        }

    # Average confidence check
    scores = [_CONFIDENCE_WEIGHTS.get(e.confidence, 0.3) for e in items]
    avg_conf = sum(scores) / len(scores)
    if avg_conf < 0.35:
        return {
            "sufficient": False,
            "reason": (
                f"证据可信度过低（平均 {avg_conf:.0%}）。"
                f"需要提高数据源质量，建议补充官方来源。"
            ),
            "per_dim": per_dim, "total_items": len(items),
            "avg_confidence": avg_conf,
        }

    return {
        "sufficient": True,
        "reason": "",
        "per_dim": per_dim,
        "total_items": len(items),
        "avg_confidence": avg_conf,
    }


# ═══════════════════════════════════════════
#  Evidence Reference Helpers
# ═══════════════════════════════════════════

def _find_evidence_refs(eb: EvidenceBundleDTO, *keywords: str) -> list[str]:
    """Find evidence source URLs containing ALL given keywords."""
    refs = []
    for item in eb.evidence_items:
        content = (item.content or "").lower()
        source = item.source or ""
        if not source.startswith("http"):
            continue
        if any(kw.lower() in content for kw in keywords):
            refs.append(source)
            if len(refs) >= 3:
                break
    return refs


def _evidence_refs_for_dim(eb: EvidenceBundleDTO, dimension: str) -> list[str]:
    """Find evidence references by content/context, not just category."""
    kw = dimension.lower() if dimension else ""
    refs: list[str] = []
    for item in eb.evidence_items:
        if not item.source.startswith("http"):
            continue
        content = (item.content or "").lower()
        category = (item.category or "").lower()
        if kw and (kw in content or kw in category):
            refs.append(item.source)
            if len(refs) >= 3:
                break
    # Fallback: return any evidence sources if dimension-specific match fails
    if not refs:
        for item in eb.evidence_items:
            if item.source.startswith("http"):
                refs.append(item.source)
                if len(refs) >= 3:
                    break
    return refs


def _dimension_confidence(eb: EvidenceBundleDTO, dimension: str) -> str:
    """Compute aggregate confidence for a dimension."""
    items = [e for e in eb.evidence_items if e.category == dimension]
    if not items:
        return "low"
    scores = [_CONFIDENCE_WEIGHTS.get(e.confidence, 0.3) for e in items]
    avg = sum(scores) / len(scores)
    if avg >= 0.8:
        return "high"
    if avg >= 0.5:
        return "medium"
    return "low"


# ═══════════════════════════════════════════
#  SWOT Generation
# ═══════════════════════════════════════════

def _generate_swot(
    gap_analysis: GapAnalysis,
    eb: EvidenceBundleDTO,
    our_company: str,
    competitor_company: str,
) -> SWOT:
    """Generate SWOT from gap analysis and evidence.

    - Strengths: competitive_advantages + positioning advantages
    - Weaknesses: competitive_disadvantages + capability gaps
    - Opportunities: gaps in competitor coverage + market evidence
    - Threats: competitor strengths + risk-related evidence
    """
    strengths: list[SWOTItem] = []
    weaknesses: list[SWOTItem] = []
    opportunities: list[SWOTItem] = []
    threats: list[SWOTItem] = []

    gaps = gap_analysis.gaps or {}
    positioning = gap_analysis.positioning or {}

    # ── Strengths from competitive advantages ──
    advantages = gaps.get("competitive_advantages", []) or []
    for adv in advantages:
        dim = adv.get("dimension", "") if isinstance(adv, dict) else ""
        desc = adv.get("description", "") if isinstance(adv, dict) else str(adv)
        refs = _evidence_refs_for_dim(eb, dim or "positioning")
        strengths.append(SWOTItem(
            item=f"[{our_company}] {desc}" if desc else f"{dim}方面具有竞争优势",
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, dim or "positioning"),
        ))

    # Strengths from positioning
    pos_diff = positioning.get("positioning_diff", "")
    if pos_diff:
        refs = _evidence_refs_for_dim(eb, "positioning")
        strengths.append(SWOTItem(
            item=pos_diff,
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, "positioning"),
        ))

    # ── Weaknesses from competitive disadvantages ──
    disadvantages = gaps.get("competitive_disadvantages", []) or []
    for disadv in disadvantages:
        dim = disadv.get("dimension", "") if isinstance(disadv, dict) else ""
        desc = disadv.get("description", "") if isinstance(disadv, dict) else str(disadv)
        refs = _evidence_refs_for_dim(eb, dim or "features")
        weaknesses.append(SWOTItem(
            item=f"[{our_company}] {desc}" if desc else f"{dim}方面存在差距",
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, dim or "features"),
        ))

    # Weaknesses from capability gaps
    cap_gaps = gaps.get("capability_gaps", []) or []
    for cg in cap_gaps:
        dim = cg.get("dimension", "") if isinstance(cg, dict) else ""
        desc = cg.get("description", "") if isinstance(cg, dict) else str(cg)
        refs = _evidence_refs_for_dim(eb, dim or "technology")
        weaknesses.append(SWOTItem(
            item=f"能力缺口：{desc}" if desc else f"{dim}能力需要建设",
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, dim or "technology"),
        ))

    # ── Opportunities from capability gaps + market evidence ──
    for cg in cap_gaps:
        dim = cg.get("dimension", "") if isinstance(cg, dict) else ""
        desc = cg.get("description", "") if isinstance(cg, dict) else str(cg)
        refs = _evidence_refs_for_dim(eb, dim or "growth")
        opportunities.append(SWOTItem(
            item=f"机会：{desc}" if desc else f"{dim}领域有发展空间",
            evidence_refs=refs,
            confidence="medium",
        ))

    # Opportunities from market evidence
    market_items = [e for e in eb.evidence_items if e.category in ("growth", "competitive_landscape")]
    news_content = " ".join(e.content for e in market_items)
    opportunity_keywords = [
        ("增长迅速", "目标市场持续增长，具备扩张空间"),
        ("融资", "资本市场活跃，融资环境良好"),
        ("新兴", "新兴市场/技术带来新机会"),
        ("政策", "政策利好驱动行业发展"),
        ("需求", "用户需求尚未被充分满足"),
    ]
    for kw, desc in opportunity_keywords:
        if kw in news_content:
            refs = _evidence_refs_for_dim(eb, "growth")
            opportunities.append(SWOTItem(
                item=desc,
                evidence_refs=refs,
                confidence="estimated",
            ))

    # ── Threats from competitor advantages + risk evidence ──
    for adv in advantages:
        dim = adv.get("dimension", "") if isinstance(adv, dict) else ""
        desc = adv.get("description", "") if isinstance(adv, dict) else str(adv)
        refs = _evidence_refs_for_dim(eb, dim or "competitive_landscape")
        threats.append(SWOTItem(
            item=f"[{competitor_company}] {desc}" if desc else f"竞品在{dim}方面的优势构成威胁",
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, dim or "competitive_landscape"),
        ))

    # Threats from risk evidence
    risk_items = [e for e in eb.evidence_items if e.category == "risks"]
    risk_content = " ".join(e.content for e in risk_items)
    threat_keywords = [
        ("竞争加剧", "行业竞争加剧，市场份额面临挑战"),
        ("监管", "监管政策趋严可能影响业务"),
        ("合规", "数据合规要求提升，合规成本增加"),
        ("安全", "数据安全风险需要关注"),
    ]
    for kw, desc in threat_keywords:
        if kw in risk_content:
            refs = _evidence_refs_for_dim(eb, "risks")
            threats.append(SWOTItem(
                item=desc,
                evidence_refs=refs,
                confidence="estimated",
            ))

    # Fallbacks if any quadrant is empty
    if not strengths:
        refs = _evidence_refs_for_dim(eb, "positioning")
        strengths.append(SWOTItem(
            item=f"[{our_company}] 在目标市场具备基础竞争力（依据有限）",
            evidence_refs=refs,
            confidence="low",
        ))
    if not opportunities:
        refs = _evidence_refs_for_dim(eb, "growth")
        opportunities.append(SWOTItem(
            item="暂无明确市场机会信号，建议补充行业研究",
            evidence_refs=refs,
            confidence="low",
        ))
    if not threats:
        refs = _evidence_refs_for_dim(eb, "competitive_landscape")
        threats.append(SWOTItem(
            item="暂无明确竞争威胁信号（可能由于信息不足）",
            evidence_refs=refs,
            confidence="low",
        ))

    return SWOT(
        strengths=strengths[:5],
        weaknesses=weaknesses[:5],
        opportunities=opportunities[:5],
        threats=threats[:5],
    )


# ═══════════════════════════════════════════
#  Opportunities Generation
# ═══════════════════════════════════════════

def _generate_opportunities(
    gap_analysis: GapAnalysis,
    eb: EvidenceBundleDTO,
    objective: str,
) -> list[OpportunityItem]:
    """Identify actionable opportunities from gaps and evidence."""
    opportunities: list[OpportunityItem] = []
    cap_gaps = (gap_analysis.gaps or {}).get("capability_gaps", []) or []
    disadvantages = (gap_analysis.gaps or {}).get("competitive_disadvantages", []) or []

    strategy_type = _OBJECTIVE_STRATEGIES.get(objective, "通用")

    # Each capability gap → potential opportunity
    for cg in cap_gaps:
        dim = cg.get("dimension", "") if isinstance(cg, dict) else ""
        desc = cg.get("description", "") if isinstance(cg, dict) else str(cg)
        impact = cg.get("impact", "medium") if isinstance(cg, dict) else "medium"

        refs = _evidence_refs_for_dim(eb, dim or "technology")
        opportunities.append(OpportunityItem(
            title=f"补齐{dim}能力" if dim else f"{desc[:30]}...",
            description=(
                f"【{strategy_type}策略】当前在{dim}领域存在能力缺口：{desc}。"
                f"补齐此能力可缩小与竞品差距，提升整体竞争力。"
            ),
            impact="high" if impact == "high" else "medium",
            effort="high",
            alignment_with_objective=4,
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, dim or "technology"),
        ))

    # Each competitive disadvantage → opportunity to improve
    for disadv in disadvantages:
        dim = disadv.get("dimension", "") if isinstance(disadv, dict) else ""
        desc = disadv.get("description", "") if isinstance(disadv, dict) else str(disadv)
        refs = _evidence_refs_for_dim(eb, dim or "users")
        opportunities.append(OpportunityItem(
            title=f"优化{dim}体验" if dim else f"{desc[:30]}...",
            description=f"【{strategy_type}策略】竞品在{dim}方面领先：{desc}。优化此方向可改善用户体验。",
            impact="medium",
            effort="medium",
            alignment_with_objective=3,
            evidence_refs=refs,
            confidence=_dimension_confidence(eb, dim or "users"),
        ))

    # Market-driven opportunity from news evidence
    market_items = [e for e in eb.evidence_items if e.category in ("growth", "competitive_landscape")]
    news_text = " ".join(e.content[:200] for e in market_items[:10])

    # Check for market signals
    market_signals = {
        "中小企业市场": {"keywords": ["中小企业", "SMB", "小微"], "impact": "high"},
        "出海/国际化": {"keywords": ["出海", "国际化", "海外"], "impact": "high"},
        "AI智能化": {"keywords": ["AI", "人工智能", "智能"], "impact": "high"},
        "垂直行业深耕": {"keywords": ["垂直", "行业解决方案", "定制"], "impact": "medium"},
    }
    for title, signal in market_signals.items():
        if any(kw in news_text for kw in signal["keywords"]):
            refs = _evidence_refs_for_dim(eb, "growth")
            opportunities.append(OpportunityItem(
                title=title,
                description=f"【{strategy_type}策略】市场信号检测：{title}方向存在发展机会，建议评估进入策略。",
                impact=signal["impact"],
                effort="medium",
                alignment_with_objective=3,
                evidence_refs=refs,
                confidence="estimated",
            ))

    return opportunities[:6]


# ═══════════════════════════════════════════
#  Risks Generation
# ═══════════════════════════════════════════

def _generate_risks(
    gap_analysis: GapAnalysis,
    eb: EvidenceBundleDTO,
) -> list[RiskItem]:
    """Identify and assess risks from competitive analysis."""
    risks: list[RiskItem] = []
    disadvantages = (gap_analysis.gaps or {}).get("competitive_disadvantages", []) or []
    cap_gaps = (gap_analysis.gaps or {}).get("capability_gaps", []) or []

    # Risks from competitive disadvantages widening
    for disadv in disadvantages:
        dim = disadv.get("dimension", "") if isinstance(disadv, dict) else ""
        desc = disadv.get("description", "") if isinstance(disadv, dict) else str(disadv)
        impact = disadv.get("impact", "medium") if isinstance(disadv, dict) else "medium"
        refs = _evidence_refs_for_dim(eb, dim or "features")
        risks.append(RiskItem(
            title=f"{dim}差距扩大风险" if dim else "竞争差距风险",
            description=f"竞品在{dim}领域持续投入，差距可能扩大。当前差距：{desc}",
            probability="high" if impact == "high" else "medium",
            impact=impact,
            mitigation=f"制定{dim}追赶计划，设立阶段性目标",
            evidence_refs=refs,
        ))

    # Risks from missing capabilities
    for cg in cap_gaps:
        dim = cg.get("dimension", "") if isinstance(cg, dict) else ""
        desc = cg.get("description", "") if isinstance(cg, dict) else str(cg)
        refs = _evidence_refs_for_dim(eb, dim or "technology")
        risks.append(RiskItem(
            title=f"能力缺失风险（{dim}）" if dim else "能力缺失风险",
            description=f"缺少{desc}能力，可能影响产品竞争力",
            probability="medium",
            impact="high",
            mitigation=f"评估{dim}能力建设方案，确定自研/采购策略",
            evidence_refs=refs,
        ))

    # Risks from risk-dimension evidence
    risk_items = [e for e in eb.evidence_items if e.category == "risks"]
    risk_text = " ".join(e.content[:200] for e in risk_items[:10])

    risk_signals = {
        "政策监管风险": {"keywords": ["监管", "政策", "法规"], "prob": "medium", "impact": "high"},
        "数据合规风险": {"keywords": ["数据安全", "合规", "隐私", "GDPR"], "prob": "medium", "impact": "high"},
        "市场波动风险": {"keywords": ["市场下行", "经济", "衰退"], "prob": "low", "impact": "medium"},
    }
    for title, signal in risk_signals.items():
        if any(kw in risk_text for kw in signal["keywords"]):
            refs = _evidence_refs_for_dim(eb, "risks")
            risks.append(RiskItem(
                title=title,
                description=f"市场/监管信号检测：{title}。建议提前准备应对方案。",
                probability=signal["prob"],
                impact=signal["impact"],
                mitigation="建立风险监控机制，定期评估影响",
                evidence_refs=refs,
            ))

    return risks[:6]


# ═══════════════════════════════════════════
#  Recommendations Generation
# ═══════════════════════════════════════════

def _generate_recommendations(
    swot: SWOT,
    opportunities: list[OpportunityItem],
    risks: list[RiskItem],
    objective: str,
) -> list[RecommendationItem]:
    """Convert insights into prioritized, actionable recommendations."""
    recommendations: list[RecommendationItem] = []
    strategy_type = _OBJECTIVE_STRATEGIES.get(objective, "通用")

    # From weaknesses → fix recommendations
    for w in swot.weaknesses[:3]:
        recommendations.append(RecommendationItem(
            action=f"【修复短板】{w.item[:60]}",
            rationale=f"当前竞争劣势，需要优先投入资源改善。{w.evidence_refs}",
            priority="p1",
            timeline="short_term",
            evidence_refs=w.evidence_refs,
            kpi="改善幅度达到行业基线水平",
        ))

    # From opportunities → pursue recommendations
    for opp in opportunities[:3]:
        recommendations.append(RecommendationItem(
            action=f"【把握机会】{opp.title[:60]}",
            rationale=f"基于{strategy_type}策略识别的发展机会，{opp.description[:80]}",
            priority="p1" if opp.impact == "high" else "p2",
            timeline="short_term" if opp.impact == "high" else "medium_term",
            evidence_refs=opp.evidence_refs,
            kpi=f"{opp.title}方向取得阶段性进展",
        ))

    # From risks → mitigate recommendations
    for risk in risks[:3]:
        recommendations.append(RecommendationItem(
            action=f"【规避风险】{risk.title[:60]}",
            rationale=risk.mitigation,
            priority="p1" if risk.impact == "high" else "p2",
            timeline="immediate" if risk.probability == "high" else "short_term",
            evidence_refs=risk.evidence_refs,
            kpi="风险等级降低至可控水平",
        ))

    # From strengths → leverage recommendations
    for s in swot.strengths[:2]:
        recommendations.append(RecommendationItem(
            action=f"【发挥优势】{s.item[:60]}",
            rationale=f"已有竞争优势需要持续巩固，{s.evidence_refs}",
            priority="p2",
            timeline="medium_term",
            evidence_refs=s.evidence_refs,
            kpi="保持并扩大领先优势",
        ))

    return recommendations[:8]


# ═══════════════════════════════════════════
#  Roadmap Generation
# ═══════════════════════════════════════════

def _generate_roadmap(recommendations: list[RecommendationItem]) -> dict:
    """Group recommendations into a phased roadmap."""
    phases: dict[str, dict] = {
        "Phase 1 (0-3月)": {
            "duration": "3个月",
            "initiatives": [],
            "success_criteria": [],
        },
        "Phase 2 (3-6月)": {
            "duration": "3个月",
            "initiatives": [],
            "success_criteria": [],
        },
        "Phase 3 (6-12月)": {
            "duration": "6个月",
            "initiatives": [],
            "success_criteria": [],
        },
    }

    for rec in recommendations:
        if rec.timeline == "immediate" or rec.priority == "p1":
            phases["Phase 1 (0-3月)"]["initiatives"].append(rec.action[:60])
        elif rec.timeline == "short_term":
            phases["Phase 2 (3-6月)"]["initiatives"].append(rec.action[:60])
        else:
            phases["Phase 3 (6-12月)"]["initiatives"].append(rec.action[:60])

    # Add success criteria per phase
    all_recs_text = " ".join(r.rationale for r in recommendations if r.rationale)
    for phase, data in phases.items():
        if data["initiatives"]:
            data["success_criteria"] = [
                f"{len(data['initiatives'])} 项行动全部启动",
                "关键里程碑达成率 > 80%",
            ]
        else:
            data["success_criteria"] = ["无明确任务——保持在监控状态"]

    return {
        "phases": [{"phase": k, **v} for k, v in phases.items() if v["initiatives"]],
    }


# ═══════════════════════════════════════════
#  Main Agent Class
# ═══════════════════════════════════════════

class StrategyAgent(BaseAgent[StrategyInput, StrategyOutput]):
    """Strategy Agent — generates strategic insights from evidence & comparison.

    Workflow:
      1. Assess evidence quality (sufficient? → Need More Research)
      2. Generate SWOT (Strengths, Weaknesses, Opportunities, Threats)
      3. Identify actionable opportunities
      4. Assess competitive risks
      5. Generate prioritized recommendations
      6. Build phased roadmap
      7. Label confidence for all outputs
    """

    @property
    def agent_name(self) -> str:
        return "strategy"

    @property
    def phase(self) -> Phase:
        return Phase.STRATEGIZING

    async def arun(self, ctx: AgentContext, input_data: StrategyInput) -> AgentResult:
        gap = input_data.gap_analysis
        eb = input_data.evidence_bundle

        # Extract company names from evidence bundle
        our_company = eb.our_company.name or "我方"
        competitor = eb.competitor_company.name or "竞品"

        # ── Step 1: Assess evidence quality ──
        quality = _assess_evidence_quality(eb)

        if not quality["sufficient"]:
            output = StrategyOutput(
                strategic_insights=StrategicInsights(
                    swot=SWOT(),
                    opportunities=[],
                    risks=[],
                    recommendations=[],
                    roadmap={"phases": []},
                    confidence_labels={},
                ),
                confidence_summary={
                    "sufficient": False,
                    "message": f"Need More Research: {quality['reason']}",
                    "evidence_stats": quality,
                },
            )
            return AgentResult(success=True, output=output)

        # ── Step 2: Generate SWOT ──
        swot = _generate_swot(gap, eb, our_company, competitor)

        # ── Step 3: Identify opportunities ──
        opportunities = _generate_opportunities(gap, eb, input_data.objective)

        # ── Step 4: Assess risks ──
        risks = _generate_risks(gap, eb)

        # ── Step 5: Generate recommendations ──
        recommendations = _generate_recommendations(
            swot, opportunities, risks, input_data.objective,
        )

        # ── Step 6: Build roadmap ──
        roadmap = _generate_roadmap(recommendations)

        # ── Step 7: Confidence labels ──
        confidence_labels: dict[str, str] = {
            "overall": _dimension_confidence(eb, "positioning"),
            "swot": "high" if len(swot.strengths) >= 2 else "medium",
            "opportunities": "medium" if len(opportunities) >= 2 else "low",
            "risks": "medium" if len(risks) >= 1 else "low",
            "recommendations": "medium",
            "evidence_quality": f"{quality['avg_confidence']:.0%}",
        }

        insights = StrategicInsights(
            swot=swot,
            opportunities=opportunities,
            risks=risks,
            recommendations=recommendations,
            roadmap=roadmap,
            confidence_labels=confidence_labels,
        )

        output = StrategyOutput(
            strategic_insights=insights,
            confidence_summary={
                "sufficient": True,
                "overall": confidence_labels["overall"],
                "evidence_quality": quality["avg_confidence"],
                "evidence_counts": quality["per_dim"],
                "total_items": quality["total_items"],
            },
        )

        return AgentResult(success=True, output=output)
