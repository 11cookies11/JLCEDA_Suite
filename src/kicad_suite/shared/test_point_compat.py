from __future__ import annotations

from typing import Any


DEFAULT_TEST_POINT_DISPLAY_NAME = "1-pad test point"
DEFAULT_TEST_POINT_PACKAGE = "1-pin SMD test point"
DEFAULT_TEST_POINT_MECHANICAL_PACKAGE = "1-pin SMD test point"
DEFAULT_TEST_POINT_SYMBOL_REF = "TestPoint:TestPoint_Pad_D1.5mm"
DEFAULT_TEST_POINT_FOOTPRINT = "TestPoint:TestPoint_Pad_D1.5mm"

_PLACEHOLDER_SYMBOL_NAMES = {
    "TP",
    "TP_1P",
    "TESTPOINT",
    "TEST_POINT",
    "TEST-POINT",
}

_PLACEHOLDER_FOOTPRINT_NAMES = {
    "TP-SMD",
    "TP-SMD_1P",
    "TP_SMD",
    "JLC-MCP:TP-SMD",
    "JLC-MCP:TP-SMD_1P",
}


def is_test_point_role(role: str) -> bool:
    return "test_point" in role.strip().lower()


def normalize_test_point_selected_part(component: dict[str, Any], selected_part: dict[str, Any]) -> dict[str, Any]:
    """Return a compatibility-normalised selected_part for test points.

    The raw model can keep project-local placeholder values such as ``TP_1P``
    and ``TP-SMD_1P``.  Downstream EDA bridges use this helper to expose a
    standard KiCad-friendly test-point identity when the role says the part is
    a test point.
    """
    if not isinstance(selected_part, dict):
        selected_part = {}

    role = str(component.get("role", ""))
    if not is_test_point_role(role):
        return dict(selected_part)

    normalised = dict(selected_part)
    display_name = str(normalised.get("display_name", "")).strip()
    if not display_name or _looks_placeholder(display_name):
        normalised["display_name"] = DEFAULT_TEST_POINT_DISPLAY_NAME

    package = str(normalised.get("package", "")).strip()
    if not package or _looks_placeholder(package):
        normalised["package"] = DEFAULT_TEST_POINT_PACKAGE

    mechanical_package = str(normalised.get("mechanical_package", "")).strip()
    if not mechanical_package or _looks_placeholder(mechanical_package):
        normalised["mechanical_package"] = DEFAULT_TEST_POINT_MECHANICAL_PACKAGE

    symbol_ref = resolve_test_point_symbol_ref(component, normalised)
    if symbol_ref:
        normalised["symbol_ref"] = symbol_ref

    footprint = resolve_test_point_footprint(component, normalised)
    if footprint:
        normalised["kicad_footprint_hint"] = footprint

    return normalised


def resolve_test_point_symbol_ref(component: dict[str, Any], selected_part: dict[str, Any]) -> str:
    role = str(component.get("role", ""))
    if not is_test_point_role(role):
        return ""

    raw = _selected_identity(selected_part)
    if not raw:
        return DEFAULT_TEST_POINT_SYMBOL_REF
    if _has_library_prefix(raw):
        return raw
    if _looks_placeholder(raw):
        return DEFAULT_TEST_POINT_SYMBOL_REF
    return raw


def resolve_test_point_footprint(component: dict[str, Any], selected_part: dict[str, Any]) -> str:
    role = str(component.get("role", ""))
    if not is_test_point_role(role):
        return ""

    raw = str(selected_part.get("kicad_footprint_hint", "")).strip()
    if not raw:
        raw = str(selected_part.get("package", "")).strip()
    if not raw:
        return DEFAULT_TEST_POINT_FOOTPRINT
    if _has_library_prefix(raw):
        return raw
    if _looks_placeholder(raw):
        return DEFAULT_TEST_POINT_FOOTPRINT
    return raw


def _selected_identity(selected_part: dict[str, Any]) -> str:
    for key in ("symbol_ref", "symbol_name", "kicad_symbol"):
        value = str(selected_part.get(key, "")).strip()
        if value:
            return value
    return ""


def _has_library_prefix(value: str) -> bool:
    return ":" in value and not value.startswith(("http:", "https:"))


def _looks_placeholder(value: str) -> bool:
    token = _normalise_token(value)
    if not token:
        return True
    return token in _PLACEHOLDER_SYMBOL_NAMES or token in _PLACEHOLDER_FOOTPRINT_NAMES or token.startswith("TP")


def _normalise_token(value: str) -> str:
    token = value.strip().upper().replace(" ", "_").replace("-", "_").replace("/", "_").replace(":", "_")
    token = "".join(ch for ch in token if ch.isalnum() or ch == "_")
    return token.strip("_")
