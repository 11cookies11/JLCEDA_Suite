"""Agent-facing structured diagnostics for a circuit-model project."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .erc_classification_service import ErcClassificationService
from .project_state import ProjectState
from ..domain.core.circuit_model_io import load_dual_circuit_model, resolve_model_paths
from ..domain.core.ir_compiler import build_ir
from ..domain.core.ir_validator import validate_ir


AGENT_DIAGNOSTICS_SCHEMA_VERSION = "agent-diagnostics.v1"


def build_agent_diagnostics(project_path: str | Path, model_path: str | Path | None = None) -> dict[str, Any]:
    """Build a single structured diagnostic payload for agents."""
    project = Path(project_path).resolve()
    model = Path(model_path).resolve() if model_path is not None else project / "source" / "circuit-model.source.json"
    state = ProjectState(project)
    state.load()

    diagnostics = _empty_buckets()
    sources: dict[str, Any] = {
        "project_state": {
            "status": state.get_status(),
            "stale": state.is_stale(),
            "summary": state.get_summary(),
        }
    }

    model_data: dict[str, Any] = {}
    try:
        source_path, resolved_path = resolve_model_paths(model)
        if source_path.exists() or resolved_path.exists() or model.exists():
            model_data = load_dual_circuit_model(model)
            sources["model"] = {
                "path": str(model),
                "component_count": len(model_data.get("components", [])) if isinstance(model_data, dict) else 0,
                "net_count": len(model_data.get("nets", [])) if isinstance(model_data, dict) else 0,
            }
        else:
            diagnostics["must_fix"].append(_diag(
                source="project",
                code="MODEL_NOT_FOUND",
                severity="error",
                message="No source or resolved circuit model was found.",
                suggested_action={
                    "command": "hwtool agent create",
                    "reason": "Create a project with source/circuit-model.source.json.",
                },
            ))
    except (OSError, ValueError, TypeError) as exc:
        diagnostics["must_fix"].append(_diag(
            source="model",
            code="MODEL_LOAD_FAILED",
            severity="error",
            message=str(exc),
            suggested_action={"command": "hwtool agent inspect --project ."},
        ))

    if model_data:
        _add_ir_diagnostics(model_data, diagnostics, sources)
        _add_erc_diagnostics(project, model_data, diagnostics, sources)

    if state.is_stale():
        diagnostics["review_required"].append(_diag(
            source="project_state",
            code="PROJECT_STATE_STALE",
            severity="warning",
            message="Source model changed after the last recorded build.",
            suggested_action={
                "command": "hwtool agent build-ir --project . && hwtool agent validate-ir --project .",
                "reason": "Refresh generated IR and validation after model changes.",
            },
        ))

    diagnostics["suggested_actions"] = _collect_suggested_actions(diagnostics)
    counts = {key: len(diagnostics[key]) for key in ("must_fix", "library_noise", "review_required")}
    return {
        "schema_version": AGENT_DIAGNOSTICS_SCHEMA_VERSION,
        "ok": counts["must_fix"] == 0,
        "stage": "diagnose",
        "project": state.state.get("project", {}),
        "status": state.get_status(),
        "counts": counts,
        "diagnostics": diagnostics,
        "sources": sources,
    }


def _add_ir_diagnostics(model: dict[str, Any], diagnostics: dict[str, list[dict[str, Any]]], sources: dict[str, Any]) -> None:
    try:
        ir = build_ir(model)
        report = validate_ir(ir)
        sources["ir_validation"] = {
            "ok": report.ok,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "stats": report.stats,
        }
    except (ValueError, KeyError, TypeError) as exc:
        diagnostics["must_fix"].append(_diag(
            source="ir",
            code="IR_BUILD_FAILED",
            severity="error",
            message=str(exc),
            suggested_action={"command": "hwtool agent inspect --project ."},
        ))
        return

    for message in report.errors:
        diagnostics["must_fix"].append(_validation_diag("ir_validation", "error", str(message)))
    for message in report.warnings:
        diagnostics["review_required"].append(_validation_diag("ir_validation", "warning", str(message)))


def _add_erc_diagnostics(
    project: Path,
    model: dict[str, Any],
    diagnostics: dict[str, list[dict[str, Any]]],
    sources: dict[str, Any],
) -> None:
    erc_file = _find_erc_file(project, model)
    if erc_file is None:
        sources["erc"] = {"available": False}
        return

    classification = ErcClassificationService().classify_file(erc_file)
    sources["erc"] = {
        "available": True,
        "path": str(erc_file),
        "finding_count": classification.get("finding_count", 0),
        "counts": classification.get("counts", {}),
    }
    buckets = classification.get("buckets", {})
    for bucket_name in ("must_fix", "library_noise", "review_required"):
        for item in buckets.get(bucket_name, []):
            diagnostics[bucket_name].append(_diag(
                source="erc",
                code=str(item.get("type", "ERC_FINDING")).upper(),
                severity=str(item.get("severity", "warning")),
                message=str(item.get("description", "")),
                details=item,
                suggested_action=item.get("suggested_action") or "",
            ))


def _find_erc_file(project: Path, model: dict[str, Any]) -> Path | None:
    topology = str(model.get("topology", "") or project.name.replace("-", "_"))
    candidate = project / "output" / topology / f"{topology}.erc.json"
    if candidate.exists():
        return candidate
    matches = sorted((project / "output").glob("**/*.erc.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _validation_diag(source: str, severity: str, message: str) -> dict[str, Any]:
    return _diag(
        source=source,
        code=_validation_code(message),
        severity=severity,
        message=message,
        suggested_action=_validation_suggestion(message),
    )


def _validation_code(message: str) -> str:
    lower = message.lower()
    if "duplicate" in lower:
        return "DUPLICATE_ENTRY"
    if "missing" in lower or "not found" in lower:
        return "MISSING_REFERENCE"
    if "must be" in lower:
        return "INVALID_FIELD_TYPE"
    if "circular" in lower:
        return "CIRCULAR_REFERENCE"
    if "floating" in lower:
        return "FLOATING_NET"
    return "VALIDATION_FINDING"


def _validation_suggestion(message: str) -> dict[str, str]:
    lower = message.lower()
    if "duplicate" in lower:
        return {"command": "hwtool agent inspect --project .", "reason": "Find and remove or merge duplicate entries."}
    if "missing" in lower or "not found" in lower:
        return {"command": "hwtool agent inspect --project .", "reason": "Inspect missing references and add or remove the referenced object."}
    return {"command": "hwtool agent validate-ir --project .", "reason": "Re-run validation after editing the model."}


def _empty_buckets() -> dict[str, list[dict[str, Any]]]:
    return {
        "must_fix": [],
        "library_noise": [],
        "review_required": [],
        "suggested_actions": [],
    }


def _diag(
    *,
    source: str,
    code: str,
    severity: str,
    message: str,
    suggested_action: Any = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source": source,
        "code": code,
        "severity": severity,
        "message": message,
    }
    if suggested_action:
        item["suggested_action"] = suggested_action
    if details:
        item["details"] = details
    return item


def _collect_suggested_actions(diagnostics: dict[str, list[dict[str, Any]]]) -> list[Any]:
    actions: list[Any] = []
    seen: set[str] = set()
    for bucket in ("must_fix", "review_required", "library_noise"):
        for item in diagnostics.get(bucket, []):
            action = item.get("suggested_action")
            if not action:
                continue
            marker = repr(action)
            if marker in seen:
                continue
            seen.add(marker)
            actions.append(action)
    return actions
