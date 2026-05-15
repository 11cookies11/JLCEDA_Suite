#!/usr/bin/env python3
"""Plan validation helpers."""

from __future__ import annotations

from typing import Any

from .common import ValidationReport, _as_dict


def symbol_pin_conflicts(plan: dict[str, Any]) -> list[str]:
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


def validate_plan(report: ValidationReport, summary: dict[str, Any], plan: dict[str, Any]) -> None:
    report.stats["execution_plan_schema"] = plan.get("schema_version", "")

    summary_counts = _as_dict(summary.get("counts"))
    symbol_count = len(plan.get("symbols", [])) if isinstance(plan.get("symbols"), list) else 0
    net_count = len(plan.get("nets", [])) if isinstance(plan.get("nets"), list) else 0
    report.stats["symbols"] = symbol_count
    report.stats["nets"] = net_count

    expected_symbols = summary_counts.get("symbols")
    expected_nets = summary_counts.get("nets")
    if expected_symbols is not None and int(expected_symbols) != symbol_count:
        report.add_error(f"symbol count mismatch: summary={expected_symbols} execution_plan={symbol_count}")
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

    conflicts = symbol_pin_conflicts(plan)
    report.stats["shared_node_labels"] = len(conflicts)
    if conflicts:
        report.add_check(f"shared-node labels: {len(conflicts)}")
        report.stats["shared_node_label_examples"] = conflicts[:8]
    else:
        report.add_check("shared-node labels: none")

