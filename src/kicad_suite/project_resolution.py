"""Project-level resolution manifest.

This sits between the editable DSL and the IR.
It records how a specific project searched, resolved, and verified parts
without relying on any shared mapping table.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parts.resolve import _as_string_list, _role_search_hints
from .schema_versions import PROJECT_RESOLUTION_SCHEMA_VERSION
from .symbol_footprint_resolver import footprint_exists, symbol_mapping_for


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean_part(part: Any) -> dict[str, Any]:
    if not isinstance(part, dict):
        if is_dataclass(part):
            part = asdict(part)
        else:
            return {}
    result: dict[str, Any] = {}
    for key in (
        "part_id",
        "display_name",
        "lcsc_id",
        "manufacturer",
        "mpn",
        "package",
        "mechanical_package",
        "description",
        "basic_or_extended",
        "price",
        "stock",
        "has_easyeda_symbol",
        "has_easyeda_footprint",
        "has_3d_model",
        "composite_score",
        "reasons",
        "risks",
        "needs_review",
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
        value = part.get(key)
        if value not in (None, ""):
            result[key] = value
    return result


def _selection_ref(item: Any) -> str:
    if not isinstance(item, dict):
        if is_dataclass(item):
            item = asdict(item)
        else:
            return ""
    for key in ("ref", "requirement_ref", "requirement_id"):
        value = str(item.get(key, "")).strip()
        if value:
            return value
    return ""


def _normalise_candidates(candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    return [_clean_part(item) for item in candidates]


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float, float, str, str]:
    composite = candidate.get("composite_score", 0) or 0
    confidence = candidate.get("confidence", 0) or 0
    stock = candidate.get("stock", 0) or 0
    try:
        composite_f = float(composite)
    except (TypeError, ValueError):
        composite_f = 0.0
    try:
        confidence_f = float(confidence)
    except (TypeError, ValueError):
        confidence_f = 0.0
    try:
        stock_f = float(stock)
    except (TypeError, ValueError):
        stock_f = 0.0
    lcsc_id = str(candidate.get("lcsc_id", "")).strip()
    part_id = str(candidate.get("part_id", "")).strip()
    return (composite_f, confidence_f, stock_f, lcsc_id, part_id)


def _candidate_label(candidate: dict[str, Any], component: dict[str, Any] | None = None) -> str:
    display_name = str(candidate.get("display_name", "")).strip()
    mpn = str(candidate.get("mpn", "")).strip()
    part_id = str(candidate.get("part_id", "")).strip()
    value = str(component.get("value", "")).strip() if isinstance(component, dict) else ""
    role = str(component.get("role", "")).strip() if isinstance(component, dict) else ""
    if display_name and mpn and display_name != mpn:
        return f"{display_name} ({mpn})"
    return display_name or mpn or part_id or value or role or "unknown"


def _candidate_matches_selected(candidate: dict[str, Any], selected_part: dict[str, Any]) -> bool:
    if not candidate or not selected_part:
        return False
    candidate_ids = {
        str(candidate.get("lcsc_id", "")).strip(),
        str(candidate.get("part_id", "")).strip(),
        str(candidate.get("mpn", "")).strip().lower(),
        str(candidate.get("display_name", "")).strip().lower(),
    }
    selected_ids = {
        str(selected_part.get("lcsc_id", "")).strip(),
        str(selected_part.get("part_id", "")).strip(),
        str(selected_part.get("mpn", "")).strip().lower(),
        str(selected_part.get("display_name", "")).strip().lower(),
    }
    return any(item and item in selected_ids for item in candidate_ids)


def _candidate_reselect_reason(candidate: dict[str, Any], selected_part: dict[str, Any]) -> str:
    reasons: list[str] = []
    if candidate.get("has_easyeda_symbol") and candidate.get("has_easyeda_footprint"):
        reasons.append("symbol+footprint available")
    if candidate.get("composite_score") not in (None, ""):
        reasons.append(f"score={candidate.get('composite_score')}")
    elif candidate.get("confidence") not in (None, ""):
        reasons.append(f"confidence={candidate.get('confidence')}")
    if candidate.get("basic_or_extended"):
        reasons.append(str(candidate.get("basic_or_extended")))
    if candidate.get("package"):
        reasons.append(str(candidate.get("package")))
    if _candidate_matches_selected(candidate, selected_part):
        reasons.append("matches current selection")
    return ", ".join(reasons) if reasons else "candidate from live resolver"


def _build_candidate_suggestions(
    component: dict[str, Any],
    candidate_parts: list[dict[str, Any]],
    selected_part: dict[str, Any],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    ranked = sorted(candidate_parts, key=_candidate_sort_key, reverse=True)
    suggestions: list[dict[str, Any]] = []
    for index, candidate in enumerate(ranked[:limit], start=1):
        suggestions.append(
            {
                "rank": index,
                "part_id": str(candidate.get("part_id", candidate.get("lcsc_id", ""))),
                "display_name": _candidate_label(candidate, component),
                "lcsc_id": str(candidate.get("lcsc_id", "")),
                "mpn": str(candidate.get("mpn", "")),
                "package": str(candidate.get("package", "")),
                "mechanical_package": str(candidate.get("mechanical_package", "")),
                "confidence": candidate.get("confidence"),
                "composite_score": candidate.get("composite_score"),
                "source": str(candidate.get("source", "")),
                "why": _candidate_reselect_reason(candidate, selected_part),
            }
        )
    return suggestions


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}



def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _selected_text(component: dict[str, Any], selected_part: dict[str, Any]) -> str:
    role = str(component.get("role", "")).strip()
    value = str(component.get("value", "")).strip()
    display_name = str(selected_part.get("display_name", "")).strip()
    mpn = str(selected_part.get("mpn", "")).strip()
    if display_name and mpn and display_name != mpn:
        return f"{display_name} ({mpn})"
    return display_name or mpn or value or role or "unknown"


def _build_search_plan(component: dict[str, Any], selected_part: dict[str, Any]) -> dict[str, Any]:
    ref = str(component.get("ref", "")).strip()
    role = str(component.get("role", "")).strip()
    value = str(component.get("value", "")).strip()
    package = str(component.get("package", "")).strip() or str(selected_part.get("package", "")).strip()
    mechanical_package = str(component.get("mechanical_package", "")).strip() or str(selected_part.get("mechanical_package", "")).strip()
    manufacturer = str(component.get("manufacturer", "")).strip() or str(selected_part.get("manufacturer", "")).strip()
    lcsc_id = str(selected_part.get("lcsc_id", "")).strip()
    mpn = str(selected_part.get("mpn", "")).strip()
    search_hints = _as_string_list(component.get("search_hints", []))

    search_terms: list[str] = []
    for term in (value, mpn, lcsc_id, str(selected_part.get("display_name", "")).strip(), role, ref, *search_hints):
        if term:
            search_terms.append(term)
    search_terms.extend(_role_search_hints(role, value))
    if package:
        search_terms.append(package)
    if mechanical_package and mechanical_package != package:
        search_terms.append(mechanical_package)

    filters: dict[str, Any] = {}
    if package:
        filters["package"] = package
    if mechanical_package:
        filters["mechanical_package"] = mechanical_package
    if manufacturer:
        filters["manufacturer"] = manufacturer
    if lcsc_id:
        filters["lcsc_id"] = lcsc_id

    priority = "high" if role in {"mcu", "usb_c_power_input", "swd_debug_header", "power_regulator", "ldo"} else "medium"
    if lcsc_id and mpn:
        priority = "high"

    reason = "Derived from DSL component metadata and selected_part hints."
    if lcsc_id:
        reason = "Selected part already carries a concrete LCSC identifier."
    elif value:
        reason = "Component value provides the strongest search anchor."

    return {
        "component_ref": ref,
        "role": role,
        "value": value,
        "search_terms": _dedupe_strings(search_terms),
        "filters": filters,
        "priority": priority,
        "generated_by": "dsl-heuristic",
        "reason": reason,
    }


def _build_resolution_result(
    component: dict[str, Any],
    selected_part: dict[str, Any],
    candidate_parts: list[dict[str, Any]],
    symbol: str,
    footprint: str,
    footprint_found: bool | None,
    *,
    parts_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    search_plan = _build_search_plan(component, selected_part)
    selected_candidate = dict(selected_part) if selected_part else {}

    candidates = candidate_parts[:]
    if not candidates and selected_candidate:
        candidates = [selected_candidate]
    ranked_candidates = sorted(candidates, key=_candidate_sort_key, reverse=True)

    import_result = (parts_result or {}).get("import_result", {})
    failed_lcsc_ids = {
        str(item).strip()
        for item in import_result.get("failed_lcsc_ids", [])
        if str(item).strip()
    } if isinstance(import_result, dict) else set()
    selected_lcsc_id = str(selected_part.get("lcsc_id", "")).strip()
    if selected_lcsc_id and selected_lcsc_id in failed_lcsc_ids:
        download_status = "failed"
    elif parts_result:
        download_status = "ok"
    else:
        download_status = "not_run"

    status = "unresolved"
    if selected_part:
        status = "selected"
        if symbol and footprint and footprint_found is not False:
            status = "resolved"
        elif symbol or footprint:
            status = "partial"

    recommended_candidates = _build_candidate_suggestions(component, ranked_candidates, selected_candidate)
    best_candidate = recommended_candidates[0] if recommended_candidates else {}
    candidate_count = len(ranked_candidates)

    return {
        "backend": "project_dsl" if not parts_result else "parts_pipeline",
        "search_plan": search_plan,
        "query_context": {
            "component_ref": str(component.get("ref", "")),
            "search_terms": search_plan["search_terms"],
            "filters": search_plan["filters"],
        },
        "candidate_count": candidate_count,
        "candidates": candidates,
        "recommended_candidates": recommended_candidates,
        "best_candidate": best_candidate,
        "selected_candidate": selected_candidate,
        "resolved_symbol": symbol,
        "resolved_footprint": footprint,
        "footprint_exists": footprint_found,
        "download_status": download_status,
        "status": status,
    }


def _build_search_queue_entry(component: dict[str, Any], search_plan: dict[str, Any]) -> dict[str, Any]:
    """Build a compact queue item for AI/resolver search stages."""
    return {
        "ref": str(component.get("ref", "")),
        "role": str(component.get("role", "")),
        "value": str(component.get("value", "")),
        "priority": str(search_plan.get("priority", "medium")),
        "search_terms": _as_string_list(search_plan.get("search_terms", [])),
        "filters": dict(search_plan.get("filters", {})) if isinstance(search_plan.get("filters", {}), dict) else {},
        "generated_by": str(search_plan.get("generated_by", "dsl-heuristic")),
        "reason": str(search_plan.get("reason", "")),
    }


def _build_resolver_request(
    component: dict[str, Any],
    search_queue_entry: dict[str, Any],
    *,
    project_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Build a standard resolver request object from a search queue entry."""
    search_terms = _as_string_list(search_queue_entry.get("search_terms", []))
    filters = dict(search_queue_entry.get("filters", {})) if isinstance(search_queue_entry.get("filters", {}), dict) else {}
    query = " ".join(search_terms).strip()
    if not query:
        query = str(search_queue_entry.get("value", "")).strip()
    if filters:
        filter_bits = [f"{key}={value}" for key, value in sorted(filters.items()) if str(value).strip()]
    else:
        filter_bits = []
    return {
        "request_id": f"{request_id}:{search_queue_entry.get('ref', '')}",
        "project_id": project_id,
        "component_ref": str(component.get("ref", "")),
        "role": str(component.get("role", "")),
        "operation": "search_part_candidates",
        "query": query,
        "search_terms": search_terms,
        "filters": filters,
        "filter_query": " ".join(filter_bits),
        "priority": str(search_queue_entry.get("priority", "medium")),
        "generated_by": str(search_queue_entry.get("generated_by", "dsl-heuristic")),
        "reason": str(search_queue_entry.get("reason", "")),
        "payload": {
            "ref": str(component.get("ref", "")),
            "role": str(component.get("role", "")),
            "value": str(component.get("value", "")),
            "query": query,
            "search_terms": search_terms,
            "filters": filters,
            "priority": str(search_queue_entry.get("priority", "medium")),
        },
    }


