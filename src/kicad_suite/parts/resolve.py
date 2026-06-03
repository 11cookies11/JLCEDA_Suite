"""Parts resolution helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..lcsc_resolver import PartRequirement, ResolverResult, ResolvedPart, resolve_many, SearchBackend
from ..part_selector import SelectionResult, SelectedPart


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        item_str = str(item).strip()
        if item_str:
            result.append(item_str)
    return result


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
        pkg = str(comp.get("package", "")) or str(sp.get("package", ""))

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


def _role_search_hints(role: str, value: str) -> list[str]:
    role = role.strip().lower()
    value = value.strip()
    hints: list[str] = []
    if role in {"mcu", "main_mcu"}:
        hints.extend(["MCU", "STM32"])
    elif role in {"main_3v3_regulator", "ldo", "power_regulator"}:
        hints.extend(["3.3V LDO", "regulator", "SOT-223", "SOT-89", "SOT-23-5"])
    elif role in {"usb_c_power_input", "usb_c"}:
        hints.extend(["USB-C", "Type-C", "CC1", "CC2", "VBUS"])
    elif role in {"swd_debug_header", "debug_header"}:
        hints.extend(["SWD", "SWCLK", "SWDIO", "VTREF", "GND"])
    elif role in {"nrst_pullup", "reset_button"}:
        hints.extend(["NRST", "reset", "pullup"])
    elif role in {"boot0_pulldown"}:
        hints.extend(["BOOT0", "pulldown"])
    elif role in {"xtal_load_cap_1", "xtal_load_cap_2", "vdd_decoupling_1", "vdd_decoupling_2", "vdd_decoupling_3"}:
        hints.extend(["capacitor", "C0603", "C0402"])
    elif role in {"power_led", "indicator_led"}:
        hints.extend(["LED", "indicator"])
    elif role in {"user_button", "reset_button"}:
        hints.extend(["switch", "tactile"])
    if value and any(unit in value.lower() for unit in ("mhz", "khz")):
        hints.append("crystal")
    return list(dict.fromkeys(hints))


def build_resolver_requests(
    requirements: list[PartRequirement],
    components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build resolver request payloads from requirements and model components."""
    comp_by_role: dict[str, dict[str, Any]] = {}
    comp_by_ref: dict[str, dict[str, Any]] = {}
    for comp in components:
        if not isinstance(comp, dict):
            continue
        role = str(comp.get("role", "")).strip()
        ref = str(comp.get("ref", "")).strip()
        if role:
            comp_by_role[role] = comp
        if ref:
            comp_by_ref[ref] = comp

    requests: list[dict[str, Any]] = []
    for requirement in requirements:
        comp = comp_by_role.get(requirement.id) or comp_by_ref.get(requirement.id) or {}
        ref = str(comp.get("ref", requirement.id)).strip()
        role = str(comp.get("role", requirement.id)).strip()
        value = str(comp.get("value", requirement.function)).strip()
        selected = comp.get("selected_part", {}) if isinstance(comp.get("selected_part"), dict) else {}
        package = str(comp.get("package", "")).strip() or str(selected.get("package", "")).strip()
        mechanical_package = str(comp.get("mechanical_package", "")).strip() or str(selected.get("mechanical_package", "")).strip()
        manufacturer = str(comp.get("manufacturer", "")).strip() or str(selected.get("manufacturer", "")).strip()
        search_hints = _as_string_list(comp.get("search_hints", []))
        preferred_mpn = list(requirement.preferred_mpn)
        if not preferred_mpn:
            mpn = str(selected.get("mpn", "")).strip()
            if mpn:
                preferred_mpn.append(mpn)
        package_preferred = list(requirement.package_preferred)
        if not package_preferred and package:
            package_preferred.append(package)

        search_terms: list[str] = [term for term in (
            value,
            requirement.id,
            ref,
            *_role_search_hints(role, value),
            *search_hints,
        ) if term]
        if package:
            search_terms.append(package)
        if mechanical_package and mechanical_package != package:
            search_terms.append(mechanical_package)
        if manufacturer:
            search_terms.append(manufacturer)
        search_terms = list(dict.fromkeys(search_terms))

        filters: dict[str, Any] = {}
        if package:
            filters["package"] = package
        if mechanical_package:
            filters["mechanical_package"] = mechanical_package
        if manufacturer:
            filters["manufacturer"] = manufacturer
        if selected.get("lcsc_id"):
            filters["lcsc_id"] = str(selected.get("lcsc_id", ""))

        requests.append(
            {
                "request_id": f"{requirement.id}:{ref or requirement.id}",
                "component_ref": ref,
                "project_id": "",
                "role": role,
                "value": value,
                "operation": "search_part_candidates",
                "query": value or requirement.function or role,
                "search_terms": search_terms,
                "filters": filters,
                "priority": "high" if role in {"mcu", "usb_c_power_input", "swd_debug_header", "power_regulator", "ldo", "main_3v3_regulator"} else "medium",
                "generated_by": "parts-pipeline",
                "reason": "Derived from component role/value and selected_part hints.",
                "preferred_mpn": preferred_mpn,
                "package_preferred": package_preferred,
                "payload": {
                    "ref": ref,
                    "role": role,
                    "value": value,
                    "query": value or requirement.function or role,
                    "search_terms": search_terms,
                    "filters": filters,
                    "priority": "high" if role in {"mcu", "usb_c_power_input", "swd_debug_header", "power_regulator", "ldo", "main_3v3_regulator"} else "medium",
                    "preferred_mpn": preferred_mpn,
                    "package_preferred": package_preferred,
                },
            }
        )
    return requests


