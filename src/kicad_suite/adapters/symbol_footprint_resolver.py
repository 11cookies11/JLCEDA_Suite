"""Symbol / Footprint Resolver: map part/role/package ->KiCad symbol + footprint.

Extracted from ``compile_kicad_execution_plan.py``.  Pure resolution logic lives here;
KiCad-specific filesystem probes are behind a pluggable adapter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..shared.env_utils import env
from ..shared.env_utils import repo_root
from ..shared.test_point_compat import (
    is_test_point_role,
    resolve_test_point_footprint,
    resolve_test_point_symbol_ref,
)

REPO_ROOT = repo_root()

# ---------------------------------------------------------------------------
# Internal globals (lazy-loaded caches)
# ---------------------------------------------------------------------------

_symbol_map_cache: dict[str, Any] | None = None
_footprint_exists_cache: dict[str, bool] = {}


class SymbolResolutionError(ValueError):
    """Raised when a component cannot be mapped to an explicit KiCad symbol."""


def _sanitize_symbol_name(name: str) -> str:
    """Return a KiCad-safe symbol name."""
    cleaned = name.replace(" ", "_").replace(":", "_").replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", cleaned)
    return cleaned.strip("._-") or "UNKNOWN"


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Symbol map loading
# ---------------------------------------------------------------------------


def load_symbol_map() -> dict[str, Any]:
    """Return an empty compatibility config.

    The shared rule table has been retired. Resolution now requires explicit
    selected_part symbol data or a matching imported project-local JLC symbol.
    """
    return {}


def reload_symbol_map() -> dict[str, Any]:
    """Force-reload the symbol map (useful after config changes)."""
    return {}


# ---------------------------------------------------------------------------
# Footprint roots (filesystem probe)
# ---------------------------------------------------------------------------


def kicad_footprint_roots() -> list[Path]:
    """Return candidate directories containing KiCad ``.pretty`` footprint libraries."""
    roots: list[Path] = []

    explicit = env("KICAD_FOOTPRINT_DIR", "")
    if explicit:
        roots.append(Path(explicit))
    extra = env("KICAD_EXTRA_FOOTPRINT_DIR", "")
    if extra:
        roots.append(Path(extra))

    source = env("KICAD_SOURCE_PROJECT_DIR", "")
    if source:
        source_root = Path(source)
        candidates = [
            source_root / "libraries" / "footprints",
            source_root / "output" / "libs",
        ]
        for c in candidates:
            if c.exists():
                roots.append(c)

    output = env("KICAD_OUTPUT_DIR", "")
    if output:
        out = Path(output)
        for sub in (out / "libs", out.parent / "libs"):
            if sub.exists():
                roots.append(sub)

    bundled = REPO_ROOT / "resources" / "kicad" / "footprints"
    if bundled.exists():
        roots.append(bundled)

    for base in ("D:/Program Files/KiCad", "C:/Program Files/KiCad"):
        base_path = Path(base)
        if base_path.exists():
            for version_dir in sorted(base_path.iterdir(), reverse=True):
                fp_dir = version_dir / "share" / "kicad" / "footprints"
                if fp_dir.exists():
                    roots.append(fp_dir)
    return roots


def footprint_exists(footprint: str) -> bool | None:
    """Return True/False if a KiCad footprint exists on disk, None if uncheckable."""
    if not footprint or ":" not in footprint:
        return None
    cached = _footprint_exists_cache.get(footprint)
    if cached is not None:
        return cached

    lib_name, fp_name = footprint.split(":", 1)
    for root in kicad_footprint_roots():
        candidate = root / f"{lib_name}.pretty" / f"{fp_name}.kicad_mod"
        if candidate.exists():
            _footprint_exists_cache[footprint] = True
            return True
    _footprint_exists_cache[footprint] = False
    return False


def clear_footprint_cache() -> None:
    """Clear the footprint-exists cache."""
    global _footprint_exists_cache
    _footprint_exists_cache = {}


# ---------------------------------------------------------------------------
# Symbol resolution
# ---------------------------------------------------------------------------


def symbol_mapping_for(component: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Resolve (lib_id, footprint, notes) for a component dict.

    The component dict should have: ``ref``, ``role``, ``value``, and optionally
    ``selected_part.package``.
    """
    ref = str(component.get("ref", ""))
    role = str(component.get("role", ""))
    value = str(component.get("value", ""))
    selected = component.get("selected_part", {})
    if not isinstance(selected, dict):
        selected = {}
    package = str(
        selected.get("kicad_footprint_hint")
        or selected.get("package", "")
        or selected.get("mechanical_package", "")
    )

    lib_id = ""
    footprint = ""
    notes: list[str] = []

    symbol_id = _selected_part_symbol_id(selected)
    if is_test_point_role(role):
        symbol_id = resolve_test_point_symbol_ref(component, selected) or symbol_id
    if symbol_id:
        lib_id = _normalize_symbol_lib_id(symbol_id)
        notes.append("Resolved from selected_part; shared symbol rule table is retired.")
        footprint_hint = str(selected.get("kicad_footprint_hint", "")).strip()
        if is_test_point_role(role):
            footprint_hint = resolve_test_point_footprint(component, selected) or footprint_hint
        if not footprint_hint:
            footprint_hint = resolve_test_point_footprint(component, selected)
        return lib_id, resolve_footprint(package, footprint_hint), notes

    imported_symbol_name = _imported_jlc_symbol_name(component, selected)
    if imported_symbol_name:
        lib_id = f"JLC-MCP:{imported_symbol_name}"
        notes.append("Resolved from imported project-local JLC symbol library.")
        footprint_hint = str(selected.get("kicad_footprint_hint", "")).strip()
        if is_test_point_role(role):
            footprint_hint = resolve_test_point_footprint(component, selected) or footprint_hint
        if not footprint_hint:
            footprint_hint = resolve_test_point_footprint(component, selected)
        return lib_id, resolve_footprint(package, footprint_hint), notes

    raise SymbolResolutionError(
        f'No explicit KiCad symbol found for component {ref or "<unknown>"} '
        f'(role={role or "<empty>"}, value={value or "<empty>"}). '
        'Run resolve-symbols or set selected_part.symbol_ref / selected_part.display_name to an imported symbol.'
    )


