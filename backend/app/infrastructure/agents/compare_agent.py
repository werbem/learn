"""Compare Agent — gap analysis (mock)."""

from app.application.dto.agent_dto import (
    CompareInput,
    CompareOutput,
    FeatureItem,
    GapAnalysis,
    GapItem,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent


class CompareAgent(BaseAgent[CompareInput, CompareOutput]):

    @property
    def agent_name(self) -> str:
        return "compare"

    @property
    def phase(self) -> Phase:
        return Phase.COMPARING

    async def arun(self, ctx: AgentContext, input_data: CompareInput) -> AgentResult:
        """Mock: returns canned gap analysis."""
        gap = GapAnalysis(
            positioning={
                "our_positioning": "[MOCK] 面向中小企业的轻量级工具",
                "competitor_positioning": "[MOCK] 面向大型企业的全功能平台",
                "positioning_diff": "目标市场不同，我方更轻量",
            },
            features={
                "feature_matrix": [
                    FeatureItem(
                        category="核心功能",
                        feature_name="数据分析",
                        our_coverage="partial",
                        competitor_coverage="full",
                        differentiator=True,
                    ).model_dump(),
                ],
                "unique_our_features": ["快速上手"],
                "unique_competitor_features": ["企业级权限管理"],
            },
            gaps={
                "competitive_advantages": [
                    GapItem(
                        dimension="用户体验",
                        description="我方交互更简洁",
                        impact="high",
                    ).model_dump(),
                ],
                "competitive_disadvantages": [
                    GapItem(
                        dimension="功能深度",
                        description="竞品功能覆盖面更广",
                        impact="high",
                    ).model_dump(),
                ],
                "capability_gaps": [
                    GapItem(
                        dimension="AI能力",
                        description="竞品已集成智能推荐",
                        impact="medium",
                    ).model_dump(),
                ],
            },
        )
        output = CompareOutput(
            gap_analysis=gap,
            dimensions_analyzed=["positioning", "features", "users"],
            dimensions_skipped=["technology"],
            evidence_references_count=5,
        )
        return AgentResult(success=True, output=output)
