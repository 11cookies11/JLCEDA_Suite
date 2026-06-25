"""Registry helpers for declarative semantic gate specifications."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..shared.env_utils import repo_root


SEMANTIC_GATE_SCHEMA_VERSION = "semantic-gate.v1"
GLOBAL_GATE_DIRS = (
    Path("resources") / "hardware-rules" / "builtin",
    Path("resources") / "hardware-rules" / "promoted",
)
PROJECT_ACCEPTED_GATE_DIR = Path("source") / "semantic-gates"
PROJECT_PROPOSED_GATE_DIR = Path("build") / "proposed-semantic-gates"


@dataclass(frozen=True)
class GateValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def gate_filename(gate_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", gate_id.strip()).strip("-._")
    return f"{stem or 'semantic-gate'}.gate.json"


def validate_gate_spec(spec: dict[str, Any]) -> GateValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if spec.get("schema_version") != SEMANTIC_GATE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SEMANTIC_GATE_SCHEMA_VERSION}")
    for key in ("gate_id", "title", "status", "severity", "scope", "rules"):
        if key not in spec:
            errors.append(f"missing required field: {key}")
    if str(spec.get("status", "")) not in {"proposed", "accepted", "promoted", "rejected", "superseded"}:
        errors.append("status must be proposed, accepted, promoted, rejected, or superseded")
    if str(spec.get("severity", "")) not in {"BLOCKER", "WARNING", "INFO"}:
        errors.append("severity must be BLOCKER, WARNING, or INFO")
    rules = spec.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules must be a non-empty array")
    else:
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"rules[{idx}] must be an object")
                continue
            for key in ("code", "description"):
                if not str(rule.get(key, "")).strip():
                    errors.append(f"rules[{idx}].{key} is required")
    if "source_finding" not in spec and spec.get("status") == "proposed":
        warnings.append("proposed gate has no source_finding metadata")
    return GateValidationResult(ok=not errors, errors=errors, warnings=warnings)


def load_gate_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_gate_file(path: Path, spec: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def gate_search_dirs(project_path: Path, include_proposed: bool = True) -> list[tuple[str, Path]]:
    root = repo_root()
    dirs: list[tuple[str, Path]] = [
        ("builtin", root / GLOBAL_GATE_DIRS[0]),
        ("promoted", root / GLOBAL_GATE_DIRS[1]),
        ("project", project_path / PROJECT_ACCEPTED_GATE_DIR),
    ]
    if include_proposed:
        dirs.append(("proposed", project_path / PROJECT_PROPOSED_GATE_DIR))
    return dirs


def list_gate_specs(project_path: Path, include_proposed: bool = True) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for source, directory in gate_search_dirs(project_path, include_proposed=include_proposed):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.gate.json")):
            try:
                spec = load_gate_file(path)
                validation = validate_gate_spec(spec)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append({"source": source, "path": str(path), "error": str(exc)})
                continue
            gate_id = str(spec.get("gate_id", "")).strip()
            overrides = seen.get(gate_id)
            if gate_id:
                seen[gate_id] = str(path)
            entries.append({
                "gate_id": gate_id,
                "title": str(spec.get("title", "")),
                "status": str(spec.get("status", "")),
                "severity": str(spec.get("severity", "")),
                "source": source,
                "path": str(path),
                "ok": validation.ok,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "overrides": overrides,
            })
    return {
        "schema_version": "semantic-gate-registry.v1",
        "count": len(entries),
        "gates": entries,
        "errors": errors,
    }


def accept_proposed_gate(project_path: Path, gate_id: str) -> dict[str, Any]:
    proposed = project_path / PROJECT_PROPOSED_GATE_DIR / gate_filename(gate_id)
    if not proposed.exists():
        raise FileNotFoundError(proposed)
    spec = load_gate_file(proposed)
    validation = validate_gate_spec(spec)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    spec["status"] = "accepted"
    target = project_path / PROJECT_ACCEPTED_GATE_DIR / proposed.name
    write_gate_file(target, spec)
    proposed.unlink()
    return {
        "gate_id": str(spec.get("gate_id", gate_id)),
        "source": str(proposed),
        "target": str(target),
        "accepted": True,
    }
