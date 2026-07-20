"""State reader — unified access to validated_input across the workflow.

Handles both new flat format and legacy nested format for backward compatibility.

New format (post-fix):
    state["validated_input"] = {
        "is_valid": true,
        "our_company": "飞猪",
        "competitor_company": "美团",
        "product": "酒店",
        "objective": "competitive_defense",
    }

Legacy format (nested GateOutput.model_dump()):
    state["validated_input"] = {
        "validated_input": {
            "is_valid": true,
            "clean_values": {
                "our_company": "飞猪",
                ...
            }
        },
        "current_phase": "validated"
    }
"""

from __future__ import annotations

from typing import Any


def get_validated_input(state: dict[str, Any]) -> dict[str, Any]:
    """Return a flat dict of validated input fields.

    Always returns a dict with these keys:
        our_company, competitor_company, product, objective, is_valid
    """
    vi = state.get("validated_input") or {}

    if not isinstance(vi, dict):
        return {
            "our_company": "",
            "competitor_company": "",
            "product": "",
            "objective": "",
            "is_valid": False,
        }

    # New flat format: {"is_valid": ..., "our_company": ..., ...}
    if "our_company" in vi:
        return {
            "our_company": vi.get("our_company", ""),
            "competitor_company": vi.get("competitor_company", ""),
            "product": vi.get("product", ""),
            "objective": vi.get("objective", ""),
            "is_valid": vi.get("is_valid", False),
        }

    # Legacy nested format: {"validated_input": {"clean_values": {...}}, ...}
    inner = vi.get("validated_input")
    if isinstance(inner, dict):
        cv = inner.get("clean_values") or {}
        if isinstance(cv, dict):
            return {
                "our_company": cv.get("our_company", ""),
                "competitor_company": cv.get("competitor_company", ""),
                "product": cv.get("product", ""),
                "objective": cv.get("objective", ""),
                "is_valid": inner.get("is_valid", False),
            }

    # Last resort: empty defaults
    return {
        "our_company": "",
        "competitor_company": "",
        "product": "",
        "objective": "",
        "is_valid": False,
    }
