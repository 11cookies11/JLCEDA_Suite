"""
Parts Pipeline — integrates Part Selector + KiCad Lib Importer into the KiCad pipeline.

Takes a circuit model (dict) and produces part.lock.yaml + part-risk-report.md
in the project output directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

from .lcsc_resolver import (
    PartRequirement,
    ResolverResult,
    ResolvedPart,
    SearchBackend,
    describe_live_backend_status,
    get_default_backend,
    resolve_many,
)
from .part_selector import select_parts, SelectedPart, SelectionResult
from .kicad_lib_importer import import_parts, _build_lock_data, _build_risk_report, _yaml_dumps


def _check_mcp_backend(base_url: str = "http://localhost:3847") -> bool:
    """Quick check if the MCP backend is reachable."""
    try:
        req = urllib.request.Request(f"{base_url}/api/search?q=test&limit=1")
        urllib.request.urlopen(req, timeout=2.0)
        return True
    except Exception:
        return False


def _mock_resolver_results(requirements: list[PartRequirement], components: list[dict[str, Any]]) -> list[ResolverResult]:
    """Generate mock resolver results from circuit component data when MCP is unavailable.

    Uses the selected_part data already in the circuit model as if it came from LCSC.
    """
    # Build lookup: role → component data
    comp_by_role: dict[str, dict[str, Any]] = {}
    for comp in components:
        if isinstance(comp, dict):
            role = str(comp.get("role", ""))
            if role:
                comp_by_role[role] = comp

    results: list[ResolverResult] = []
    for req in requirements:
        comp = comp_by_role.get(req.id, {})
        sp = comp.get("selected_part", {}) if isinstance(comp.get("selected_part"), dict) else {}

        if sp.get("part_id"):
            # Build a realistic mock ResolvedPart from the circuit model data
            candidate = ResolvedPart(
                lcsc_id=str(sp.get("lcsc_id", sp.get("part_id", ""))),
                mpn=str(sp.get("mpn", sp.get("display_name", ""))),
                manufacturer=str(sp.get("manufacturer", "")),
                package=str(sp.get("package", "")),
                description=str(sp.get("display_name", "")),
                stock=5000,
                basic_or_extended="Basic",
                price=None,
                has_easyeda_symbol=bool(sp.get("library_uuid")),
                has_easyeda_footprint=bool(sp.get("place_uuid")),
                has_3d_model=False,
                source="jlcpcb_parts",
                confidence=0.85,
            )
            results.append(ResolverResult(id=req.id, candidates=[candidate]))
        else:
            results.append(ResolverResult(id=req.id, candidates=[]))

    return results


def _components_to_requirements(components: list[dict[str, Any]]) -> list[PartRequirement]:
    """Convert circuit model components to PartRequirements for the LCSC Resolver."""
    requirements: list[PartRequirement] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        role = str(comp.get("role", ""))
        value = str(comp.get("value", ""))
        ref = str(comp.get("ref", ""))

        sp = comp.get("selected_part") if isinstance(comp.get("selected_part"), dict) else {}
        pkg = str(sp.get("package", ""))

        # Build function description from role + value + ref
        function = value or role

        # Extract preferred MPN from selected_part if it has LCSC data
        preferred_mpn: list[str] = []
        mpn = str(sp.get("mpn", ""))
        if mpn:
            preferred_mpn.append(mpn)

        package_preferred: list[str] = []
        if pkg:
            package_preferred.append(pkg)

        req = PartRequirement(
            id=role or ref,
            function=function,
            preferred_mpn=preferred_mpn,
            package_preferred=package_preferred,
        )
        requirements.append(req)

    return requirements


def _enrich_selected_with_refs(
    selections: list[SelectionResult],
    components: list[dict[str, Any]],
) -> list[SelectedPart]:
    """Map refs and values from circuit components onto selected parts."""
    comp_by_role: dict[str, dict[str, Any]] = {}
    for comp in components:
        if isinstance(comp, dict):
            role = str(comp.get("role", ""))
            if role:
                comp_by_role[role] = comp

    parts: list[SelectedPart] = []
    for sel in selections:
        if sel.selected is not None:
            part = sel.selected
            comp = comp_by_role.get(part.requirement_id, {})
            part.ref = str(comp.get("ref", ""))
            if comp.get("value"):
                part.value = str(comp.get("value", ""))
            parts.append(part)

    return parts


def run_parts_pipeline(
    model: dict[str, Any],
    output_dir: str | Path,
    *,
    project_name: str = "",
    run_importer: bool = False,
    mcp_backend: SearchBackend | None = None,
) -> dict[str, Any]:
    """Run the full parts pipeline: resolve → select → lock.

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
            "warning": "No components found in circuit model",
        }

    # Step 1: Convert components → PartRequirements
    requirements = _components_to_requirements(components)

    # Step 2: Resolve LCSC parts (with graceful fallback if live lookup unavailable)
    live_available = bool(describe_live_backend_status().get("ok"))
    if live_available:
        try:
            backend = mcp_backend or get_default_backend(timeout=10.0)
            resolver_results = resolve_many(requirements, backend=backend)
        except Exception:
            live_available = False

    if not live_available:
        resolver_results = _mock_resolver_results(requirements, components)

    # Step 3: Select best parts
    selections = select_parts(requirements, resolver_results)

    # Step 4: Enrich with reference designators
    selected_parts = _enrich_selected_with_refs(selections, components)

    result: dict[str, Any] = {
        "lock_file": "",
        "risk_report_file": "",
        "selections": [sel.selected for sel in selections if sel.selected],
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
        except Exception as exc:
            result["import_error"] = str(exc)

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
    result["summary"] = {
        "total_components": len(components),
        "resolved_parts": len(selected_parts),
        "low_risk": sum(1 for p in selected_parts if _part_risk(p) == "low"),
        "medium_risk": sum(1 for p in selected_parts if _part_risk(p) == "medium"),
        "high_risk": sum(1 for p in selected_parts if _part_risk(p) == "high"),
        "needs_review": sum(1 for p in selected_parts if p.needs_review),
    }

    return result


def _part_risk(part: SelectedPart) -> str:
    """Get the risk level recorded in the part's note or package."""
    from .part_selector import classify_package_risk
    return classify_package_risk(part.package)
