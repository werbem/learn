"""Gate Agent — input validation (mock)."""

from app.application.dto.agent_dto import GateInput, GateOutput, ValidatedInputDTO
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent


class GateAgent(BaseAgent[GateInput, GateOutput]):

    @property
    def agent_name(self) -> str:
        return "gate"

    @property
    def phase(self) -> Phase:
        return Phase.VALIDATING

    async def arun(self, ctx: AgentContext, input_data: GateInput) -> AgentResult:
        """Mock: always passes validation."""
        validated = ValidatedInputDTO(
            is_valid=True,
            clean_values=input_data.user_input.model_dump(),
            issues=[],
        )
        output = GateOutput(
            validated_input=validated,
            current_phase=Phase.VALIDATED.value,
        )
        return AgentResult(success=True, output=output)
