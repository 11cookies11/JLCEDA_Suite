#!/usr/bin/env python3
"""Shared helpers for artifact validation modules."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


OLD_REPO_PATH_PATTERNS = (
    "D:/GitRepository/AI/JLCEDA_Suite",
    "D:\\GitRepository\\AI\\JLCEDA_Suite",
    "JLCEDA_Suite",
)

TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".kicad_pcb",
    ".kicad_pro",
    ".kicad_sch",
    ".kicad_sym",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass
class ValidationReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_check(self, message: str) -> None:
        self.checks.append(message)


def load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text: str | None = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise UnicodeDecodeError("utf-8", raw, 0, 1, f"could not decode {path}")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def _resolve_path(base: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def repo_root(summary_path: Path) -> Path:
    for candidate in (summary_path.parent, *summary_path.parents):
        if (candidate / ".git").exists() or (candidate / "package.json").exists():
            return candidate
    return summary_path.parent


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested_dict(summary: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = summary
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return _as_dict(current)


def project_dir_from_summary(summary: dict[str, Any], summary_path: Path) -> Path | None:
    base = repo_root(summary_path)
    for container in (_as_dict(summary.get("files")), _as_dict(summary.get("output_files"))):
        for key in ("project", "schematic", "execution_plan", "part_lock"):
            raw = container.get(key)
            if isinstance(raw, str) and raw:
                return _resolve_path(base, raw).parent

    for key in ("project_file", "schematic_file"):
        raw = summary.get(key)
        if isinstance(raw, str) and raw:
            return _resolve_path(base, raw).parent

    hierarchical = _as_dict(summary.get("hierarchical_sheets"))
    root = hierarchical.get("root_schematic_file")
    if isinstance(root, str) and root:
        return _resolve_path(base, root).parent

    return None


def summary_project_files(summary: dict[str, Any], summary_path: Path) -> list[Path]:
    base = repo_root(summary_path)
    files: list[Path] = []
    for container in (_as_dict(summary.get("files")), _as_dict(summary.get("output_files"))):
        for key in (
            "project",
            "schematic",
            "summary",
            "part_lock",
            "part_risk_report",
            "execution_plan",
            "kicad_project",
            "kicad_schematic",
            "kicad_write_summary",
            "pipeline_summary",
        ):
            raw = container.get(key)
            if isinstance(raw, str) and raw:
                files.append(_resolve_path(base, raw))

    for key in ("project_file", "schematic_file", "summary_file"):
        raw = summary.get(key)
        if isinstance(raw, str) and raw:
            files.append(_resolve_path(base, raw))

    hierarchical = _as_dict(summary.get("hierarchical_sheets"))
    for key in ("root_schematic_file",):
        raw = hierarchical.get(key)
        if isinstance(raw, str) and raw:
            files.append(_resolve_path(base, raw))
    sheet_files = hierarchical.get("sheet_files")
    if isinstance(sheet_files, list):
        for raw in sheet_files:
            if isinstance(raw, str) and raw:
                files.append(_resolve_path(base, raw))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in files:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def check_file_exists(report: ValidationReport, path: Path, label: str) -> None:
    if path.exists():
        report.add_check(f"{label}: found")
    else:
        report.add_error(f"{label}: missing file at {path}")

