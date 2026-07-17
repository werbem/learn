"""Review Agent — quality assurance (mock)."""

from app.application.dto.agent_dto import (
    ReviewInput,
    ReviewIssue,
    ReviewOutput,
    ReviewResult,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent


class ReviewAgent(BaseAgent[ReviewInput, ReviewOutput]):

    @property
    def agent_name(self) -> str:
        return "review"

    @property
    def phase(self) -> Phase:
        return Phase.REVIEWING

    async def arun(self, ctx: AgentContext, input_data: ReviewInput) -> AgentResult:
        """Mock: always passes review with high score."""
        result = ReviewResult(
            passed=True,
            score=92,
            checks={
                "completeness": True,
                "logic": True,
                "sources": True,
                "duplication": True,
                "format": True,
                "neutrality": True,
                "actionability": True,
            },
            issues=[
                ReviewIssue(
                    severity="suggestion",
                    category="format",
                    section="目标用户与画像",
                    description="建议增加用户画像图表",
                    suggestion="可考虑加入饼图展示用户构成",
                ),
            ],
            revision_suggestions=[],
            passed_for_output=True,
        )
        output = ReviewOutput(
            review_result=result,
            passed_for_output=True,
            score=92,
            check_summary={
                "completeness": True,
                "logic": True,
                "sources": True,
                "duplication": True,
                "format": True,
                "neutrality": True,
                "actionability": True,
            },
            issue_count={"critical": 0, "major": 0, "minor": 0, "suggestion": 1},
        )
        return AgentResult(success=True, output=output)
