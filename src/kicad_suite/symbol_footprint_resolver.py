"""Symbol / Footprint Resolver: map part/role/package → KiCad symbol + footprint.

Extracted from ``compile_kicad_execution_plan.py``.  Pure resolution logic lives here;
KiCad-specific filesystem probes are behind a pluggable adapter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .env_utils import env

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Internal globals (lazy-loaded caches)
# ---------------------------------------------------------------------------

_symbol_map_cache: dict[str, Any] | None = None
_footprint_exists_cache: dict[str, bool] = {}


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Symbol map loading
# ---------------------------------------------------------------------------


def load_symbol_map() -> dict[str, Any]:
    """Load kicad-symbol-map.json (cached)."""
    global _symbol_map_cache
    if _symbol_map_cache is not None:
        return _symbol_map_cache
    path = env("KICAD_SYMBOL_MAP_FILE", "")
    path_obj = Path(path) if path else REPO_ROOT / "config" / "kicad-symbol-map.json"
    _symbol_map_cache = _load_json_file(path_obj)
    return _symbol_map_cache


def reload_symbol_map() -> dict[str, Any]:
    """Force-reload the symbol map (useful after config changes)."""
    global _symbol_map_cache
    _symbol_map_cache = None
    return load_symbol_map()


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


def _mapping_matches(match: dict[str, Any], ref: str, role: str, value: str) -> bool:
    """Check whether a match block applies to a component."""
    if "ref" in match and str(match["ref"]) != ref:
        return False
    if "ref_prefix" in match and not str(ref).startswith(str(match["ref_prefix"])):
        return False
    if "role_contains" in match:
        items = match["role_contains"]
        items_list = items if isinstance(items, list) else [items]
        if not any(str(item) in role for item in items_list):
            return False
    if "value_contains" in match:
        items = match["value_contains"]
        items_list = items if isinstance(items, list) else [items]
        if not any(str(item) in value for item in items_list):
            return False
    return True


def symbol_mapping_for(component: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Resolve (lib_id, footprint, notes) for a component dict.

    The component dict should have: ``ref``, ``role``, ``value``, and optionally
    ``selected_part.package``.
    """
    symbol_map = load_symbol_map()
    mappings = symbol_map.get("mappings", [])
    ref = str(component.get("ref", ""))
    role = str(component.get("role", ""))
    value = str(component.get("value", ""))

    lib_id = ""
    footprint = ""
    notes: list[str] = []

    for entry in mappings:
        if not isinstance(entry, dict):
            continue
        match = entry.get("match", {})
        if isinstance(match, dict) and _mapping_matches(match, ref, role, value):
            lib_id = str(entry.get("lib_id", ""))
            footprint = str(entry.get("footprint", ""))
            note = str(entry.get("note", ""))
            if note:
                notes.append(note)
            break

    sp = component.get("selected_part", {})
    package = str(sp.get("package", sp.get("mechanical_package", ""))) if isinstance(sp, dict) else ""

    if not lib_id:
        fallback = symbol_map.get("fallback", {})
        if isinstance(fallback, dict):
            lib_id = str(fallback.get("lib_id", ""))
            footprint = str(fallback.get("footprint", ""))
            note = str(fallback.get("note", ""))
            if note:
                notes.append(note)

    if not lib_id:
        lib_id = "AIAgent:Generic_2Pin"
        if package:
            footprint = _normalize_footprint(package)
    else:
        footprint = resolve_footprint(package, footprint)

    return lib_id, footprint, notes


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
    }
    for jlc, kicad in table.items():
        if jlc in fp:
            return kicad
    return fp


def _normalize_footprint(footprint: str) -> str:
    """Apply footprint aliases and JLC-MCP remapping."""
    symbol_map = load_symbol_map()
    aliases = symbol_map.get("footprint_aliases", {})
    if isinstance(aliases, dict) and footprint in aliases:
        footprint = str(aliases[footprint])
    if footprint.startswith("JLC-MCP:"):
        return footprint
    return _remap_jlc_footprint(footprint)


def resolve_footprint(component_package: str, mapping_footprint: str) -> str:
    """Choose the best KiCad footprint for a component.

    Priority:
    1. mapping_footprint if it has ``Library:Name`` format
    2. component_package if it has ``Library:Name`` format
    3. mapping_footprint raw
    4. component_package raw
    """
    if mapping_footprint and _has_library_prefix(mapping_footprint):
        return _normalize_footprint(mapping_footprint)
    if component_package and _has_library_prefix(component_package):
        return _normalize_footprint(component_package)
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
    from .compile_kicad_execution_plan import _validate_symbol_libraries as _impl
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

    Checks the symbol map's ``symbol_sizes`` config first, then falls back to
    parsing the ``.kicad_sym`` file on disk.
    """
    symbol_map = load_symbol_map()
    sizes = symbol_map.get("symbol_sizes", {})
    if isinstance(sizes, dict) and lib_id in sizes:
        entry = sizes[lib_id]
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            return float(entry[0]), float(entry[1])
    from .compile_kicad_execution_plan import _estimate_symbol_size_from_pins, _legacy_estimate_symbol_size
    result = _estimate_symbol_size_from_pins(lib_id)
    if result is not None:
        return result
    return _legacy_estimate_symbol_size(lib_id)
