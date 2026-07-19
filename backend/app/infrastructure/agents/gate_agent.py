"""Gate Agent — input validation and normalization."""

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
        """Validate and normalize user input.

        Merges scene/additional_objective into the final objective field
        so downstream agents receive a unified objective context.
        """
        raw = input_data.user_input.model_dump()

        # Resolve objective: prefer scene > additional_objective > raw objective
        objective = raw.get("objective", "product_improvement")
        scene = raw.get("scene") or ""
        additional = (raw.get("optional") or {}).get("additional_objective", "")

        if scene:
            objective = scene
        elif additional:
            objective = additional

        validated = ValidatedInputDTO(
            is_valid=True,
            clean_values={
                "our_company": raw.get("our_company", ""),
                "competitor_company": raw.get("competitor_company", ""),
                "product": raw.get("product", ""),
                "objective": objective,
                "scene": scene or additional,
            },
            issues=[],
        )
        output = GateOutput(
            validated_input=validated,
            current_phase=Phase.VALIDATED.value,
        )
        return AgentResult(success=True, output=output)
