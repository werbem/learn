"""LangGraph node functions.

Each function is a LangGraph node that reads from / writes to WorkflowState.
In Phase 1, each node delegates to its mock agent and returns an updated dict.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.application.dto.agent_dto import (
    CompareInput,
    GateInput,
    PlannerInput,
    ReportInput,
    ResearchInput,
    ReviewInput,
    StrategyInput,
    UserInputDTO,
)
from app.infrastructure.agents.base import AgentContext
from app.infrastructure.agents.compare_agent import CompareAgent
from app.infrastructure.agents.gate_agent import GateAgent
from app.infrastructure.agents.planner_agent import PlannerAgent
from app.infrastructure.agents.report_agent import ReportAgent
from app.infrastructure.agents.research_agent import ResearchAgent
from app.infrastructure.agents.review_agent import ReviewAgent
from app.infrastructure.agents.strategy_agent import StrategyAgent
from app.infrastructure.workflow.state import WorkflowState


def _make_ctx(state: WorkflowState, agent_name: str) -> AgentContext:
    return AgentContext(
        task_id=state.get("task_id", ""),
        current_phase=state.get("current_phase", "initialized"),
        retry_count=state.get("retry_counts", {}).get(agent_name, 0),
    )


def _push_phase(state: WorkflowState, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Append a phase record and return the new list."""
    history = list(state.get("phase_history", []))
    history.append(record)
    return history


