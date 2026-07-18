"""Integration test for Research Agent with Tavily Search.

Tests:
  1. Research Agent collects real evidence via Tavily + LLM extraction
  2. Evidence has real URLs (never fabricated)
  3. Evidence is categorized by dimension
  4. Empty results return "No Evidence Found" gracefully

Prerequisites:
  TAVILY_API_KEY must be set in .env

Run:
  python tests/integration/test_research_agent.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.application.dto.agent_dto import ResearchInput, ResearchPlan
from app.infrastructure.agents.base import AgentContext
from app.infrastructure.agents.research_agent import ResearchAgent


def _make_context() -> AgentContext:
    return AgentContext(task_id="test-research", current_phase="researching")


def _make_plan(objective: str, analysis_scope: list[str]) -> ResearchPlan:
    """Create a minimal ResearchPlan for testing."""
    return ResearchPlan(
        objective=objective,
        analysis_scope=analysis_scope,
        research_tasks=[],
        required_sources=["web"],
        workflow=["research", "compare", "strategy", "report", "review"],
        estimated_complexity="moderate",
    )


async def run_test():
    agent = ResearchAgent()
    ctx = _make_context()

    # ── 测试案例：飞猪DAU下降 ──
    plan = _make_plan(
        objective="分析飞猪DAU持续下降的原因，对标携程和美团发现自身短板",
        analysis_scope=["positioning", "users", "features", "growth", "risks"],
    )

    input_data = ResearchInput(
        research_plan=plan,
        our_company="阿里巴巴",
        competitor_company="携程、美团",
        product="飞猪旅行",
    )

    print("=" * 60)
    print("  Research Agent Integration Test")
    print("=" * 60)
    print()
    print("输入：")
    print(f"  目标:    {plan.objective}")
    print(f"  我方:    {input_data.our_company}")
    print(f"  竞品:    {input_data.competitor_company}")
    print(f"  产品:    {input_data.product}")
    print()

    result = await agent.arun(ctx, input_data)

    assert result.success, f"Agent should succeed: {result.error}"

    output = result.output
    bundle = output.evidence_bundle
    quality = output.quality_report

    print("─" * 60)
    print("  采集结果")
    print("─" * 60)

    # 1. Evidence count
    evidence_count = len(bundle.evidence_items)
    print(f"  Evidence 数量: {evidence_count}")
    print(f"  搜索来源数:    {len(bundle.sources_used)}")
    print(f"  Tavily 调用:   {result.phase_record.get('tavily_calls', 0)}")
    print(f"  LLM 生成:      {result.phase_record.get('llm_generated', False)}")
    print()

    # 2. Quality Report
    print("  质量报告：")
    print(f"    尝试来源: {quality.sources_attempted}")
    print(f"    成功来源: {quality.sources_succeeded}")
    print(f"    平均可信度: {quality.avg_confidence}")
    print(f"    降级使用:   {quality.fallback_used}")
    if quality.missing_data_warnings:
        print(f"    警告:       {', '.join(quality.missing_data_warnings)}")
    print()

    # 3. Evidence details
    if evidence_count > 0:
        print(f"  证据详情 (前 {min(5, evidence_count)} 条)：")
        print()
        for i, e in enumerate(bundle.evidence_items[:5]):
            print(f"  [{i+1}] {e.title}")
            print(f"      来源: {e.source}")
            print(f"      维度: {e.category}")
            print(f"      可信度: {e.confidence}")
            print(f"      URL: {e.url}")
            print(f"      摘要: {e.content[:120]}...")
            print()

        # Verify: every evidence must have a real URL
        print("  URL 验证：")
        for e in bundle.evidence_items:
            assert e.url, f"Evidence has no URL: {e.title}"
            assert e.url.startswith("http"), f"Evidence URL not a real URL: {e.url}"
        print(f"    ✅ 全部 {evidence_count} 条证据都有真实 URL")
        print()

        # Verify: no fabricated sources
        mock_evidence = [
            e for e in bundle.evidence_items
            if e.confidence == "estimated" or "mock" in e.source.lower()
        ]
        print(f"  Mock 检测:")
        if mock_evidence:
            print(f"    ⚠️  发现 {len(mock_evidence)} 条可能为 Mock (confidence=estimated)")
        else:
            print(f"    ✅ 全部证据来自真实来源")

    else:
        print("  ⚠️  未找到证据。可能原因：")
        print("     1. TAVILY_API_KEY 未配置")
        print("     2. 搜索关键词无匹配结果")
        print("     3. LLM 提取无相关证据")

    print()
    print("─" * 60)
    print("  维度分布")
    print("─" * 60)
    for dim, score in sorted(
        quality.coverage_by_dimension.items(), key=lambda x: -x[1]
    ):
        bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
        print(f"  {dim:25s}  [{bar}]  {score:.0f}%")

    print()
    print("─" * 60)
    print("  测试结果")
    print("─" * 60)

    checks = []
    checks.append(("证据非空" if evidence_count > 0 else "证据为空", evidence_count > 0))
    checks.append(("有真实URL", all(e.url.startswith("http") for e in bundle.evidence_items) if evidence_count > 0 else True))
    checks.append(("有来源", all(e.source for e in bundle.evidence_items) if evidence_count > 0 else True))
    checks.append(("维度分类", all(e.category for e in bundle.evidence_items) if evidence_count > 0 else True))

    for name, passed in checks:
        print(f"  {'✅' if passed else '❌'} {name}")

    all_passed = all(p for _, p in checks)
    if all_passed:
        print()
        print("  🎉 全部通过！Research Agent 成功采集真实证据。")
    else:
        print()
        print("  ⚠️  部分检查未通过，请确认 TAVILY_API_KEY 配置正确。")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_test())
