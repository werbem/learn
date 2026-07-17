"""Unit tests for WorkflowState creation."""

from app.infrastructure.workflow.state import WorkflowState, create_initial_state


class TestWorkflowState:
    def test_create_initial_state(self) -> None:
        user_input = {
            "our_company": "A",
            "competitor_company": "B",
            "product": "C",
            "objective": "product_improvement",
        }
        state = create_initial_state(user_input)
        assert state["task_id"] is not None
        assert state["current_phase"] == "initialized"
        assert state["progress"] == 0.0
        assert state["user_input"]["our_company"] == "A"
        assert state["research_plan"] is None
        assert state["evidence_bundle"] is None
        assert state["errors"] == []

    def test_initial_state_fields(self) -> None:
        state = create_initial_state({"test": "value"})
        assert "phase_history" in state
        assert "retry_counts" in state
        assert "stream_events" in state
        assert "human_checkpoints" in state
        assert "final_report" in state
        assert state["version"] == "v1"
