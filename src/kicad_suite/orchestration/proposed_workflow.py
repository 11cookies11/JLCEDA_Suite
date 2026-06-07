"""Validation and persistence for agent-proposed workflow plans."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROPOSED_WORKFLOW_SCHEMA_VERSION = "agent_proposed_workflow.v1"
PROPOSED_WORKFLOW_FILENAME = "agent-proposed-workflow.json"

ALLOWED_AGENT_COMMANDS = {
    "status",
    "inspect",
    "diagnose",
    "build-ir",
    "validate-ir",
    "report",
    "workflow status",
    "workflow run",
}

ALLOWED_MODEL_API_OPERATIONS = {
    "set_selected_part",
    "connect_member",
    "disconnect_member",
    "set_net_kind",
    "update_component",
    "patch_model",
}

ALLOWED_STEP_TYPES = {
    "agent_command",
    "model_api",
    "workflow",
    "agent_review",
}


def proposed_workflow_path(project_path: str | Path) -> Path:
    return Path(project_path) / "build" / PROPOSED_WORKFLOW_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_proposed_workflow_file(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("proposed workflow file must contain a JSON object")
    return payload


def validate_proposed_workflow(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a validation report for an agent-proposed workflow plan."""
    errors: list[str] = []
    warnings: list[str] = []
    schema_version = str(plan.get("schema_version", ""))
    workflow_id = str(plan.get("workflow_id", "")).strip()
    steps = plan.get("steps", [])
    completion = plan.get("completion", {})

    if schema_version != PROPOSED_WORKFLOW_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PROPOSED_WORKFLOW_SCHEMA_VERSION}")
    if not workflow_id:
        errors.append("workflow_id is required")
    elif not re.fullmatch(r"[A-Za-z0-9_.:-]+", workflow_id):
        errors.append("workflow_id may only contain letters, numbers, _, ., :, and -")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
    elif len(steps) > 20:
        errors.append("steps must contain at most 20 items")
    if not isinstance(completion, dict) or not completion:
        errors.append("completion is required")

    if isinstance(steps, list):
        seen_step_ids: set[str] = set()
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"steps[{index}] must be an object")
                continue
            step_id = str(step.get("id", "")).strip()
            step_type = str(step.get("type", "")).strip()
            if not step_id:
                errors.append(f"steps[{index}].id is required")
            elif step_id in seen_step_ids:
                errors.append(f"duplicate step id: {step_id}")
            seen_step_ids.add(step_id)
            if step_type not in ALLOWED_STEP_TYPES:
                errors.append(f"steps[{index}].type is not allowed: {step_type}")
                continue
            if step_type == "agent_command":
                command = str(step.get("command", "")).strip()
                if command not in ALLOWED_AGENT_COMMANDS:
                    errors.append(f"steps[{index}].command is not allowed: {command}")
            elif step_type == "model_api":
                operation = str(step.get("operation", "")).strip()
                if operation not in ALLOWED_MODEL_API_OPERATIONS:
                    errors.append(f"steps[{index}].operation is not allowed: {operation}")
                payload = step.get("payload", {})
                if payload and not isinstance(payload, dict):
                    errors.append(f"steps[{index}].payload must be an object")
            elif step_type == "workflow":
                workflow = str(step.get("workflow", "")).strip()
                if not workflow:
                    errors.append(f"steps[{index}].workflow is required")
            elif step_type == "agent_review":
                if not str(step.get("decision_schema", "")).strip():
                    warnings.append(f"steps[{index}].decision_schema is recommended")

    completion_type = str(completion.get("type", "")) if isinstance(completion, dict) else ""
    if completion_type not in {"diagnose_clean", "validate_ir_clean", "manual_review_complete"}:
        errors.append("completion.type must be diagnose_clean, validate_ir_clean, or manual_review_complete")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "workflow_id": workflow_id,
    }


def save_proposed_workflow(project_path: str | Path, plan: dict[str, Any], validation: dict[str, Any]) -> Path:
    path = proposed_workflow_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **plan,
        "status": "approved_plan" if validation.get("ok") else "invalid_plan",
        "validated_at": _now_iso(),
        "validation": validation,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def proposed_workflow_summary(project_path: str | Path) -> dict[str, Any]:
    path = proposed_workflow_path(project_path)
    if not path.exists():
        return {"exists": False, "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = payload.get("steps", [])
    return {
        "exists": True,
        "path": str(path),
        "workflow_id": str(payload.get("workflow_id", "")),
        "status": str(payload.get("status", "")),
        "step_count": len(steps) if isinstance(steps, list) else 0,
        "completion": payload.get("completion", {}),
    }
