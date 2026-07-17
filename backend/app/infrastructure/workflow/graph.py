"""LangGraph graph definition.

Compiles all nodes into a StateGraph with conditional edges.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.infrastructure.workflow.nodes import (
    compare_node,
    fail_node,
    finalize_node,
    need_research_node,
    plan_node,
    report_node,
    research_node,
    review_node,
    strategy_node,
    validate_input_node,
)
from app.infrastructure.workflow.state import WorkflowState


def _route_from_validate(state: WorkflowState) -> str:
    """After validate: valid → plan, invalid → fail."""
    cp = state.get("current_phase", "")
    return "plan_node" if cp == "validated" else "fail_node"


def _route_from_strategy(state: WorkflowState) -> str:
    """After strategy: sufficient → report, need more research → need_research."""
    cp = state.get("current_phase", "")
    if cp == "need_more_research":
        return "need_research_node"
    return "report_node"


def _route_from_review(state: WorkflowState) -> str:
    """After review: passed → finalize, failed → check retry budget."""
    cp = state.get("current_phase", "")
    if cp == "reviewed":
        return "finalize_node"
    # review_failed — check retry count
    retries = state.get("retry_counts", {})
    report_retries = retries.get("report_retry", 0)
    if report_retries < 3:
        return "report_node"
    return "fail_node"


def build_workflow_graph() -> StateGraph:
    """Build and compile the LangGraph StateGraph."""

    graph = StateGraph(WorkflowState)

    # ── Register nodes ──
    graph.add_node("validate_input_node", validate_input_node)
    graph.add_node("plan_node", plan_node)
    graph.add_node("research_node", research_node)
    graph.add_node("compare_node", compare_node)
    graph.add_node("strategy_node", strategy_node)
    graph.add_node("need_research_node", need_research_node)
    graph.add_node("report_node", report_node)
    graph.add_node("review_node", review_node)
    graph.add_node("finalize_node", finalize_node)
    graph.add_node("fail_node", fail_node)

    # ── Set entry ──
    graph.set_entry_point("validate_input_node")

    # ── Conditional: validate → plan | fail ──
    graph.add_conditional_edges(
        "validate_input_node",
        _route_from_validate,
        {"plan_node": "plan_node", "fail_node": "fail_node"},
    )

    # ── Main pipeline (sequential) ──
    graph.add_edge("plan_node", "research_node")
    graph.add_edge("research_node", "compare_node")
    graph.add_edge("compare_node", "strategy_node")

    # ── Conditional: strategy → report | need_research ──
    graph.add_conditional_edges(
        "strategy_node",
        _route_from_strategy,
        {
            "report_node": "report_node",
            "need_research_node": "need_research_node",
        },
    )
    graph.add_edge("report_node", "review_node")

    # ── Conditional: review → finalize | report (retry) | fail ──
    graph.add_conditional_edges(
        "review_node",
        _route_from_review,
        {
            "finalize_node": "finalize_node",
            "report_node": "report_node",
            "fail_node": "fail_node",
        },
    )

    # ── Terminals ──
    graph.add_edge("finalize_node", END)
    graph.add_edge("fail_node", END)
    graph.add_edge("need_research_node", END)

    return graph.compile()


# Compiled singleton
workflow_graph = build_workflow_graph()
