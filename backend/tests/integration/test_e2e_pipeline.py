"""End-to-end pipeline test.

Runs the full chain:
  Gate → real Planner → real Research → real Compare → real Strategy → real Report

Reports data flow at each step to verify the link is real.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.infrastructure.workflow.nodes import (
    plan_node,
    research_node,
    compare_node,
    strategy_node,
    report_node,
    validate_input_node,
)
from app.infrastructure.workflow.state import WorkflowState


def _make_state(company: str, competitors: str, product: str, objective: str = "product_improvement") -> WorkflowState:
    return WorkflowState(
        task_id="test-e2e",
        user_input={
            "our_company": company,
            "competitor_company": competitors,
            "product": product,
            "objective": objective,
        },
        current_phase="initialized",
        phase_history=[],
        errors=[],
        progress=0.0,
    )


def _check_mock(phase: str, result: dict) -> str:
    """Detect if a step returned mock data."""
    pr = result.get("phase_history", [{}])[-1] if result.get("phase_history") else {}
    llm_gen = pr.get("llm_generated", None)
    if llm_gen is True:
        return "✅ LLM"
    elif llm_gen is False:
        return "⚠️ MOCK"
    else:
        # Heuristic: check if output looks real
        if phase == "research":
            eb = result.get("evidence_bundle", {})
            items = eb.get("evidence_items", [])
            if items:
                has_real = any(
                    e.get("url", "").startswith("http") and e.get("confidence") != "estimated"
                    for e in items
                )
                return "✅ TAVILY+LLM" if has_real else "⚠️ EMPTY"
            return "⚠️ EMPTY"
        if phase == "report":
            doc = result.get("report_document", {})
            fmts = doc.get("formats", {})
            if fmts.get("markdown") and len(fmts.get("markdown", "")) > 500:
                return "✅ LLM"
            return "⚠️ EMPTY"
        if phase == "strategy":
            insights = result.get("strategic_insights", {})
            swot = insights.get("swot", {})
            if len(swot.get("strengths", [])) >= 1:
                return "✅ LLM"
            return "⚠️ EMPTY"
        return "❓"


async def run_pipeline():
    # ── Input ──
    print("=" * 65)
    print("  端到端数据链路测试")
    print("=" * 65)
    print()
    print("  用户输入: 飞猪DAU下降原因分析")
    print("  我方:     阿里巴巴(飞猪)")
    print("  竞品:     携程、美团")
    print()

    state = _make_state(
        company="阿里巴巴",
        competitors="携程、美团",
        product="飞猪旅行",
        objective="product_improvement",
    )

    # ── Step 1: Gate ──
    print("─" * 65)
    print("  [1/6] Gate Agent (输入校验)")
    print("─" * 65)
    g = await validate_input_node(state)
    valid = g.get("validated_input", {}).get("is_valid", False)
    state.update(g)
    print(f"  校验结果: {'✅ 通过' if valid else '❌ 失败'}")
    print(f"  Phase:    {state.get('current_phase')}")

    # ── Step 2: Planner ──
    print()
    print("─" * 65)
    print("  [2/6] Planner Agent (研究计划)")
    print("─" * 65)
    p = await plan_node(state)
    state.update(p)
    plan = state.get("research_plan", {})
    llm_status = _check_mock("plan", p)
    print(f"  状态:     {llm_status}")
    print(f"  目标:     {plan.get('objective', '')[:80]}")
    print(f"  维度:     {plan.get('analysis_scope', [])}")
    print(f"  复杂度:   {plan.get('estimated_complexity', '')}")
    print(f"  Phase:    {state.get('current_phase')}")

    # ── Step 3: Research ──
    print()
    print("─" * 65)
    print("  [3/6] Research Agent (证据采集)")
    print("─" * 65)
    r = await research_node(state)
    state.update(r)
    bundle = state.get("evidence_bundle", {})
    evidence = bundle.get("evidence_items", [])
    rstatus = _check_mock("research", r)
    print(f"  状态:     {rstatus}")
    print(f"  证据数:   {len(evidence)}")
    if evidence:
        for i, e in enumerate(evidence[:3]):
            print(f"  [{i+1}] {e.get('title', '')[:60]}")
            print(f"       URL: {e.get('url', '')[:70]}")
    else:
        print(f"  ⚠️  无证据 (TAVILY_API_KEY 未配置)")
    print(f"  Phase:    {state.get('current_phase')}")

    # ── Step 4: Compare ──
    print()
    print("─" * 65)
    print("  [4/6] Compare Agent (差距分析)")
    print("─" * 65)
    c = await compare_node(state)
    state.update(c)
    gap = state.get("gap_analysis", {})
    features = gap.get("features", {})
    gaps = gap.get("gaps", {})
    positioning = gap.get("positioning", {})

    print(f"  DEBUG gap keys: {list(gap.keys()) if gap else 'EMPTY'}")
    print(f"  DEBUG features: {gap.get('features', {}).get('overall_summary', 'NO-SUMMARY')[:60]}")
    print(f"  DEBUG fm length: {len(gap.get('features', {}).get('feature_matrix', []))}")
    print(f"  状态:     {'✅ LLM' if gap.get('features',{}).get('overall_summary') else '⚠️ 空'}")
    print(f"  差异化:   我:{positioning.get('our_positioning','?')[:60]}")
    print(f"            竞:{positioning.get('competitor_positioning','?')[:60]}")
    print(f"  优势:     {len(gaps.get('competitive_advantages',[]))} 项")
    for a in gaps.get('competitive_advantages',[])[:2]:
        print(f"            + {a.get('description','')[:80]}")
    print(f"  劣势:     {len(gaps.get('competitive_disadvantages',[]))} 项")
    for d in gaps.get('competitive_disadvantages',[])[:2]:
        print(f"            - {d.get('description','')[:80]}")
    print(f"  能力差距: {len(gaps.get('capability_gaps',[]))} 项")
    for cg in gaps.get('capability_gaps',[])[:2]:
        print(f"            ! {cg.get('description','')[:100]}")
    fm = features.get('feature_matrix',[])
    print(f"  差异点数: {len(fm)}")
    for f in fm[:3]:
        refs = f.get('evidence_refs',[])
        print(f"            [{','.join(refs)}] {f.get('feature_name','')[:60]}")
    print(f"  Phase:    {state.get('current_phase')}")

    # ── Step 5: Strategy ──
    print()
    print("─" * 65)
    print("  [5/6] Strategy Agent (策略建议)")
    print("─" * 65)
    s = await strategy_node(state)
    state.update(s)
    insights = state.get("strategic_insights", {})
    print(f'  状态:     {_check_mock("strategy", s)}')
    swot = insights.get("swot", {})
    print(f"  SWOT:     S={len(swot.get('strengths',[]))} W={len(swot.get('weaknesses',[]))} O={len(swot.get('opportunities',[]))} T={len(swot.get('threats',[]))}")
    print(f"  Phase:    {state.get('current_phase')}")

    # ── Step 6: Report ──
    print()
    print("─" * 65)
    print("  [6/6] Report Agent (报告生成)")
    print("─" * 65)
    rp = await report_node(state)
    state.update(rp)
    doc = state.get("report_document", {})
    formats = doc.get("formats", {})
    print(f"  状态:     {_check_mock('report', rp)}")
    print(f"  Markdown: {'✅' if formats.get('markdown') else '❌'}")
    print(f"  HTML:     {'✅' if formats.get('html') else '❌'}")
    print(f"  Word:     {'✅' if formats.get('docx_url') else '❌'}")
    print(f"  Phase:    {state.get('current_phase')}")

    # ── Summary ──
    print()
    print("=" * 65)
    print("  数据链路总结")
    print("=" * 65)
    print()
    print(f"  Gate      → {'✅ 真实' if valid else '❌'}")
    print(f"  Planner   → {_check_mock('plan', p)}")
    print(f"  Research  → {_check_mock('research', r)}")
    print(f"  Compare   → ⚠️ MOCK (待改造)")
    print(f'  Strategy  → {_check_mock("strategy", s)}')
    print(f"  Report    → {_check_mock('report', rp)}")
    print()
    print(f"  链路状态: Planner ✅ → Research {'✅' if evidence else '⏸️ (缺key)'} → MOCK ×3")
    print()
    if not evidence:
        print("  ⚠️  请在 .env 中配置 TAVILY_API_KEY 以获取真实证据")
        print("      注册地址: https://tavily.com")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_pipeline())
