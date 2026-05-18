#!/usr/bin/env python3
"""Summary builders for KiCad pipeline outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _collect_warnings(*sources: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for source in sources:
        for item in source.get("warnings", []):
            if isinstance(item, str) and item:
                warnings.append(item)
        error = source.get("error")
        if isinstance(error, str) and error:
            warnings.append(error)
        if source.get("import_error"):
            warnings.append(str(source["import_error"]))
        registration = source.get("library_registration")
        if isinstance(registration, dict) and registration.get("attempted") and not registration.get("success", False):
            stderr = registration.get("stderr", "")
            warnings.append(f"library registration failed: {stderr or 'unknown error'}")
        gui_assets = source.get("gui_asset_validation")
        if isinstance(gui_assets, dict) and gui_assets.get("attempted") and not gui_assets.get("success", False):
            for issue in gui_assets.get("issues", []):
                warnings.append(f"GUI asset validation failed: {issue}")
    seen: set[str] = set()
    unique: list[str] = []
    for item in warnings:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def build_run_pipeline_summary(
    *,
    project_name: str,
    output_dir: Path,
    model_path: str,
    plan_file: str,
    write_result: dict[str, Any],
    erc_result: dict[str, Any],
    parts_result: dict[str, Any],
    plan_diagnostics: dict[str, Any],
    postprocess: dict[str, Any],
    simulation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical summary payload for scripts/run_pipeline.py."""
    warnings = _collect_warnings(erc_result, parts_result, postprocess)
    return {
        "project_name": project_name,
        "output_dir": str(output_dir),
        "files": {
            "circuit_model": str(model_path),
            "execution_plan": plan_file,
            "project": write_result.get("project_file"),
            "schematic": write_result.get("schematic_file"),
            "board": write_result.get("board_file", ""),
            "summary": write_result.get("summary_file"),
            "kicad_erc_summary": erc_result.get("summary_file", ""),
            "kicad_erc_report": erc_result.get("output_file", ""),
            "part_lock": parts_result.get("lock_file", ""),
            "part_risk_report": parts_result.get("risk_report_file", ""),
            "simulation_profile": (simulation_result or {}).get("profile_file", ""),
            "simulation_plan": (simulation_result or {}).get("plan_file", ""),
            "simulation_task_plan": (simulation_result or {}).get("task_plan_file", ""),
            "event_log": (simulation_result or {}).get("event_log_file", ""),
        },
        "counts": {
            "symbols": write_result.get("symbol_count", 0),
            "nets": write_result.get("net_count", 0),
            "board_footprints": write_result.get("board_footprints", 0),
            "board_warnings": len(write_result.get("board_warnings", [])),
        },
        "erc": {
            "schema_version": erc_result.get("schema_version", ""),
            "enabled": erc_result.get("enabled", False),
            "attempted": erc_result.get("attempted", False),
            "success": erc_result.get("success", False),
            "return_code": erc_result.get("return_code", None),
            "findings": erc_result.get("finding_count", 0),
            "executable": erc_result.get("executable", ""),
            "summary_file": erc_result.get("summary_file", ""),
            "output_file": erc_result.get("output_file", ""),
            "error": erc_result.get("error", ""),
        },
        "diagnostics": plan_diagnostics,
        "postprocess": postprocess,
        "simulation": simulation_result or {},
        "symbols_injected": bool(postprocess.get("symbols_injected", False)),
        "warnings": warnings,
    }
