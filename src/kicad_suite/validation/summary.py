#!/usr/bin/env python3
"""Summary validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import ValidationReport, _as_dict, check_file_exists, load_json, project_dir_from_summary, summary_project_files
from .erc import validate_erc
from .paths import scan_for_stale_paths
from .plan import validate_plan


def validate_summary(report: ValidationReport, summary: dict[str, Any], summary_path: Path) -> None:
    project_dir = project_dir_from_summary(summary, summary_path)
    if project_dir is not None:
        report.stats["project_dir"] = str(project_dir)
    else:
        report.add_warning("Could not infer project directory from summary.")

    top_level_warnings = summary.get("warnings", [])
    if isinstance(top_level_warnings, list):
        for warning in top_level_warnings:
            if isinstance(warning, str) and warning:
                report.add_warning(warning)

    for path in summary_project_files(summary, summary_path):
        check_file_exists(report, path, path.name)

    if project_dir is not None and project_dir.exists():
        stale = scan_for_stale_paths(project_dir)
        if stale:
            for item in stale:
                report.add_error(item)
        else:
            report.add_check("stale paths: none found")

    plan_path = None
    for container in (_as_dict(summary.get("files")), _as_dict(summary.get("output_files"))):
        raw = container.get("execution_plan") or container.get("kicad_execution_plan")
        if isinstance(raw, str) and raw:
            plan_path = (Path(raw) if Path(raw).is_absolute() else (summary_path.parent / Path(raw)).resolve())
            break
    if plan_path is None:
        raw = summary.get("execution_plan")
        if isinstance(raw, str) and raw:
            plan_path = (Path(raw) if Path(raw).is_absolute() else (summary_path.parent / Path(raw)).resolve())
    if plan_path is None:
        raw = _as_dict(_as_dict(summary.get("diagnostics")).get("kicad_erc")).get("execution_plan")
        if isinstance(raw, str) and raw:
            plan_path = (Path(raw) if Path(raw).is_absolute() else (summary_path.parent / Path(raw)).resolve())

    if plan_path is not None:
        if plan_path.exists():
            plan = load_json(plan_path)
            validate_plan(report, summary, plan)
            validate_erc(report, summary, summary_path)
        else:
            report.add_error(f"execution plan missing at {plan_path}")
    else:
        report.add_warning("Could not infer execution plan path from summary.")
