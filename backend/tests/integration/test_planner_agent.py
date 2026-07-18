"""Integration test for Planner Agent with real LLM.

Tests:
  1. Planner Agent generates different plans for different scenarios
  2. Each plan has meaningful content (not hardcoded)
  3. LLM-generated output is structured correctly

Run with:
    export OPENAI_API_KEY=sk-xxx
    python -m pytest tests/integration/test_planner_agent.py -v
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from app.application.dto.agent_dto import PlannerInput
from app.infrastructure.agents.base import AgentContext
from app.infrastructure.agents.planner_agent import PlannerAgent


def _make_context() -> AgentContext:
    return AgentContext(
        task_id="test-planner",
        current_phase="planning",
    )


def _print_plan(label: str, plan: dict) -> None:
    """Pretty-print a research plan."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Objective:       {plan.get('objective', '')[:80]}")
    print(f"  Analysis Scope:  {', '.join(plan.get('analysis_scope', []))}")
    print(f"  Complexity:      {plan.get('estimated_complexity', '')}")
    print(f"  Required:        {', '.join(plan.get('required_sources', []))}")

    tasks = plan.get("research_tasks", [])
    print(f"  Research Tasks:  {len(tasks)}")
    for t in tasks:
        print(f"    [{t['priority']}] {t['source_type']:12s} keywords={t['keywords']}")
    print()


class TestPlannerAgent:

    @pytest.mark.asyncio
    async def test_scenario_飞猪DAU下降(self):
        """案例1：分析飞猪DAU下降原因"""
        agent = PlannerAgent()
        result = await agent.arun(
            _make_context(),
            PlannerInput(
                our_company="阿里巴巴",
                competitor_company="携程、美团",
                product="飞猪旅行",
                objective="product_improvement",
                optional_context="飞猪App DAU连续3个月下降，需要分析原因并制定对策",
            ),
        )

        assert result.success, f"Planner should succeed: {result.error}"
        plan = result.output.research_plan

        self._validate_plan(plan, expected_companies=["飞猪", "携程", "美团"])

        # Check it's not the default mock
        is_mock = plan.objective == "product_improvement"
        assert not is_mock, "Plan should be LLM-generated, not mock fallback"

    @pytest.mark.asyncio
    async def test_scenario_美团酒店增长(self):
        """案例2：分析美团酒店业务增长原因"""
        agent = PlannerAgent()
        result = await agent.arun(
            _make_context(),
            PlannerInput(
                our_company="美团",
                competitor_company="携程、飞猪",
                product="美团酒店",
                objective="competitive_defense",
                optional_context="美团酒店业务过去一年实现高速增长，需要分析增长驱动因素",
            ),
        )

        assert result.success, f"Planner should succeed: {result.error}"
        plan = result.output.research_plan

        self._validate_plan(plan, expected_companies=["美团", "携程", "飞猪"])

        is_mock = plan.objective == "product_improvement"
        assert not is_mock, "Plan should be LLM-generated, not mock fallback"

    @pytest.mark.asyncio
    async def test_two_scenarios_different(self):
        """验证：两个场景生成不同的研究计划"""
        agent = PlannerAgent()

        ctx = _make_context()

        result1 = await agent.arun(
            ctx,
            PlannerInput(
                our_company="阿里巴巴",
                competitor_company="携程、美团",
                product="飞猪旅行",
                objective="product_improvement",
                optional_context="飞猪App DAU连续3个月下降",
            ),
        )
        result2 = await agent.arun(
            ctx,
            PlannerInput(
                our_company="美团",
                competitor_company="携程、飞猪",
                product="美团酒店",
                objective="competitive_defense",
                optional_context="美团酒店业务高速增长",
            ),
        )

        plan1 = result1.output.research_plan
        plan2 = result2.output.research_plan

        # 1. Different objectives
        assert plan1.objective != plan2.objective, \
            "Two scenarios should have different objectives"

        # 2. At least one different analysis scope
        scope_diff = set(plan1.analysis_scope) != set(plan2.analysis_scope)
        assert scope_diff or len(plan1.analysis_scope) != len(plan2.analysis_scope), \
            "Two scenarios should have different analysis scopes"

        # 3. Print comparison
        _print_plan("案例1：飞猪DAU下降", plan1.model_dump())
        _print_plan("案例2：美团酒店增长", plan2.model_dump())

    def _validate_plan(self, plan, expected_companies: list[str]) -> None:
        """Validate that a plan has all required fields with meaningful content."""
        assert plan.objective, "Plan must have objective"
        assert len(plan.objective) > 10, \
            f"Objective should be meaningful, got: {plan.objective}"

        assert len(plan.analysis_scope) >= 3, \
            f"Should have 3+ analysis dimensions, got {len(plan.analysis_scope)}: {plan.analysis_scope}"

        assert len(plan.research_tasks) >= 3, \
            f"Should have 3+ research tasks, got {len(plan.research_tasks)}"

        for t in plan.research_tasks:
            assert t.source_type, f"Task must have source_type: {t}"
            assert len(t.keywords) >= 1, f"Task must have at least 1 keyword: {t}"

        assert plan.estimated_complexity in ("simple", "moderate", "complex"), \
            f"Invalid complexity: {plan.estimated_complexity}"

        # Verify the plan references the expected companies
        all_text = str(plan.model_dump())
        has_company = any(c in all_text for c in expected_companies)
        assert has_company, \
            f"Plan should reference expected companies: {expected_companies}"


if __name__ == "__main__":
    """Direct runner for manual execution."""
    import asyncio

    t = TestPlannerAgent()

    async def run():
        print("=" * 60)
        print("  Planner Agent Integration Test")
        print("=" * 60)
        print()

        print("Running 案例1: 飞猪DAU下降...")
        try:
            await t.test_scenario_飞猪DAU下降()
            print("  ✅ 通过\n")
        except Exception as e:
            print(f"  ❌ 失败: {e}\n")

        print("Running 案例2: 美团酒店增长...")
        try:
            await t.test_scenario_美团酒店增长()
            print("  ✅ 通过\n")
        except Exception as e:
            print(f"  ❌ 失败: {e}\n")

        print("Running 比较验证...")
        try:
            await t.test_two_scenarios_different()
            print("  ✅ 通过\n")
        except Exception as e:
            print(f"  ❌ 失败: {e}")

    asyncio.run(run())