def execute_resolver_requests(
    resolver_requests: list[dict[str, Any]],
    backend: SearchBackend | None = None,
    *,
    max_candidates: int = 5,
) -> list[ResolverResult]:
    """Execute resolver requests through the live resolver."""
    requirements: list[PartRequirement] = []
    for request in resolver_requests:
        payload = request.get("payload", request) if isinstance(request, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        request_id = str(request.get("request_id", "")).strip() if isinstance(request, dict) else ""
        requirement_id = request_id.split(":", 1)[0] if request_id else ""
        if not requirement_id and isinstance(request, dict):
            requirement_id = str(request.get("component_ref", "")).strip()
        if not requirement_id and isinstance(request, dict):
            requirement_id = str(request.get("role", "")).strip()
        if not requirement_id and isinstance(payload, dict):
            requirement_id = str(payload.get("ref", "")).strip()
        role = str(payload.get("role", request.get("role", ""))).strip() if isinstance(request, dict) else ""
        value = str(payload.get("value", request.get("value", ""))).strip() if isinstance(request, dict) else ""
        preferred_mpn = _as_string_list(payload.get("preferred_mpn", request.get("preferred_mpn", []))) if isinstance(request, dict) else []
        package_preferred = _as_string_list(payload.get("package_preferred", request.get("package_preferred", []))) if isinstance(request, dict) else []
        if not preferred_mpn:
            mpn_hint = str(payload.get("mpn", "")).strip()
            if mpn_hint:
                preferred_mpn.append(mpn_hint)
        if not package_preferred:
            package_hint = str(payload.get("package", "")).strip()
            if package_hint:
                package_preferred.append(package_hint)
        requirements.append(
            PartRequirement(
                id=requirement_id or role or request_id,
                function=value or role or requirement_id,
                preferred_mpn=preferred_mpn,
                package_preferred=package_preferred,
                category=str(payload.get("category", request.get("category", ""))) if isinstance(request, dict) else "",
                in_stock_only=bool(payload.get("in_stock_only", True)),
                basic_only=bool(payload.get("basic_only", False)),
            )
        )
    return resolve_many(requirements, backend=backend, max_candidates=max_candidates)


def apply_selected_parts_to_model(
    model: dict[str, Any],
    selected_parts: list[SelectedPart | dict[str, Any]],
) -> dict[str, Any]:
    """Return a copy of the model with selected_part fields merged in by ref / requirement_id."""
    merged = deepcopy(model)
    if not isinstance(merged.get("components"), list):
        return merged

    by_ref: dict[str, dict[str, Any]] = {}
    by_requirement: dict[str, dict[str, Any]] = {}
    for item in selected_parts:
        if hasattr(item, "__dataclass_fields__"):
            payload = dict(item.__dict__)
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            continue
        clean = {k: v for k, v in payload.items() if v not in (None, "")}
        ref = str(clean.get("ref", "")).strip()
        requirement_id = str(clean.get("requirement_id", "")).strip()
        if ref:
            by_ref[ref] = clean
        if requirement_id:
            by_requirement[requirement_id] = clean

    for component in merged.get("components", []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", "")).strip()
        role = str(component.get("role", "")).strip()
        selected = by_ref.get(ref) or by_requirement.get(role)
        if not selected:
            continue
        existing = component.get("selected_part", {}) if isinstance(component.get("selected_part"), dict) else {}
        selected_part = dict(existing)
        for key in (
            "part_id",
            "display_name",
            "lcsc_id",
            "manufacturer",
            "mpn",
            "package",
            "mechanical_package",
            "kicad_footprint_hint",
            "library_uuid",
            "symbol_uuid",
            "place_uuid",
            "pin_count",
            "named_pin_count",
            "availability_status",
            "confidence",
            "source",
        ):
            if selected.get(key) not in (None, ""):
                selected_part[key] = selected[key]
        component["selected_part"] = selected_part
        if selected.get("needs_review") is not None:
            component["needs_review"] = bool(selected.get("needs_review"))
    return merged


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
