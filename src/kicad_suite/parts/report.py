"""Parts summary helpers."""

from __future__ import annotations

from .resolve import part_risk
from ..part_selector import SelectedPart


def build_parts_summary(components_count: int, selected_parts: list[SelectedPart]) -> dict[str, int]:
    """Build the standard parts summary payload."""
    return {
        "total_components": components_count,
        "resolved_parts": len(selected_parts),
        "low_risk": sum(1 for p in selected_parts if part_risk(p) == "low"),
        "medium_risk": sum(1 for p in selected_parts if part_risk(p) == "medium"),
        "high_risk": sum(1 for p in selected_parts if part_risk(p) == "high"),
        "needs_review": sum(1 for p in selected_parts if p.needs_review),
    }