def _selected_part_symbol_id(selected: dict[str, Any]) -> str:
    """Derive a stable EasyEDA/JLC symbol id from selected_part."""
    for key in ("symbol_ref", "symbol_name", "kicad_symbol"):
        value = str(selected.get(key, "")).strip()
        if value:
            return value
    return ""


def _normalize_symbol_lib_id(symbol_id: str) -> str:
    if not symbol_id:
        return ""
    if ":" in symbol_id and not symbol_id.startswith(("http:", "https:")):
        return symbol_id
    return f"JLC-MCP:{_sanitize_symbol_name(symbol_id)}"


def _imported_jlc_symbol_name(component: dict[str, Any], selected: dict[str, Any]) -> str:
    """Find a matching symbol already imported into the project-local JLC library."""
    candidates: list[str] = []
    for key in ("display_name", "mpn", "part_id", "lcsc_id"):
        value = str(selected.get(key, "")).strip()
        if value:
            candidates.append(value)
    value = str(component.get("value", "")).strip()
    if value:
        candidates.append(value)

    seen: set[str] = set()
    for candidate in candidates:
        symbol_name = _sanitize_symbol_name(candidate)
        if not symbol_name or symbol_name in seen:
            continue
        seen.add(symbol_name)
        imported_name = _find_imported_jlc_symbol_by_normalized_name(symbol_name)
        if imported_name:
            return imported_name
    return ""


def _find_imported_jlc_symbol_by_normalized_name(normalized_name: str) -> str:
    from .kicad_symbol_library import kicad_symbol_roots

    for root in kicad_symbol_roots():
        for symbol_file in sorted(root.glob("JLC-MCP*.kicad_sym")):
            if not symbol_file.is_file():
                continue
            text = symbol_file.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'^\s*\(symbol\s+"([^"]+)"', text, re.MULTILINE):
                imported_name = match.group(1)
                if _sanitize_symbol_name(imported_name) == normalized_name:
                    return imported_name
    return ""


# ---------------------------------------------------------------------------
# Footprint resolution
# ---------------------------------------------------------------------------


def _has_library_prefix(value: str) -> bool:
    return ":" in value and not value.startswith(("http:", "https:"))


