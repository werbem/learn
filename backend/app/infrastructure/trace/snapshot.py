"""Per-agent debug snapshot extraction.

Captures compact input/output metadata for each agent execution,
avoiding full text storage. Each snapshot contains summary, hash,
size, and key agent-specific fields.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash(val: str) -> str:
    return hashlib.md5(val.encode()).hexdigest()[:8]


def _safe_len(val: Any) -> int:
    if isinstance(val, (list, dict, str)):
        return len(val)
    return 0

# ── Agent-specific field extractors ──

_PLANNER_INPUT_FIELDS = ["our_company", "competitor_company", "product", "objective"]
_PLANNER_OUTPUT_FIELDS = ["analysis_goal", "research_dimensions", "search_keywords", "priority"]

_RESEARCH_INPUT_FIELDS = ["research_task_count"]
_RESEARCH_OUTPUT_FIELDS = ["evidence_count", "source_count", "failed_source_count"]

_COMPARE_INPUT_FIELDS = ["evidence_count"]
_COMPARE_OUTPUT_FIELDS = ["gap_count", "reference_count"]

_STRATEGY_INPUT_FIELDS = ["gap_count"]
_STRATEGY_OUTPUT_FIELDS = ["recommendation_count", "opportunity_count", "risk_count"]

_REPORT_INPUT_FIELDS = ["section_count"]
_REPORT_OUTPUT_FIELDS = ["word_count", "section_count", "format_count"]

_REVIEW_INPUT_FIELDS = ["section_count"]
_REVIEW_OUTPUT_FIELDS = ["score", "issues_count", "high_count", "medium_count", "low_count"]


# ── Generic snapshot extractor ──

def extract_fields(data: dict, fields: list[str]) -> dict:
    """Extract only the specified fields from a dict."""
    result = {}
    for f in fields:
        if f in data:
            val = data[f]
            if isinstance(val, (list, dict)):
                result[f] = f"<{type(val).__name__} len={len(val)}>"
            elif isinstance(val, str) and len(val) > 100:
                result[f] = val[:97] + "..."
            else:
                result[f] = val
    return result


def capture_input_snapshot(agent_name: str, input_data: Any) -> dict[str, Any]:
    """Create a compact input snapshot for debug trace."""
    raw = input_data.model_dump() if hasattr(input_data, "model_dump") else {}
    raw_json = json.dumps(raw, default=str, ensure_ascii=False)

    # Per-agent field extraction
    field_map = {
        "planner": _PLANNER_INPUT_FIELDS,
        "research": _RESEARCH_INPUT_FIELDS,
        "compare": _COMPARE_INPUT_FIELDS,
        "strategy": _STRATEGY_INPUT_FIELDS,
        "report": _REPORT_INPUT_FIELDS,
        "review": _REVIEW_INPUT_FIELDS,
    }
    fields = field_map.get(agent_name, [])

    return {
        "size_chars": len(raw_json),
        "hash": _hash(raw_json),
        "key_fields": extract_fields(raw, fields),
        "all_keys": list(raw.keys())[:20],
    }


def capture_output_snapshot(agent_name: str, output: Any, success: bool) -> dict[str, Any]:
    """Create a compact output snapshot for debug trace."""
    raw = output.model_dump() if hasattr(output, "model_dump") else {}
    raw_json = json.dumps(raw, default=str, ensure_ascii=False)

    field_map = {
        "planner": _PLANNER_OUTPUT_FIELDS,
        "research": _RESEARCH_OUTPUT_FIELDS,
        "compare": _COMPARE_OUTPUT_FIELDS,
        "strategy": _STRATEGY_OUTPUT_FIELDS,
        "report": _REPORT_OUTPUT_FIELDS,
        "review": _REVIEW_OUTPUT_FIELDS,
    }
    fields = field_map.get(agent_name, [])

    return {
        "success": success,
        "size_chars": len(raw_json),
        "hash": _hash(raw_json),
        "key_fields": extract_fields(raw, fields) if success else {},
    }
