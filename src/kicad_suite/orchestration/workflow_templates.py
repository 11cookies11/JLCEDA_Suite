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
        description="Main project workflow that routes part selection, IR repair, and diagnostic repair to agent-facing child workflows, then exports KiCad.",
        deterministic_steps=(
            "load_source_model",
            "check_parts_selected",
            "resolve_libraries",
            "build_and_validate_ir",
            "export_kicad",
            "run_diagnose",
            "complete_when_clean",
        ),
        agent_cut_points=("needs_selection", "library_resolution_failed", "ir_build_failed", "ir_validation_failed", "export_failed", "diagnose_must_fix", "diagnose_review_required"),
        supported_task_types=("agent_decision", "agent_repair", "agent_review"),
    ),
    "lcsc_selection_v1": WorkflowTemplate(
        workflow_id="lcsc_selection_v1",
        description="Emit agent tasks for components that still need LCSC selection; the agent chooses parts and writes source.",
        deterministic_steps=(
            "load_source_model",
            "scan_missing_selected_parts",
            "build_needs_selection_tasks",
        ),
        agent_cut_points=("needs_selection",),
        supported_task_types=("agent_decision",),
    ),
    "ir_repair_v1": WorkflowTemplate(
        workflow_id="ir_repair_v1",
        description="Convert IR validation failures into agent repair tasks.",
        deterministic_steps=(
            "load_source_model",
            "build_ir",
            "validate_ir",
            "build_repair_tasks",
        ),
        agent_cut_points=("ir_validation_failed",),
        supported_task_types=("agent_repair", "agent_review"),
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
    "export_repair_v1": WorkflowTemplate(
        workflow_id="export_repair_v1",
        description="Retry KiCad export and emit repair tasks on failure.",
        deterministic_steps=(
            "load_source_model",
            "run_export_kicad",
            "complete_when_exported",
        ),
        agent_cut_points=("export_failed",),
        supported_task_types=("agent_repair",),
    ),
    "unknown_task_v1": WorkflowTemplate(
        workflow_id="unknown_task_v1",
        description="Fallback workflow that asks the agent to classify an unknown or unsupported workflow condition.",
        deterministic_steps=(
            "read_workflow_context",
            "build_unknown_task_review",
        ),
        agent_cut_points=("unknown_condition",),
        supported_task_types=("agent_review",),
    ),
}


def get_template(workflow_id: str) -> WorkflowTemplate | None:
    return _TEMPLATES.get(workflow_id)


def list_templates() -> list[dict[str, object]]:
    return [template.to_dict() for template in _TEMPLATES.values()]
