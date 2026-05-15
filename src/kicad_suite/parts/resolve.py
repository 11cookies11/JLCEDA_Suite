"""Parts resolution helpers."""

from __future__ import annotations

from typing import Any

from ..lcsc_resolver import PartRequirement, ResolverResult, ResolvedPart
from ..part_selector import SelectionResult, SelectedPart


def build_part_requirements(components: list[dict[str, Any]]) -> list[PartRequirement]:
    """Convert circuit model components to part requirements."""
    requirements: list[PartRequirement] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        role = str(comp.get("role", ""))
        value = str(comp.get("value", ""))
        ref = str(comp.get("ref", ""))
        sp = comp.get("selected_part") if isinstance(comp.get("selected_part"), dict) else {}
        pkg = str(sp.get("package", ""))

        preferred_mpn: list[str] = []
        mpn = str(sp.get("mpn", ""))
        if mpn:
            preferred_mpn.append(mpn)

        package_preferred: list[str] = []
        if pkg:
            package_preferred.append(pkg)

        requirements.append(
            PartRequirement(
                id=role or ref,
                function=value or role,
                preferred_mpn=preferred_mpn,
                package_preferred=package_preferred,
            )
        )

    return requirements


def build_mock_resolver_results(
    requirements: list[PartRequirement],
    components: list[dict[str, Any]],
) -> list[ResolverResult]:
    """Build mock resolver results from already-selected circuit parts."""
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


def enrich_selected_parts_with_refs(
    selections: list[SelectionResult],
    components: list[dict[str, Any]],
) -> list[SelectedPart]:
    """Attach refs and values from the circuit model to selected parts."""
    comp_by_role: dict[str, dict[str, Any]] = {}
    for comp in components:
        if isinstance(comp, dict):
            role = str(comp.get("role", ""))
            if role:
                comp_by_role[role] = comp

    parts: list[SelectedPart] = []
    for sel in selections:
        if sel.selected is None:
            continue
        part = sel.selected
        comp = comp_by_role.get(part.requirement_id, {})
        part.ref = str(comp.get("ref", ""))
        if comp.get("value"):
            part.value = str(comp.get("value", ""))
        parts.append(part)

    return parts


def part_risk(part: SelectedPart) -> str:
    """Get the part risk classification."""
    from ..part_selector import classify_package_risk

    return classify_package_risk(part.package)