def _build_verification_report(
    component: dict[str, Any],
    selected_part: dict[str, Any],
    candidate_parts: list[dict[str, Any]],
    search_plan: dict[str, Any],
    symbol: str,
    footprint: str,
    footprint_found: bool | None,
    *,
    parts_result: dict[str, Any] | None = None,
    needs_reselection: bool = False,
) -> dict[str, Any]:
    import_result = (parts_result or {}).get("import_result", {})
    failed_lcsc_ids = {
        str(item).strip()
        for item in import_result.get("failed_lcsc_ids", [])
        if str(item).strip()
    } if isinstance(import_result, dict) else set()

    selected_lcsc_id = str(selected_part.get("lcsc_id", "")).strip()
    missing_fields: list[str] = []
    for key in ("part_id", "display_name", "lcsc_id", "mpn", "package"):
        if not str(selected_part.get(key, "")).strip():
            missing_fields.append(key)

    mismatch_fields: list[str] = []
    if symbol.startswith("AIAgent:"):
        mismatch_fields.append("symbol")
    if footprint and footprint_found is False:
        mismatch_fields.append("footprint")
    if selected_lcsc_id and selected_lcsc_id in failed_lcsc_ids:
        mismatch_fields.append("download")

    candidate_count = len(candidate_parts)
    ranked_candidates = sorted(candidate_parts, key=_candidate_sort_key, reverse=True)
    best_candidate = ranked_candidates[0] if ranked_candidates else {}
    best_candidate_matches_selected = _candidate_matches_selected(best_candidate, selected_part) if best_candidate else False
    if candidate_count and selected_part and not best_candidate_matches_selected and selected_lcsc_id:
        mismatch_fields.append("candidate_mismatch")

    if not selected_part:
        status = "unresolved"
        trust_level = "unverified"
    elif mismatch_fields or missing_fields or needs_reselection:
        status = "reselect_required"
        trust_level = "unverified"
    elif footprint and footprint_found is True and symbol:
        status = "verified"
        trust_level = "verified"
    else:
        status = "provisional"
        trust_level = "provisional"

    if selected_lcsc_id and selected_lcsc_id in failed_lcsc_ids:
        download_status = "failed"
    elif footprint and footprint_found is False:
        download_status = "missing"
    elif selected_part:
        download_status = "ok" if symbol and footprint else "not_run"
    else:
        download_status = "not_run"

    search_terms = _as_string_list(search_plan.get("search_terms", []))
    filters = search_plan.get("filters", {}) if isinstance(search_plan.get("filters", {}), dict) else {}

    reason_parts: list[str] = []
    if missing_fields:
        reason_parts.append(f"missing fields: {', '.join(missing_fields)}")
    if mismatch_fields:
        reason_parts.append(f"mismatch fields: {', '.join(mismatch_fields)}")
    if selected_lcsc_id and selected_lcsc_id in failed_lcsc_ids:
        reason_parts.append(f"import failed for lcsc_id {selected_lcsc_id}")
    if candidate_count:
        reason_parts.append(
            f"{candidate_count} candidate(s) from resolver; best is {str(best_candidate.get('part_id', best_candidate.get('lcsc_id', 'unknown'))).strip() or 'unknown'}"
        )
    else:
        reason_parts.append("no resolver candidates available for comparison")
    if not reason_parts:
        reason_parts.append("Selected part, symbol, and footprint are consistent enough for downstream use.")

    reselect_suggestions = _build_candidate_suggestions(component, ranked_candidates, selected_part)
    if not reselect_suggestions and search_terms:
        reselect_suggestions = [
            {
                "rank": 1,
                "part_id": "",
                "display_name": _candidate_label(selected_part or {}, component),
                "lcsc_id": selected_lcsc_id,
                "mpn": str(selected_part.get("mpn", "")).strip(),
                "package": str(selected_part.get("package", "")).strip(),
                "mechanical_package": str(selected_part.get("mechanical_package", "")).strip(),
                "confidence": selected_part.get("confidence"),
                "composite_score": selected_part.get("composite_score"),
                "source": str(selected_part.get("source", "")),
                "why": "reuse current search terms to re-query the resolver",
                "search_terms": search_terms,
                "filters": filters,
            }
        ]

    return {
        "status": status,
        "trust_level": trust_level,
        "source_backend": "parts_pipeline" if parts_result else "dsl_only",
        "download_status": download_status,
        "mismatch_fields": mismatch_fields,
        "missing_fields": missing_fields,
        "reselect_required": bool(needs_reselection or mismatch_fields or missing_fields),
        "candidate_count": candidate_count,
        "best_candidate": best_candidate,
        "best_candidate_matches_selected": best_candidate_matches_selected,
        "reselect_suggestions": reselect_suggestions,
        "reason": "; ".join(reason_parts),
        "checked_at": _now_iso(),
    }


