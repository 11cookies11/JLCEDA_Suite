"""Unified Report System: aggregate all project data into a single report.

Produces machine-readable JSON, human-readable Markdown, or plain-text output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project_state import ProjectState
from .erc_classification_service import ErcClassificationService
from ..domain.core.circuit_model_io import load_dual_circuit_model, resolve_model_paths
from ..domain.core.ir_compiler import build_ir
from ..shared.schema_versions import IR_SCHEMA_VERSION


REPORT_SCHEMA_VERSION = "report.v1"

# Format constants
FORMAT_JSON = "json"
FORMAT_MARKDOWN = "markdown"
FORMAT_TEXT = "text"
FORMATS = (FORMAT_JSON, FORMAT_MARKDOWN, FORMAT_TEXT)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_report(
    project_path: str | Path,
    model: dict[str, Any] | None = None,
    erc_result: dict[str, Any] | None = None,
    simulation_result: dict[str, Any] | None = None,
    history_limit: int = 20,
) -> dict[str, Any]:
    """Aggregate all available data sources into a unified report dict.

    Args:
        project_path: Project root containing ``source/`` and ``build/``.
        model: Pre-loaded merged circuit model dict (loaded from disk if None).
        erc_result: Optional ERC result dict from ``run_erc()``.
        simulation_result: Optional simulation result dict.
        history_limit: Max operation history entries to include.

    Returns a dict with schema_version ``"report.v1"``.
    """
    root = Path(project_path).resolve()

    # Load model if not provided.
    if model is None:
        model_path = root / "source" / "circuit-model.source.json"
        source_path, resolved_path = resolve_model_paths(model_path)
        if source_path.exists() or resolved_path.exists():
            model = load_dual_circuit_model(model_path)
        else:
            model = {}

    # Project state.
    ps = ProjectState(root)
    ps.load()

    # IR (best-effort ???may fail on broken references).
    ir: dict[str, Any] | None = None
    ir_error: str | None = None
    try:
        if model:
            ir = build_ir(model)
    except (ValueError, KeyError, TypeError) as exc:
        ir_error = str(exc)

    # Build sections.
    sections: list[dict[str, Any]] = []

    # 1. Project overview.
    sections.append(_section("project", "Project Overview", "info", {
        "project_name": str(ps.state.get("project", {}).get("name", "")),
        "project_id": str(ps.state.get("project", {}).get("id", "")),
        "status": ps.get_status(),
    }))

    # 2. Summary counts.
    sections.append(_section("summary", "Summary", "info", ps.get_summary()))

    # 3. DSL status.
    dsl = ps.state.get("dsl", {})
    sections.append(_section("dsl", "DSL Status", "ok" if dsl.get("hash") else "warning", {
        "path": str(dsl.get("path", "source/circuit-model.source.json")),
        "hash": str(dsl.get("hash", "")),
        "valid": dsl.get("valid"),
    }))

    # 4. Build status.
    build = ps.state.get("build", {})
    stale = ps.is_stale()
    build_status = "ok" if build.get("last_build_ok") else ("warning" if stale else "info")
    sections.append(_section("build", "Build Status", build_status, {
        "last_build_ok": build.get("last_build_ok", False),
        "last_build_at": build.get("last_build_at"),
        "input_dsl_hash": build.get("input_dsl_hash", ""),
        "stale": stale,
    }))

    # 5. Diagnostics.
    diag = ps.state.get("diagnostics", {})
    diag_status = "error" if diag.get("errors", 0) > 0 else ("warning" if diag.get("warnings", 0) > 0 else "ok")
    sections.append(_section("diagnostics", "Diagnostics", diag_status, {
        "errors": diag.get("errors", 0),
        "warnings": diag.get("warnings", 0),
        "items": diag.get("items", []),
    }))

    # 6. IR status.
    ir_status = "ok" if ir else "error"
    sections.append(_section("ir", "Resolved Hardware IR", ir_status, {
        "schema_version": IR_SCHEMA_VERSION,
        "compiled": ir is not None,
        "component_count": len(ir.get("components", [])) if ir else 0,
        "net_count": len(ir.get("nets", [])) if ir else 0,
        "error": ir_error,
    }))

    # 7. Component symbol status.
    comp_section = _component_status(model)
    sections.append(_section("components", "Component Symbol Status", comp_section["status"], comp_section))

    # 8. Risks.
    risks = model.get("risks", []) if isinstance(model.get("risks"), list) else []
    open_risks = sum(1 for r in risks if isinstance(r, dict) and r.get("status") not in ("resolved", "closed"))
    sections.append(_section("risks", "Risks", "warning" if open_risks > 0 else "ok", {
        "total": len(risks),
        "open": open_risks,
        "items": risks[:20] if risks else [],
    }))

    # 9. ERC details.
    if erc_result:
        erc_ok = erc_result.get("success", False)
        erc_data = _erc_details(erc_result)
        erc_data["attempted"] = erc_result.get("attempted", False)
        erc_data["success"] = erc_ok
        sections.append(_section("erc", "ERC", "ok" if erc_ok else "error", erc_data))

    # 10. Simulation (optional).
    if simulation_result:
        sections.append(_section("simulation", "Simulation", "info", {
            "plan_file": simulation_result.get("plan_file", ""),
            "scenario_count": simulation_result.get("plan", {}).get("summary", {}).get("scenario_count", 0),
        }))

    # 10. Operation history.
    history = ps.get_history(limit=history_limit)
    sections.append(_section("history", "Recent Operations", "info", {
        "count": len(history),
        "entries": history,
    }))

    # Compute overall status.
    overall = _overall_status(sections)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "project": {
            "name": str(ps.state.get("project", {}).get("name", "")),
            "id": str(ps.state.get("project", {}).get("id", "")),
            "status": ps.get_status(),
        },
        "sections": sections,
    }


def format_report(report: dict[str, Any], fmt: str = FORMAT_JSON) -> str:
    """Render a report dict into *fmt* (json, markdown, or text)."""
    if fmt == FORMAT_JSON:
        return json.dumps(report, ensure_ascii=False, indent=2)
    if fmt == FORMAT_TEXT:
        return _render_text(report)
    if fmt == FORMAT_MARKDOWN:
        return _render_markdown(report)
    raise ValueError(f"Unknown report format: {fmt}")


# ---------------------------------------------------------------------------
# Internal: data extractors
# ---------------------------------------------------------------------------


def _component_status(model: dict[str, Any]) -> dict[str, Any]:
    """Extract per-component symbol resolution status."""
    components = model.get("components", [])
    if not isinstance(components, list):
        return {"status": "info", "total": 0, "resolved": 0, "placeholder": 0, "items": []}

    items: list[dict[str, Any]] = []
    resolved = 0
    placeholder = 0
    for c in components:
        if not isinstance(c, dict):
            continue
        ref = str(c.get("ref", ""))
        sp = c.get("selected_part", {})
        sp = sp if isinstance(sp, dict) else {}
        lcsc = str(sp.get("lcsc_id", ""))
        has_symbol = bool(lcsc)
        if has_symbol:
            resolved += 1
        elif c.get("value"):
            placeholder += 1

        items.append({
            "ref": ref,
            "role": str(c.get("role", "")),
            "value": str(c.get("value", "")),
            "lcsc_id": lcsc or None,
            "symbol_ok": has_symbol,
        })

    status = "ok" if placeholder == 0 else ("warning" if resolved > 0 else "error")
    return {"status": status, "total": len(items), "resolved": resolved, "placeholder": placeholder, "items": items}


def _erc_details(erc_result: dict[str, Any]) -> dict[str, Any]:
    """Extract structured ERC violation details."""
    finding_count = erc_result.get("finding_count", 0)
    details: dict[str, Any] = {
        "finding_count": finding_count,
        "warnings": erc_result.get("warnings", []),
        "violations": [],
    }

    # Try to read the ERC JSON report for structured violations
    output_file = erc_result.get("output_file", "")
    if output_file:
        try:
            erc_data = json.loads(Path(output_file).read_text(encoding="utf-8"))
            from collections import Counter
            type_counts: Counter = Counter()
            examples: dict[str, str] = {}
            for sheet in erc_data.get("sheets", []):
                for v in sheet.get("violations", []):
                    vtype = str(v.get("type", "?"))
                    type_counts[vtype] += 1
                    if vtype not in examples:
                        examples[vtype] = str(v.get("description", ""))[:120]
            severities: dict[str, str] = {}
            for sheet in erc_data.get("sheets", []):
                for v in sheet.get("violations", []):
                    vtype = str(v.get("type", "?"))
                    severities.setdefault(vtype, str(v.get("severity", "?")))
            for vtype, count in type_counts.most_common(20):
                details["violations"].append({
                    "type": vtype,
                    "count": count,
                    "severity": severities.get(vtype, "?"),
                    "example": examples.get(vtype, ""),
                })
            details["classification"] = ErcClassificationService().classify_report(erc_data)
        except (OSError, json.JSONDecodeError, LookupError):
            pass

    return details


# ---------------------------------------------------------------------------
# Internal: section builder
# ---------------------------------------------------------------------------


def _section(key: str, title: str, status: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"key": key, "title": title, "status": status, "data": data}


def _overall_status(sections: list[dict[str, Any]]) -> str:
    priorities = {"error": 0, "warning": 1, "ok": 2, "info": 3}
    worst = "info"
    for s in sections:
        cur = s.get("status", "info")
        if priorities.get(cur, 99) < priorities.get(worst, 99):
            worst = cur
    return worst


# ---------------------------------------------------------------------------
# Internal: formatters
# ---------------------------------------------------------------------------


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Report: {report['project']['name']}",
        f"Status: {report['overall_status'].upper()}",
        f"Generated: {report['generated_at']}",
        "",
    ]
    for s in report.get("sections", []):
        lines.append(f"-- {s['title']} ({s['status']})")
        data = s.get("data", {})
        for k, v in data.items():
            if k in ("items", "entries"):
                continue
            lines.append(f"   {k}: {v}")
        lines.append("")
    return "\n".join(lines)


def _render_markdown(report: dict[str, Any]) -> str:
    status_emoji = {"ok": "[OK]", "warning": "[WARN]", "error": "[ERR]", "info": "[INFO]"}
    lines = [
        f"# Report: {report['project']['name']}",
        "",
        f"**Status:** {report['overall_status'].upper()}  ",
        f"**Generated:** {report['generated_at']}",
        "",
        "| Section | Status | Key Metrics |",
        "|---------|--------|-------------|",
    ]
    for s in report.get("sections", []):
        emoji = status_emoji.get(s.get("status", "info"), "")
        data = s.get("data", {})
        metrics = ", ".join(
            f"{k}={v}"
            for k, v in data.items()
            if k not in ("items", "entries") and v not in (None, "", [], {})
        )
        if len(metrics) > 80:
            metrics = metrics[:77] + "..."
        lines.append(f"| {emoji} {s['title']} | {s['status']} | {metrics} |")
    lines.append("")

    # Detail sections for items with errors/warnings.
    for s in report.get("sections", []):
        items = s.get("data", {}).get("items", [])
        if items and s.get("status") in ("error", "warning"):
            lines.append(f"## {s['title']}")
            for item in items:
                if isinstance(item, dict):
                    level = item.get("level", "info")
                    msg = item.get("message", str(item))
                    lines.append(f"- **[{level}]** {msg}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
    return "\n".join(lines)