async def validate_input_node(state: WorkflowState) -> dict[str, Any]:
    """Gate Agent node."""
    ctx = _make_ctx(state, "gate")
    user_input = UserInputDTO(**state.get("user_input", {}))
    agent = GateAgent()
    result = await agent.aexecute(ctx, GateInput(user_input=user_input))
    if result.success:
        output = result.output
        return {
            "validated_input": output.validated_input.model_dump(),
            "current_phase": output.current_phase,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "validation_failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def plan_node(state: WorkflowState) -> dict[str, Any]:
    """Planner Agent node."""
    ctx = _make_ctx(state, "planner")
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = PlannerAgent()
    result = await agent.aexecute(
        ctx,
        PlannerInput(
            our_company=vi.get("our_company", ""),
            competitor_company=vi.get("competitor_company", ""),
            product=vi.get("product", ""),
            objective=vi.get("objective", ""),
            optional_context=(vi.get("optional") or {}).get("additional_context"),
        ),
    )
    if result.success:
        plan = result.output.research_plan
        return {
            "research_plan": plan.model_dump(),
            "current_phase": "planned",
            "progress": 5.0,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def research_node(state: WorkflowState) -> dict[str, Any]:
    """Research Agent node."""
    ctx = _make_ctx(state, "research")
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = ResearchAgent()
    result = await agent.aexecute(
        ctx,
        ResearchInput(
            research_plan=None,
            our_company=vi.get("our_company", ""),
            competitor_company=vi.get("competitor_company", ""),
            product=vi.get("product", ""),
        ),
    )
    if result.success:
        return {
            "evidence_bundle": result.output.evidence_bundle.model_dump(),
            "current_phase": "researched",
            "progress": 25.0,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def compare_node(state: WorkflowState) -> dict[str, Any]:
    """Compare Agent node."""
    ctx = _make_ctx(state, "compare")
    bundle = state.get("evidence_bundle", {})
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = CompareAgent()
    result = await agent.aexecute(
        ctx,
        CompareInput(
            evidence_bundle=bundle,
            analysis_scope=state.get("research_plan", {}).get("analysis_scope", []),
            our_company=vi.get("our_company", ""),
            competitor_company=vi.get("competitor_company", ""),
            product=vi.get("product", ""),
        ),
    )
    if result.success:
        return {
            "gap_analysis": result.output.gap_analysis.model_dump(),
            "current_phase": "compared",
            "progress": 45.0,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def strategy_node(state: WorkflowState) -> dict[str, Any]:
    """Strategy Agent node."""
    ctx = _make_ctx(state, "strategy")
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = StrategyAgent()
    result = await agent.aexecute(
        ctx,
        StrategyInput(
            gap_analysis=state.get("gap_analysis", {}),
            evidence_bundle=state.get("evidence_bundle", {}),
            objective=vi.get("objective", ""),
            product=vi.get("product", ""),
        ),
    )
    if result.success:
        cs = result.output.confidence_summary or {}
        sufficient = cs.get("sufficient", True)
        return {
            "strategic_insights": result.output.strategic_insights.model_dump(),
            "current_phase": "strategized" if sufficient else "need_more_research",
            "progress": 65.0,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def report_node(state: WorkflowState) -> dict[str, Any]:
    """Report Agent node."""
    ctx = _make_ctx(state, "report")
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = ReportAgent()
    result = await agent.aexecute(
        ctx,
        ReportInput(
            evidence_bundle=state.get("evidence_bundle", {}),
            gap_analysis=state.get("gap_analysis", {}),
            strategic_insights=state.get("strategic_insights", {}),
            objective=vi.get("objective", ""),
            product=vi.get("product", ""),
            our_company=vi.get("our_company", ""),
            competitor_company=vi.get("competitor_company", ""),
        ),
    )
    if result.success:
        return {
            "report_document": result.output.report_document.model_dump(),
            "current_phase": "reported",
            "progress": 85.0,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def review_node(state: WorkflowState) -> dict[str, Any]:
    """Review Agent node."""
    ctx = _make_ctx(state, "review")
    agent = ReviewAgent()
    vi = state.get("validated_input", {}).get("clean_values", {})
    result = await agent.aexecute(
        ctx,
        ReviewInput(
            report_document=state.get("report_document", {}),
            evidence_bundle=state.get("evidence_bundle", {}),
            objective=vi.get("objective", ""),
        ),
    )
    if result.success:
        passed = result.output.passed_for_output
        return {
            "review_result": result.output.review_result.model_dump(),
            "current_phase": "reviewed" if passed else "review_failed",
            "progress": 95.0,
            "phase_history": _push_phase(state, result.phase_record),
            "updated_at": datetime.utcnow().isoformat(),
        }
    return {
        "current_phase": "failed",
        "errors": list(state.get("errors", [])) + [result.error],
        "phase_history": _push_phase(state, result.phase_record),
        "updated_at": datetime.utcnow().isoformat(),
    }




async def need_research_node(state: WorkflowState) -> dict[str, Any]:
    """Terminal node — evidence insufficient for strategic analysis."""
    cs = state.get("strategic_insights", {})
    # cs is a dict from model_dump()
    msg = ""
    if isinstance(cs, dict):
        cs_inner = cs.get("confidence_summary", {}) or {}
        if isinstance(cs_inner, dict):
            msg = cs_inner.get("message", "Need More Research: evidence insufficient")

    return {
        "current_phase": "need_more_research",
        "final_report": {
            "markdown": f"# Need More Research\n\n{msg}",
            "word_url": None,
            "html": None,
        },
        "progress": 65.0,
        "phase_history": _push_phase(
            state,
            {
                "phase": "need_more_research",
                "entered_at": datetime.utcnow().isoformat(),
                "duration_ms": 0,
                "status": "completed",
            },
        ),
        "updated_at": datetime.utcnow().isoformat(),
    }

async def finalize_node(state: WorkflowState) -> dict[str, Any]:
    """Finalize node — persists results and returns output URLs.

    In Phase 1 this returns mock data without real persistence.
    """
    report_doc = state.get("report_document", {})
    formats = report_doc.get("formats", {}) if report_doc else {}
    return {
        "final_report": {
            "markdown": formats.get("markdown"),
            "html": formats.get("html"),
            "word_url": formats.get("docx_url"),
        },
        "current_phase": "completed",
        "progress": 100.0,
        "total_duration_ms": 0,
        "phase_history": _push_phase(
            state,
            {
                "phase": "completed",
                "entered_at": datetime.utcnow().isoformat(),
                "duration_ms": 0,
                "status": "completed",
            },
        ),
        "updated_at": datetime.utcnow().isoformat(),
    }


async def fail_node(state: WorkflowState) -> dict[str, Any]:
    """Terminal failure node."""
    return {
        "current_phase": "failed",
        "final_report": {"markdown": None, "word_url": None, "html": None},
        "updated_at": datetime.utcnow().isoformat(),
    }
