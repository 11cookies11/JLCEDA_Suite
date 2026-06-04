#!/usr/bin/env python3
"""Validate generated KiCad pipeline artifacts for consistency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..shared.validation.common import ValidationReport, load_json
from ..domain.core.validation.summary import validate_summary


def validate_artifacts(
    summary_path: Path,
    *,
    strict: bool = False,
    require_erc: bool = False,
) -> ValidationReport:
    report = ValidationReport()
    summary = load_json(summary_path)
    report.stats["summary_schema"] = summary.get("schema_version", "")

    validate_summary(report, summary, summary_path)

    if require_erc and not report.stats.get("erc_enabled", False):
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
