"""
Parts Pipeline 鈥?integrates Part Selector + KiCad Lib Importer into the KiCad pipeline.

Takes a circuit model (dict) and produces part.lock.yaml + part-risk-report.md
in the project output directory.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
from typing import Any

from ..lcsc_resolver import SearchBackend, describe_live_backend_status, get_default_backend
from ..part_selector import select_parts
from ..kicad_lib_importer import import_parts, _build_lock_data, _build_risk_report, _yaml_dumps
from .resolve import (
    build_mock_resolver_results as _mock_resolver_results,
    build_resolver_requests as _build_resolver_requests,
    build_part_requirements as _components_to_requirements,
    enrich_selected_parts_with_refs as _enrich_selected_with_refs,
    execute_resolver_requests as _execute_resolver_requests,
)
from .report import build_parts_summary


def run_parts_pipeline(
    model: dict[str, Any],
    output_dir: str | Path,
    *,
    project_name: str = "",
    run_importer: bool = False,
    mcp_backend: SearchBackend | None = None,
) -> dict[str, Any]:
    """Run the full parts pipeline: resolve 鈫?select 鈫?lock.

    Args:
        model: Circuit model dict (from synthesize_circuit_model / JSON).
        output_dir: Directory to write part.lock.yaml and part-risk-report.md.
        project_name: Project name for part.lock.yaml metadata.
        run_importer: If True, attempt to run easyeda2kicad to import parts.
        mcp_backend: Optional live backend for LCSC resolution.

    Returns:
        Dict with keys: lock_file, risk_report_file, selections, import_result (if run_importer).
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extract components
    components: list[dict[str, Any]] = []
    if isinstance(model.get("components"), list):
        components = model["components"]

    if not components:
        return {
            "lock_file": "",
            "risk_report_file": "",
            "selections": [],
            "warnings": ["No components found in circuit model"],
            "warning": "No components found in circuit model",
        }

    # Step 1: Convert components 鈫?PartRequirements
    requirements = _components_to_requirements(components)
    resolver_requests = _build_resolver_requests(requirements, components)

    # Step 2: Resolve LCSC parts (with graceful fallback if live lookup unavailable)
    live_available = bool(describe_live_backend_status().get("ok"))
    warnings: list[str] = []
    if live_available:
        try:
            backend = mcp_backend or get_default_backend(timeout=10.0)
            resolver_results = _execute_resolver_requests(resolver_requests, backend=backend)
        except Exception:
            live_available = False
            warnings.append("Live parts resolver unavailable; fell back to circuit-model-derived mock results.")

    if not live_available:
        warnings.append("Using mock parts resolver results from the circuit model.")
        resolver_results = _mock_resolver_results(requirements, components)

    # Step 3: Select best parts
    selections = select_parts(requirements, resolver_results)

    resolver_results_payload = [asdict(result) for result in resolver_results]
    selection_results_payload = [asdict(selection) for selection in selections]

    # Step 4: Enrich with reference designators
    selected_parts = _enrich_selected_with_refs(selections, components)

    result: dict[str, Any] = {
        "lock_file": "",
        "risk_report_file": "",
        "requirements": [asdict(req) for req in requirements],
        "resolver_requests": resolver_requests,
        "resolver_results": resolver_results_payload,
        "selection_results": selection_results_payload,
        "selections": [sel.selected for sel in selections if sel.selected],
        "warnings": warnings,
    }

    if not selected_parts:
        result["warning"] = "No parts were selected (MCP backend may be unavailable)"
        return result

    # Step 5: Run KiCad Library Importer (optional)
    if run_importer:
        try:
            import_result = import_parts(
                selected_parts,
                output_path,
                project_name=project_name,
            )
            result["import_result"] = {
                "imported_count": import_result.imported_count,
                "skipped_count": import_result.skipped_count,
                "failed_lcsc_ids": import_result.failed_lcsc_ids,
                "symbol_lib_file": import_result.symbol_lib_file,
                "footprint_lib_dir": import_result.footprint_lib_dir,
                "model_dir": import_result.model_dir,
                "errors": import_result.errors,
            }
            result["lock_file"] = import_result.lock_file
            result["risk_report_file"] = import_result.risk_report_file
            if import_result.warnings:
                result["warnings"].extend(import_result.warnings)
            if import_result.errors:
                result["warnings"].extend(import_result.errors)
        except Exception as exc:
            result["import_error"] = str(exc)
            result["warnings"].append(f"Parts importer failed: {exc}")

    # Step 6: Always generate lock file + risk report (even without importer)
    if not result.get("lock_file"):
        lock_data = _build_lock_data(selected_parts, [], {}, project_name=project_name)
        lock_path = output_path / "part.lock.yaml"
        lock_path.write_text(_yaml_dumps(lock_data) + "\n", encoding="utf-8")
        result["lock_file"] = str(lock_path)

        report = _build_risk_report(selected_parts)
        report_path = output_path / "part-risk-report.md"
        report_path.write_text(report, encoding="utf-8")
        result["risk_report_file"] = str(report_path)

    # Step 7: Summary
    result["summary"] = build_parts_summary(len(components), selected_parts)

    return result

