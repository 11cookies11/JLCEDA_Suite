#!/usr/bin/env python3
"""ERC validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import ValidationReport, _as_dict, check_file_exists, load_json, repo_root, _nested_dict


def erc_record(summary: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        _as_dict(summary.get("erc")),
        _nested_dict(summary, "diagnostics", "kicad_erc"),
        _nested_dict(summary, "diagnostics", "erc"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return {}


def erc_paths(summary: dict[str, Any], summary_path: Path) -> dict[str, Path]:
    base = repo_root(summary_path)
    paths: dict[str, Path] = {}
    containers = (
        _as_dict(summary.get("files")),
        _as_dict(summary.get("output_files")),
        erc_record(summary),
        _nested_dict(summary, "diagnostics", "kicad_erc"),
    )
    for container in containers:
        for key, normalized in (
            ("kicad_erc_summary", "summary_file"),
            ("kicad_erc_report", "output_file"),
            ("summary_file", "summary_file"),
            ("output_file", "output_file"),
        ):
            raw = container.get(key)
            if isinstance(raw, str) and raw:
                paths[normalized] = (base / Path(raw)).resolve() if not Path(raw).is_absolute() else Path(raw)
    return paths


def validate_erc(report: ValidationReport, summary: dict[str, Any], summary_path: Path) -> None:
    erc = erc_record(summary)
    paths = erc_paths(summary, summary_path)
    summary_file = paths.get("summary_file")
    report_file = paths.get("output_file")

    if summary_file is not None:
        check_file_exists(report, summary_file, summary_file.name)
        if summary_file.exists():
            erc_file_summary = load_json(summary_file)
            report.stats["erc_schema"] = erc_file_summary.get("schema_version", "")
            report.stats["erc_finding_count"] = erc_file_summary.get("finding_count", 0)
            if erc and erc_file_summary.get("schema_version") != erc.get("schema_version", "kicad-erc-result.v1"):
                report.add_error(
                    "ERC summary schema mismatch: "
                    f"summary={erc.get('schema_version', '')} file={erc_file_summary.get('schema_version', '')}"
                )
            if erc and erc_file_summary.get("success") != erc.get("success"):
                report.add_error("ERC summary disagreement between pipeline summary and report file.")
            erc = erc_file_summary

    if report_file is not None:
        check_file_exists(report, report_file, report_file.name)

    if not erc:
        if summary_file is not None or report_file is not None:
            report.add_warning("ERC outputs were referenced but no ERC summary payload was found.")
        else:
            report.add_check("ERC: no ERC payload referenced")
        return

    enabled = bool(erc.get("enabled", False))
    attempted = bool(erc.get("attempted", False))
    success = bool(erc.get("success", False))
    finding_count = int(erc.get("finding_count", 0) or 0)

    report.stats.setdefault("erc_schema", erc.get("schema_version", ""))
    report.stats.setdefault("erc_finding_count", finding_count)
    report.stats["erc_enabled"] = enabled
    report.stats["erc_attempted"] = attempted
    report.stats["erc_success"] = success

    if not enabled:
        report.add_check("ERC: disabled or unavailable")
        error = str(erc.get("error", "")).strip()
        if error and error != "KICAD_CLI_NOT_FOUND":
            report.add_warning(f"ERC reported an error while disabled: {error}")
        elif error == "KICAD_CLI_NOT_FOUND":
            report.add_check("ERC executable: kicad-cli not found")
        return

    if not attempted:
        report.add_error("ERC was enabled but not attempted.")
        return

    if success:
        report.add_check(f"ERC: success with {finding_count} finding(s)")
        return

    error = str(erc.get("error", "")).strip()
    return_code = erc.get("return_code")
    if return_code is not None:
        report.add_error(f"ERC failed with return code {return_code}.")
    elif error:
        report.add_error(f"ERC failed: {error}")
    else:
        report.add_error("ERC failed without a captured error.")

