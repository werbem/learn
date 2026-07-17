"""Planner Agent — task decomposition (mock)."""

from app.application.dto.agent_dto import (
    PlannerInput,
    PlannerOutput,
    ResearchPlan,
    ResearchTask,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent


class PlannerAgent(BaseAgent[PlannerInput, PlannerOutput]):

    @property
    def agent_name(self) -> str:
        return "planner"

    @property
    def phase(self) -> Phase:
        return Phase.PLANNING

    async def arun(self, ctx: AgentContext, input_data: PlannerInput) -> AgentResult:
        """Mock: returns a standard research plan."""
        plan = ResearchPlan(
            objective=input_data.objective,
            analysis_scope=["positioning", "users", "features", "business", "growth"],
            research_tasks=[
                ResearchTask(
                    task_id="task_web_001",
                    source_type="web",
                    keywords=[input_data.competitor_company, input_data.product],
                    priority=5,
                    dependencies=[],
                ),
                ResearchTask(
                    task_id="task_as_001",
                    source_type="app_store",
                    keywords=[input_data.product],
                    priority=3,
                    dependencies=[],
                ),
                ResearchTask(
                    task_id="task_social_001",
                    source_type="social",
                    keywords=[input_data.competitor_company],
                    priority=3,
                    dependencies=[],
                ),
                ResearchTask(
                    task_id="task_ai_001",
                    source_type="ai_search",
                    keywords=[
                        f"{input_data.competitor_company} {input_data.product} 竞品分析",
                    ],
                    priority=4,
                    dependencies=[],
                ),
            ],
            required_sources=["web", "app_store", "social", "ai_search"],
            workflow=["research", "compare", "strategy", "report", "review"],
            estimated_complexity="moderate",
        )
        output = PlannerOutput(
            research_plan=plan,
            phase_record={
                "phase": Phase.PLANNED.value,
                "duration_ms": 0,
                "status": "completed",
            },
        )
        return AgentResult(success=True, output=output)
