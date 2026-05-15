#!/usr/bin/env python3
"""Validate generated KiCad pipeline artifacts for consistency."""

from __future__ import annotations

import json
import argparse
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


def _project_dir_from_summary(summary: dict[str, Any], summary_path: Path) -> Path | None:
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


def _execution_plan_path(summary: dict[str, Any], summary_path: Path) -> Path | None:
    base = repo_root(summary_path)
    for container in (_as_dict(summary.get("files")), _as_dict(summary.get("output_files"))):
        raw = container.get("execution_plan") or container.get("kicad_execution_plan")
        if isinstance(raw, str) and raw:
            return _resolve_path(base, raw)
    raw = summary.get("execution_plan")
    if isinstance(raw, str) and raw:
        return _resolve_path(base, raw)
    raw = _nested_dict(summary, "diagnostics", "kicad_erc").get("execution_plan")
    if isinstance(raw, str) and raw:
        return _resolve_path(base, raw)
    return None


def _summary_project_files(summary: dict[str, Any], summary_path: Path) -> list[Path]:
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


def _check_file_exists(report: ValidationReport, path: Path, label: str) -> None:
    if path.exists():
        report.add_check(f"{label}: found")
    else:
        report.add_error(f"{label}: missing file at {path}")


def _walk_text_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"fp-lib-table", "sym-lib-table"}:
            files.append(path)
    return files


def _scan_for_stale_paths(project_dir: Path) -> list[str]:
    findings: list[str] = []
    for path in _walk_text_files(project_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for needle in OLD_REPO_PATH_PATTERNS:
            if needle in text:
                findings.append(f"{path}: contains stale path {needle}")
                break
    return findings


def _symbol_pin_conflicts(plan: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    symbols = plan.get("symbols")
    if not isinstance(symbols, list):
        return findings
    for symbol in symbols:
        if not isinstance(symbol, dict):
            continue
        ref = str(symbol.get("ref", ""))
        pins = symbol.get("pins")
        if not isinstance(pins, list):
            continue
        pin_map: dict[str, set[str]] = {}
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            number = str(pin.get("number", ""))
            net = str(pin.get("net", ""))
            if not number or not net:
                continue
            pin_map.setdefault(number, set()).add(net)
        for number, nets in pin_map.items():
            if len(nets) > 1:
                joined = ", ".join(sorted(nets))
                findings.append(f"{ref} pin {number} connects to multiple nets: {joined}")
    return findings


def _erc_record(summary: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        _as_dict(summary.get("erc")),
        _nested_dict(summary, "diagnostics", "kicad_erc"),
        _nested_dict(summary, "diagnostics", "erc"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return {}


def _erc_paths(summary: dict[str, Any], summary_path: Path) -> dict[str, Path]:
    base = repo_root(summary_path)
    paths: dict[str, Path] = {}
    containers = (
        _as_dict(summary.get("files")),
        _as_dict(summary.get("output_files")),
        _erc_record(summary),
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
                paths[normalized] = _resolve_path(base, raw)
    return paths


def _validate_erc(report: ValidationReport, summary: dict[str, Any], summary_path: Path) -> None:
    erc = _erc_record(summary)
    erc_paths = _erc_paths(summary, summary_path)
    summary_file = erc_paths.get("summary_file")
    report_file = erc_paths.get("output_file")

    if summary_file is not None:
        _check_file_exists(report, summary_file, summary_file.name)
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
        _check_file_exists(report, report_file, report_file.name)

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


def validate_artifacts(
    summary_path: Path,
    *,
    strict: bool = False,
    require_erc: bool = False,
) -> ValidationReport:
    report = ValidationReport()
    summary = load_json(summary_path)
    report.stats["summary_schema"] = summary.get("schema_version", "")

    project_dir = _project_dir_from_summary(summary, summary_path)
    if project_dir is not None:
        report.stats["project_dir"] = str(project_dir)
    else:
        report.add_warning("Could not infer project directory from summary.")

    files = _summary_project_files(summary, summary_path)
    for path in files:
        _check_file_exists(report, path, path.name)

    if project_dir is not None and project_dir.exists():
        stale = _scan_for_stale_paths(project_dir)
        if stale:
            for item in stale:
                report.add_error(item)
        else:
            report.add_check("stale paths: none found")

    plan_path = _execution_plan_path(summary, summary_path)
    if plan_path is not None:
        if plan_path.exists():
            plan = load_json(plan_path)
            report.stats["execution_plan_schema"] = plan.get("schema_version", "")

            summary_counts = _as_dict(summary.get("counts"))
            symbol_count = len(plan.get("symbols", [])) if isinstance(plan.get("symbols"), list) else 0
            net_count = len(plan.get("nets", [])) if isinstance(plan.get("nets"), list) else 0
            report.stats["symbols"] = symbol_count
            report.stats["nets"] = net_count

            expected_symbols = summary_counts.get("symbols")
            expected_nets = summary_counts.get("nets")
            if expected_symbols is not None and int(expected_symbols) != symbol_count:
                report.add_error(
                    f"symbol count mismatch: summary={expected_symbols} execution_plan={symbol_count}"
                )
            else:
                report.add_check("symbol count: ok")
            if expected_nets is not None and int(expected_nets) != net_count:
                report.add_error(f"net count mismatch: summary={expected_nets} execution_plan={net_count}")
            else:
                report.add_check("net count: ok")

            diagnostics = _as_dict(plan.get("diagnostics"))
            report.stats["plan_warnings"] = len(diagnostics.get("warnings", [])) if isinstance(diagnostics.get("warnings"), list) else 0
            report.stats["plan_unsupported"] = len(diagnostics.get("unsupported", [])) if isinstance(diagnostics.get("unsupported"), list) else 0
            report.add_check(
                f"plan diagnostics: {report.stats['plan_warnings']} warning(s), {report.stats['plan_unsupported']} unsupported item(s)"
            )

            conflicts = _symbol_pin_conflicts(plan)
            report.stats["shared_node_labels"] = len(conflicts)
            if conflicts:
                report.add_check(f"shared-node labels: {len(conflicts)}")
                report.stats["shared_node_label_examples"] = conflicts[:8]
            else:
                report.add_check("shared-node labels: none")

            _validate_erc(report, summary, summary_path)
        else:
            report.add_error(f"execution plan missing at {plan_path}")

    if require_erc:
        if not report.stats.get("erc_enabled", False):
            report.add_error("ERC was required but not enabled or not available.")

    if strict and report.warnings:
        report.ok = False
        report.add_error("strict mode requested and warnings were emitted")

    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True, help="Path to kicad-write-summary.json or run summary JSON.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--require-erc", action="store_true", help="Fail when ERC was not enabled or unavailable.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON report.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    report = validate_artifacts(args.summary, strict=args.strict, require_erc=args.require_erc)
    payload = {
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "checks": report.checks,
        "stats": report.stats,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Artifact validation")
        print(f"  ok: {report.ok}")
        for item in report.checks:
            print(f"  check: {item}")
        for item in report.warnings:
            print(f"  warn: {item}")
        for item in report.errors:
            print(f"  error: {item}")
    return 0 if report.ok else 1