def _remap_jlc_footprint(fp: str) -> str:
    """Map JLC-MCP footprint names to KiCad system library paths."""
    table: dict[str, str] = {
        "R0201": "Resistor_SMD:R_0201_0603Metric",
        "R0402": "Resistor_SMD:R_0402_1005Metric",
        "R0603": "Resistor_SMD:R_0603_1608Metric",
        "R0805": "Resistor_SMD:R_0805_2012Metric",
        "R1206": "Resistor_SMD:R_1206_3216Metric",
        "C0201": "Capacitor_SMD:C_0201_0603Metric",
        "C0402": "Capacitor_SMD:C_0402_1005Metric",
        "C0603": "Capacitor_SMD:C_0603_1608Metric",
        "C0805": "Capacitor_SMD:C_0805_2012Metric",
        "C1206": "Capacitor_SMD:C_1206_3216Metric",
        "L0402": "Inductor_SMD:L_0402_1005Metric",
        "L0603": "Inductor_SMD:L_0603_1608Metric",
        "L0805": "Inductor_SMD:L_0805_2012Metric",
        "LED0603": "LED_SMD:LED_0603_1608Metric",
        "LED0805": "LED_SMD:LED_0805_2012Metric",
        "SOD-123": "Diode_SMD:D_SOD-123",
        "SOD-323": "Diode_SMD:D_SOD-323",
        "SOT-23": "Package_TO_SOT_SMD:SOT-23",
        "SOT-23-3": "Package_TO_SOT_SMD:SOT-23",
        "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
        "SOT-23-6": "Package_TO_SOT_SMD:SOT-23-6",
        "SOT-89-3": "Package_TO_SOT_SMD:SOT-89-3",
        "SOT-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin3",
        "SOT-223-3": "Package_TO_SOT_SMD:SOT-223-3_TabPin3",
        "SOIC-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "SOP-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "TSSOP-20": "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
        "QFN-20": "Package_DFN_QFN:QFN-20-1EP_3x3mm_P0.4mm_EP1.65x1.65mm",
        "QFN-24": "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
        "QFN-32": "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm",
        "QFN-48": "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",
        "LQFP-48": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
        "QFP-48": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
        "LQFP-64": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
        "QFP-64": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
        "LQFP-100": "Package_QFP:LQFP-100_14x14mm_P0.5mm",
        "QFP-100": "Package_QFP:LQFP-100_14x14mm_P0.5mm",
    }
    for jlc, kicad in table.items():
        if jlc in fp:
            return kicad
    return fp


def _normalize_footprint(footprint: str) -> str:
    """Return library-qualified footprints unchanged; otherwise use JLC-MCP naming."""
    if ":" in footprint:
        return footprint
    return f"JLC-MCP:{footprint}"


def normalize_footprint(footprint: str) -> str:
    """Public wrapper for normalizing footprint names."""
    return _normalize_footprint(footprint)


def resolve_footprint(component_package: str, mapping_footprint: str) -> str:
    """Choose the best KiCad footprint for a component.

    Priority:
    1. mapping_footprint if it has ``Library:Name`` format
    2. component_package if it has ``Library:Name`` format
    3. mapping_footprint raw
    4. component_package raw
    """
    if mapping_footprint and _has_library_prefix(mapping_footprint):
        return mapping_footprint
    if component_package and _has_library_prefix(component_package):
        return component_package
    if mapping_footprint:
        return _normalize_footprint(mapping_footprint)
    if component_package:
        return _normalize_footprint(component_package)
    return ""


# ---------------------------------------------------------------------------
# Symbol library validation
# ---------------------------------------------------------------------------


def validate_symbol_libraries(
    preflight: list[tuple[str, str, str, str, list[str]]],
) -> list[str]:
    """Check that JLC-MCP symbol libraries exist on disk.

    Returns a list of missing-library error messages (empty if all good).
    """
    from ..compile_kicad_execution_plan import _validate_symbol_libraries as _impl
    try:
        _impl(preflight)
        return []
    except SystemExit:
        pass
    except Exception as exc:
        return [str(exc)]
    return []


# ---------------------------------------------------------------------------
# Symbol size estimation
# ---------------------------------------------------------------------------


def estimate_symbol_size(lib_id: str) -> tuple[float, float]:
    """Estimate (width_mm, height_mm) for a KiCad symbol.

    Uses symbol geometry on disk. The retired rule table no longer provides
    manual size overrides.
    """
    from ..compile_kicad_execution_plan import _estimate_symbol_size_from_pins
    result = _estimate_symbol_size_from_pins(lib_id)
    if result is not None:
        return result
    return 12.7, 10.16
