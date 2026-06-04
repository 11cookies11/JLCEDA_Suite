"""Symbol / Footprint Resolver: map part/role/package → KiCad symbol + footprint.

Extracted from ``compile_kicad_execution_plan.py``.  Pure resolution logic lives here;
KiCad-specific filesystem probes are behind a pluggable adapter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .env_utils import env

from .env_utils import repo_root

REPO_ROOT = repo_root()

# ---------------------------------------------------------------------------
# Internal globals (lazy-loaded caches)
# ---------------------------------------------------------------------------

_symbol_map_cache: dict[str, Any] | None = None
_footprint_exists_cache: dict[str, bool] = {}

# Minimal role → (KiCad_lib:symbol, footprint_hint) safety net.
# These are only used when ``resolve-symbols`` was skipped and no
# ``selected_part`` is present.  Generic EasyEDA search handles
# everything else — see ``_ROLE_GENERIC_SEARCH`` in jlc_installer.py.
_ROLE_FALLBACK: dict[str, tuple[str, str]] = {
    # Passives – Device library symbols are reliable and universal
    "boot0_pulldown": ("Device:R", "R0603"),
    "nrst_pullup": ("Device:R", "R0603"),
    "led_resistor": ("Device:R", "R0603"),
    "user_button_pullup": ("Device:R", "R0603"),
    "i2c_pullup": ("Device:R", "R0603"),
    "xtal_load_cap_1": ("Device:C", "C0603"),
    "xtal_load_cap_2": ("Device:C", "C0603"),
    "hse_load_cap_1": ("Device:C", "C0603"),
    "hse_load_cap_2": ("Device:C", "C0603"),
    "lse_load_cap_1": ("Device:C", "C0603"),
    "lse_load_cap_2": ("Device:C", "C0603"),
    "vdd_decoupling_1": ("Device:C", "C0603"),
    "vdd_decoupling_2": ("Device:C", "C0603"),
    "vdd_decoupling_3": ("Device:C", "C0603"),
    "vdd_decoupling_4": ("Device:C", "C0603"),
    "vdd_bulk_cap": ("Device:C", "C0805"),
    "reg_input_cap": ("Device:C", "C0805"),
    "reg_output_cap": ("Device:C", "C0805"),
    "main_8mhz_xtal": ("Device:Crystal", ""),
    "rtc_32k_xtal": ("Device:Crystal", ""),
    "main_12mhz_xtal": ("Device:Crystal", ""),
    # NexDAP bring-up board roles
    "usb_vbus_ptc_fuse": ("Device:Fuse", "F1206"),
    "usb_vbus_tvs_diode": ("Device:D_TVS", "SMF5.0A"),
    "main_regulator_input_capacitor": ("Device:C", "C0603"),
    "main_regulator_output_capacitor": ("Device:C", "C0603"),
    "main_3v3_bulk_capacitor": ("Device:C", "C0603"),
    "esp_chip_en_pullup": ("Device:R", "R0603"),
    "esp_en_reset_capacitor": ("Device:C", "C0603"),
    "esp_gpio9_boot_pullup": ("Device:R", "R0603"),
    "esp_gpio8_strap_pullup": ("Device:R", "R0603"),
    "esp_vdd3p3_decoupling_1": ("Device:C", "C0603"),
    "esp_vdd3p3_decoupling_2": ("Device:C", "C0603"),
    "esp_vdd3p3_bulk": ("Device:C", "C0603"),
    "rp2040_run_pullup": ("Device:R", "R0603"),
    "rp2040_vreg_in_bypass": ("Device:C", "C0603"),
    "rp2040_vreg_out_bulk": ("Device:C", "C0603"),
    "rp2040_iovdd_decoupling": ("Device:C", "C0603"),
    "rp2040_dvdd_decoupling": ("Device:C", "C0603"),
    "rp2040_3v3_bulk": ("Device:C", "C0603"),
    "rp_xtal_load_cap_1": ("Device:C", "C0603"),
    "rp_xtal_load_cap_2": ("Device:C", "C0603"),
    "bridge_flash_decoupling": ("Device:C", "C0603"),
    "rp2040_bootsel_gate_resistor": ("Device:R", "R0603"),
    "rp2040_bootsel_gate_pulldown": ("Device:R", "R0603"),
    "swdio_series_resistor": ("Device:R", "R0603"),
    "swclk_series_resistor": ("Device:R", "R0603"),
    "swo_series_resistor": ("Device:R", "R0603"),
    "nreset_series_resistor": ("Device:R", "R0603"),
    "target_uart_tx_series_resistor": ("Device:R", "R0603"),
    "target_uart_rx_series_resistor": ("Device:R", "R0603"),
    "target_nreset_pullup": ("Device:R", "R0603"),
    "vtref_adc_divider_top": ("Device:R", "R0603"),
    "vtref_adc_divider_bottom": ("Device:R", "R0603"),
    "vtref_adc_filter_cap": ("Device:C", "C0603"),
    "power_led_resistor": ("Device:R", "R0603"),
    "dap_led_resistor": ("Device:R", "R0603"),
    "target_swd_connector": ("Connector_Generic:Conn_02x05_Odd_Even", "HDR-TH_10P-P2.54-V-M-2X5"),
    "rp2040_bootsel_open_drain_pulldown": ("Transistor_FET:2N7002", "SOT-23-3"),
    "nreset_open_drain_nmos": ("Transistor_FET:2N7002", "SOT-23-3"),
    "target_esd_protection": ("Device:D_TVS", "SOT-23-6"),
    "power_indicator_led": ("Device:LED", "LED0603-RD"),
    "dap_activity_led": ("Device:LED", "LED0603-RD"),
    "test_point_swdio": ("Connector:TestPoint", "TP-SMD_1P"),
    "test_point_swclk": ("Connector:TestPoint", "TP-SMD_1P"),
    # LEDs – Device:LED works for any basic indicator
    "power_led": ("Device:LED", ""),
    "status_led": ("Device:LED", ""),
    "user_led": ("Device:LED", ""),
}


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

    The shared rule table has been retired. Resolution now uses selected_part
    plus built-in role templates.
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

    symbol_name = _selected_part_symbol_name(selected)
    if symbol_name:
        lib_id = f"JLC-MCP:{symbol_name}"
        notes.append("Resolved from selected_part; shared symbol rule table is retired.")
        return lib_id, resolve_footprint(package, str(selected.get("kicad_footprint_hint", ""))), notes

    role_fallback = _ROLE_FALLBACK.get(role)
    if role_fallback:
        lib_sym, fp = role_fallback
        notes.append(f'Role "{role}" resolved to KiCad built-in {lib_sym} (selected_part missing or incomplete).')
        return lib_sym, resolve_footprint(package, fp), notes

    notes.append(f'Mapped unknown role "{role}" to local AIAgent:Generic_2Pin placeholder symbol.')
    return 'AIAgent:Generic_2Pin', _normalize_footprint(package), notes


def _selected_part_symbol_name(selected: dict[str, Any]) -> str:
    """Derive a stable EasyEDA/JLC symbol name from selected_part."""
    for key in ("symbol_ref", "symbol_name", "kicad_symbol"):
        value = str(selected.get(key, "")).strip()
        if value:
            return _sanitize_symbol_name(value)
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

    Uses symbol geometry on disk. The retired rule table no longer provides
    manual size overrides.
    """
    from .compile_kicad_execution_plan import _estimate_symbol_size_from_pins, _legacy_estimate_symbol_size
    result = _estimate_symbol_size_from_pins(lib_id)
    if result is not None:
        return result
    return _legacy_estimate_symbol_size(lib_id)
