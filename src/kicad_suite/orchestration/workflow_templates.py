"""Workflow template registry for agent-assisted orchestration."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class WorkflowTemplate:
    """Static metadata for an agent-facing workflow template."""

    workflow_id: str
    description: str
    deterministic_steps: tuple[str, ...]
    agent_cut_points: tuple[str, ...]
    supported_task_types: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_TEMPLATES: dict[str, WorkflowTemplate] = {
    "full_build_v1": WorkflowTemplate(
        workflow_id="full_build_v1",
        description="Main project workflow that pushes child workflows for part selection and diagnostic repair.",
        deterministic_steps=(
            "load_source_model",
            "check_parts_selected",
            "run_diagnose",
            "complete_when_clean",
        ),
        agent_cut_points=("needs_selection", "diagnose_must_fix", "diagnose_review_required"),
        supported_task_types=("agent_decision", "agent_repair", "agent_review"),
    ),
    "lcsc_selection_v1": WorkflowTemplate(
        workflow_id="lcsc_selection_v1",
        description="Resolve selected LCSC parts and emit agent tasks for components that still need selection.",
        deterministic_steps=(
            "load_source_model",
            "resolve_existing_lcsc_parts",
            "build_needs_selection_tasks",
        ),
        agent_cut_points=("needs_selection",),
        supported_task_types=("agent_decision",),
    ),
    "repair_after_diagnose_v1": WorkflowTemplate(
        workflow_id="repair_after_diagnose_v1",
        description="Convert diagnose must_fix and review_required findings into agent repair/review tasks.",
        deterministic_steps=(
            "run_diagnose",
            "build_repair_tasks",
            "complete_when_clean",
        ),
        agent_cut_points=("diagnose_must_fix", "diagnose_review_required"),
        supported_task_types=("agent_repair", "agent_review"),
    ),
}


def get_template(workflow_id: str) -> WorkflowTemplate | None:
    return _TEMPLATES.get(workflow_id)


def list_templates() -> list[dict[str, object]]:
    return [template.to_dict() for template in _TEMPLATES.values()]
