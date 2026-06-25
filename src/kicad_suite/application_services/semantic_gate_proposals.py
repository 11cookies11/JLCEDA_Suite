"""Generate reviewable semantic gate proposals from build artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .semantic_gate_registry import (
    PROJECT_PROPOSED_GATE_DIR,
    SEMANTIC_GATE_SCHEMA_VERSION,
    gate_filename,
    validate_gate_spec,
    write_gate_file,
)


HARDWARE_ERC_PATH = Path("build") / "hardware-erc.v1.json"


def propose_gates_from_hardware_erc(project_path: Path, include_warnings: bool = False) -> dict[str, Any]:
    """Create proposed gate specs from hardware ERC findings.

    The proposals are review artifacts only. They do not change export behavior
    until a later executor consumes accepted gate specs.
    """
    root = Path(project_path).resolve()
    erc_path = root / HARDWARE_ERC_PATH
    if not erc_path.is_file():
        raise FileNotFoundError(erc_path)
    erc = json.loads(erc_path.read_text(encoding="utf-8"))
    if not isinstance(erc, dict):
        raise ValueError(f"{erc_path} must contain a JSON object")

    findings: list[dict[str, Any]] = []
    findings.extend(_finding_dicts(erc.get("blockers", [])))
    if include_warnings:
        findings.extend(_finding_dicts(erc.get("warnings", [])))

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for finding in findings:
        spec = _proposal_from_finding(finding)
        validation = validate_gate_spec(spec)
        if not validation.ok:
            skipped.append({
                "code": str(finding.get("code", "")),
                "reason": "; ".join(validation.errors),
            })
            continue
        path = root / PROJECT_PROPOSED_GATE_DIR / gate_filename(str(spec["gate_id"]))
        write_gate_file(path, spec)
        written.append({
            "gate_id": str(spec["gate_id"]),
            "path": str(path),
            "severity": str(spec["severity"]),
            "source_code": str(finding.get("code", "")),
        })

    return {
        "schema_version": "semantic-gate-proposals.v1",
        "source": str(erc_path),
        "written": len(written),
        "skipped": skipped,
        "gates": written,
    }


def _finding_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _proposal_from_finding(finding: dict[str, Any]) -> dict[str, Any]:
    code = _clean_code(str(finding.get("code", "UNKNOWN_HARDWARE_ERC")))
    severity = str(finding.get("severity", "BLOCKER")).upper()
    if severity not in {"BLOCKER", "WARNING", "INFO"}:
        severity = "BLOCKER"
    gate_id = f"hardware.{code.lower()}.v1"
    message = str(finding.get("message", "")).strip()
    suggestion = str(finding.get("suggestion", "")).strip()
    return {
        "schema_version": SEMANTIC_GATE_SCHEMA_VERSION,
        "gate_id": gate_id,
        "title": f"Hardware ERC: {code}",
        "status": "proposed",
        "severity": severity,
        "scope": {
            "source": "hardware-erc",
            "component": finding.get("component"),
            "pin": finding.get("pin"),
            "net": finding.get("net"),
        },
        "source_finding": finding,
        "rules": [
            {
                "code": code,
                "description": message or f"Review hardware ERC finding {code}.",
                "suggestion": suggestion or "Review the circuit model and either repair it or document why this rule should be accepted.",
            }
        ],
    }


def _clean_code(code: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", code.strip().upper()).strip("_")
    return cleaned or "UNKNOWN_HARDWARE_ERC"