def _component_resolution_status(verification: dict[str, Any], resolved: dict[str, Any]) -> tuple[str, bool]:
    status = str(verification.get("status", "unresolved"))
    needs_reselection = bool(verification.get("reselect_required", False))
    if status == "verified":
        return "resolved", False
    if status == "provisional":
        return "partial", True
    if status == "selected":
        return "selected", True
    if status == "reselect_required":
        return "partial", True
    if bool(resolved.get("symbol")) or bool(resolved.get("footprint")):
        return "partial", needs_reselection or True
    return "unresolved", True


def _resolution_source(component: dict[str, Any], resolved: dict[str, Any]) -> str:
    selected = component.get("selected_part", {})
    if not isinstance(selected, dict):
        selected = {}
    if selected.get("kicad_footprint_hint"):
        return "selected_part_hint"
    if selected.get("lcsc_id"):
        return "selected_part"
    if str(resolved.get("symbol", "")).startswith("AIAgent:"):
        return "placeholder"
    return "role_template"


def build_project_resolution(
    model: dict[str, Any],
    *,
    parts_result: dict[str, Any] | None = None,
    generator_name: str = "hwtool",
    generator_version: str = "",
) -> dict[str, Any]:
    """Build a project-level resolution manifest from the circuit model."""
    components: list[dict[str, Any]] = []
    selected_count = 0
    resolved_count = 0
    verified_count = 0
    provisional_count = 0
    rejected_count = 0
    needs_reselection_count = 0
    placeholder_symbol_count = 0
    missing_footprint_count = 0
    unverified_count = 0
    search_queue: list[dict[str, Any]] = []
    resolver_requests: list[dict[str, Any]] = []
    project_id = str(model.get("project_id", ""))
    request_id = str(model.get("request_id", ""))
    part_pipeline_selected_by_ref: dict[str, dict[str, Any]] = {}
    resolver_results_by_key: dict[str, dict[str, Any]] = {}
    for item in (parts_result or {}).get("resolver_results", []) or []:
        payload = _to_plain_dict(item)
        key = str(payload.get("id", "")).strip()
        if key:
            resolver_results_by_key[key] = payload
    selection_results_by_key: dict[str, dict[str, Any]] = {}
    for item in (parts_result or {}).get("selection_results", []) or []:
        payload = _to_plain_dict(item)
        key = str(payload.get("requirement_id", "")).strip()
        if key:
            selection_results_by_key[key] = payload

    for item in (parts_result or {}).get("selections", []) or []:
        ref = _selection_ref(item)
        selected = _clean_part(item)
        if ref and selected:
            part_pipeline_selected_by_ref[ref] = selected

    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue

        selected_part = _clean_part(component.get("selected_part", {}))
        pipeline_selected = part_pipeline_selected_by_ref.get(str(component.get("ref", "")).strip(), {})
        if pipeline_selected:
            selected_part = {**selected_part, **pipeline_selected}
        candidate_parts = _normalise_candidates(component.get("candidate_parts", []))
        component_key = str(component.get("role", "")).strip() or str(component.get("ref", "")).strip()
        live_resolver_result = resolver_results_by_key.get(component_key, {})
        live_selection_result = selection_results_by_key.get(component_key, {})
        if live_resolver_result.get("candidates"):
            candidate_parts = _normalise_candidates(live_resolver_result.get("candidates", []))
        if selected_part:
            selected_count += 1

        search_plan = _build_search_plan(component, selected_part)
        symbol, footprint, notes = symbol_mapping_for({**component, "selected_part": selected_part})
        footprint_found = footprint_exists(footprint) if footprint else None
        if symbol.startswith("AIAgent:"):
            placeholder_symbol_count += 1
        if footprint and footprint_found is False:
            missing_footprint_count += 1

        verification = _build_verification_report(
            component,
            selected_part,
            candidate_parts,
            search_plan,
            symbol,
            footprint,
            footprint_found,
            parts_result=parts_result,
        )
        resolution_result = _build_resolution_result(
            component,
            selected_part,
            candidate_parts,
            symbol,
            footprint,
            footprint_found,
            parts_result=parts_result,
        )
        if live_resolver_result:
            resolution_result["backend"] = "parts_pipeline"
            resolution_result["candidates"] = candidate_parts
            resolution_result["query_context"] = live_resolver_result.get("query_context", resolution_result["query_context"])
        if live_selection_result.get("selected"):
            resolution_result["selected_candidate"] = _clean_part(live_selection_result.get("selected"))
        if live_selection_result.get("all_candidates"):
            resolution_result["candidates"] = _normalise_candidates(live_selection_result.get("all_candidates", []))
        search_queue.append(_build_search_queue_entry(component, resolution_result["search_plan"]))
        resolver_requests.append(
            _build_resolver_request(
                component,
                search_queue[-1],
                project_id=project_id,
                request_id=request_id,
            )
        )
        resolution_status, needs_reselection = _component_resolution_status(
            verification,
            {"symbol": symbol, "footprint": footprint},
        )
        if resolution_status == "resolved":
            resolved_count += 1
        elif resolution_status == "partial":
            provisional_count += 1
        else:
            rejected_count += 1
        if verification.get("status") == "verified":
            verified_count += 1
        if needs_reselection:
            needs_reselection_count += 1
        if verification.get("status") != "verified":
            unverified_count += 1

        components.append(
            {
                "ref": str(component.get("ref", "")),
                "role": str(component.get("role", "")),
                "value": str(component.get("value", "")),
                "selected_part": selected_part,
                "candidate_parts": candidate_parts,
                "search_plan": resolution_result["search_plan"],
                "resolution_result": resolution_result,
                "resolved": {
                    "symbol": symbol,
                    "footprint": footprint,
                    "footprint_exists": footprint_found,
                    "source": _resolution_source(component, {"symbol": symbol, "footprint": footprint}),
                    "notes": notes,
                },
                "verification": verification,
                "status": resolution_status,
                "needs_reselection": needs_reselection,
                "availability_status": str(component.get("availability_status", "unknown")),
                "notes": _as_string_list(component.get("notes", [])),
            }
        )

    parts_pipeline: dict[str, Any] = {
        "enabled": bool(parts_result),
        "lock_file": str((parts_result or {}).get("lock_file", "")),
        "risk_report_file": str((parts_result or {}).get("risk_report_file", "")),
        "summary": dict((parts_result or {}).get("summary", {})) if isinstance((parts_result or {}).get("summary", {}), dict) else {},
        "warnings": [str(item) for item in (parts_result or {}).get("warnings", []) if str(item)],
        "selection_count": len((parts_result or {}).get("selections", []) or []),
        "selected_parts": [_clean_part(item) for item in ((parts_result or {}).get("selections", []) or [])],
        "resolver_requests": [_to_plain_dict(item) for item in ((parts_result or {}).get("resolver_requests", []) or [])],
        "requirements": [_to_plain_dict(item) if isinstance(item, dict) else _clean_part(item) for item in ((parts_result or {}).get("requirements", []) or [])],
        "resolver_results": [_to_plain_dict(item) for item in ((parts_result or {}).get("resolver_results", []) or [])],
        "selection_results": [_to_plain_dict(item) for item in ((parts_result or {}).get("selection_results", []) or [])],
        "import_result": (parts_result or {}).get("import_result", {}),
    }

    return {
        "schema_version": PROJECT_RESOLUTION_SCHEMA_VERSION,
        "project_id": str(model.get("project_id", "")),
        "request_id": str(model.get("request_id", "")),
        "topology": str(model.get("topology", "")),
        "dsl_schema_version": str(model.get("schema_version", "")),
        "generated_at": _now_iso(),
        "generator": {
            "name": generator_name,
            "version": generator_version,
        },
        "generation_mode": "pipeline" if parts_result else "dsl_only",
        "summary": {
            "component_count": len(components),
            "search_queue_count": len(search_queue),
            "resolver_request_count": len(resolver_requests),
            "selected_count": selected_count,
            "resolved_count": resolved_count,
            "verified_count": verified_count,
            "provisional_count": provisional_count,
            "rejected_count": rejected_count,
            "needs_reselection_count": needs_reselection_count,
            "placeholder_symbol_count": placeholder_symbol_count,
            "missing_footprint_count": missing_footprint_count,
            "unverified_count": unverified_count,
        },
        "parts_pipeline": parts_pipeline,
        "search_queue": search_queue,
        "resolver_requests": resolver_requests,
        "components": components,
        "warnings": [],
        "errors": [],
    }


def write_project_resolution(
    model: dict[str, Any],
    output_dir: str | Path,
    *,
    parts_result: dict[str, Any] | None = None,
    generator_name: str = "hwtool",
    generator_version: str = "",
) -> dict[str, Any]:
    """Write project-resolution.json and return the manifest plus file path."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    manifest = build_project_resolution(
        model,
        parts_result=parts_result,
        generator_name=generator_name,
        generator_version=generator_version,
    )
    path = output_path / "project-resolution.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "manifest": manifest,
    }
