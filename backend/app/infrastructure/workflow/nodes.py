"""LangGraph node functions — with SSE event injection.

Each node emits phase_update events via push_event() for real-time
progress tracking via SSE.
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
from app.infrastructure.workflow.stream import (
    AGENT_DONE_MSGS,
    AGENT_RUNNING_MSGS,
    push_event,
)


def _tid(state: WorkflowState) -> str:
    return state.get("task_id", "")


def _emit(agent: str, status: str, state: WorkflowState, extra: dict | None = None) -> None:
    """Emit an SSE event for an agent phase transition."""
    tid = _tid(state)
    msg = AGENT_RUNNING_MSGS.get(agent, f"{agent} 运行中") if status == "running" else AGENT_DONE_MSGS.get(agent, f"{agent} 完成")
    progress = state.get("progress", 0.0)
    push_event(tid, agent=agent, status=status, message=msg, progress=progress, extra=extra)


# ── Helpers ──

def _make_ctx(state: WorkflowState, agent_name: str) -> AgentContext:
    return AgentContext(
        task_id=state.get("task_id", ""),
        current_phase=state.get("current_phase", "initialized"),
        retry_count=state.get("retry_counts", {}).get(agent_name, 0),
    )


def _push_phase(state: WorkflowState, record: dict[str, Any]) -> list[dict[str, Any]]:
    history = list(state.get("phase_history", []))
    history.append(record)
    return history


# ═══════════════════════════════════════════════════
#  Node Functions
# ═══════════════════════════════════════════════════

async def validate_input_node(state: WorkflowState) -> dict[str, Any]:
    """Gate: validate user input."""
    _emit("gate", "running", state)

    ctx = _make_ctx(state, "gate")
    agent = GateAgent()
    result = await agent.aexecute(ctx, GateInput(user_input=state.get("user_input", {})))
    if result.success:
        _emit("gate", "completed", state)
        return {
            "validated_input": result.output.model_dump(),
            "current_phase": result.output.current_phase,
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
    """Planner: generate research plan."""
    _emit("planner", "running", state)

    ctx = _make_ctx(state, "planner")
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = PlannerAgent()
    result = await agent.aexecute(
        ctx,
        PlannerInput(
            our_company=vi.get("our_company", ""),
            competitor_company=vi.get("competitor_company", ""),
            product=vi.get("product", ""),
            objective=vi.get("objective", "product_improvement"),
        ),
    )
    if result.success:
        _emit("planner", "completed", state)
        return {
            "research_plan": result.output.research_plan.model_dump(),
            "current_phase": "planned",
            "progress": 15.0,
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
    """Research: collect evidence from web sources."""
    _emit("research", "running", state)

    ctx = _make_ctx(state, "research")
    agent = ResearchAgent()
    result = await agent.aexecute(
        ctx,
        ResearchInput(
            research_plan=state.get("research_plan", {}),
            our_company=state.get("validated_input", {}).get("clean_values", {}).get("our_company", ""),
            competitor_company=state.get("validated_input", {}).get("clean_values", {}).get("competitor_company", ""),
            product=state.get("validated_input", {}).get("clean_values", {}).get("product", ""),
        ),
    )
    if result.success:
        eb = result.output.evidence_bundle if hasattr(result.output, 'evidence_bundle') else None
        count = len(eb.evidence_items) if eb and hasattr(eb, 'evidence_items') else 0
        _emit("research", "completed", state, extra={"evidence_count": count})
        return {
            "evidence_bundle": eb.model_dump() if eb else {},
            "current_phase": "researched",
            "progress": 40.0,
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
    """Compare: gap analysis between our product and competitors."""
    _emit("compare", "running", state)

    ctx = _make_ctx(state, "compare")
    vi = state.get("validated_input", {}).get("clean_values", {})
    agent = CompareAgent()
    result = await agent.aexecute(
        ctx,
        CompareInput(
            evidence_bundle=state.get("evidence_bundle", {}),
            analysis_scope=state.get("research_plan", {}).get("analysis_scope", []) or vi.get("objective", "").split(","),
            objective=vi.get("objective", ""),
            product=vi.get("product", ""),
            our_company=vi.get("our_company", ""),
            competitor_company=vi.get("competitor_company", ""),
        ),
    )
    if result.success:
        _emit("compare", "completed", state)
        return {
            "gap_analysis": result.output.gap_analysis.model_dump() if hasattr(result.output, 'gap_analysis') else {},
            "current_phase": "compared",
            "progress": 55.0,
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
    """Strategy: generate SWOT, opportunities, recommendations."""
    _emit("strategy", "running", state)

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
        _emit("strategy", "completed", state)
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
    """Report: generate formatted report (Markdown/HTML/Word)."""
    _emit("report", "running", state)

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
        _emit("report", "completed", state)
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
    """Review: quality assurance on the generated report."""
    _emit("review", "running", state)

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
        _emit("review", "completed", state, extra={"passed": passed})
        return {
            "review_result": result.output.review_result.model_dump(),
            "current_phase": "reviewed" if passed else "review_failed",
            "retry_counts": {**state.get("retry_counts", {}), "report_retry": state.get("retry_counts", {}).get("report_retry", 0) + (0 if passed else 1)},
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


async def fail_node(state: WorkflowState) -> dict[str, Any]:
    """Terminal node for failure states."""
    return {
        "current_phase": "failed",
        "progress": 0.0,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def finalize_node(state: WorkflowState) -> dict[str, Any]:
    """Terminal node for success — mark complete."""
    from app.infrastructure.workflow.stream import push_done
    push_done(_tid(state), status="completed")

    return {
        "current_phase": "completed",
        "progress": 100.0,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def need_research_node(state: WorkflowState) -> dict[str, Any]:
    """Terminal node when more research is needed."""
    from app.infrastructure.workflow.stream import push_done
    push_done(_tid(state), status="need_more_research")

    return {
        "current_phase": "need_more_research",
        "progress": 65.0,
        "updated_at": datetime.utcnow().isoformat(),
    }
