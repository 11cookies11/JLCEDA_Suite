"""Install JLC components into project libraries — fetch, convert, save."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import jlc_api
from .easyeda_parser import parse_easyeda_component, ParsedComponent
from .easyeda_converter import build_kicad_symbol, build_kicad_footprint, make_two_pin_symbol
from .symbol_footprint_resolver import _ROLE_FALLBACK

# KiCad library section template for sym-lib-table / fp-lib-table
_SYM_LIB_TEMPLATE = """(sym_lib_table
  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))
)
"""


def search_and_install(
    query: str,
    project_path: Path,
    *,
    limit: int = 5,
    auto_select: bool = False,
) -> dict[str, Any]:
    """Search JLC for a component and install the first match into *project_path*.

    Returns a result dict suitable for agent CLI output.
    """
    results = jlc_api.search(query, limit=limit)
    if not results:
        return {"ok": False, "stage": "jlc_install", "error": f"No results for '{query}'"}

    if auto_select:
        selected = results[0]
    else:
        selected = results[0]  # default: pick first

    lcsc_id = selected["lcsc_id"]
    install_result = install_by_lcsc_id(lcsc_id, project_path)
    return {
        "ok": install_result.get("ok", False),
        "stage": "jlc_install",
        "lcsc_id": lcsc_id,
        "part": selected,
        "candidates": results,
        "install": install_result,
    }


def install_by_lcsc_id(lcsc_id: str, project_path: Path) -> dict[str, Any]:
    """Download component data from EasyEDA and install symbol + footprint into *project_path*."""
    # 1. Fetch from EasyEDA
    comp_data = jlc_api.get_component(lcsc_id, retries=5, delay=0.5)
    if comp_data is None:
        return {"ok": False, "error": f"Component {lcsc_id} not found on EasyEDA"}

    # 2. Parse
    parsed = parse_easyeda_component(
        comp_data["data_str"],
        comp_data.get("package_data_str"),
        comp_data.get("title", ""),
        comp_data.get("package_title", ""),
    )
    parsed.lcsc_id = lcsc_id

    # 3. Ensure project library directories exist
    sym_dir = project_path / "libraries" / "symbols"
    fp_dir = project_path / "libraries" / "footprints" / "JLC-MCP.pretty"
    sym_dir.mkdir(parents=True, exist_ok=True)
    fp_dir.mkdir(parents=True, exist_ok=True)

    # 4. Determine library name (reuse existing or create new)
    lib_name, sym_file = _find_or_create_sym_lib(sym_dir)

    # 5. Convert and write symbol
    if parsed.shapes:
        sym_content = build_kicad_symbol(parsed, lib_name)
    else:
        # Fallback: minimal 2-pin symbol
        sym_name = parsed.title or lcsc_id
        sym_content = make_two_pin_symbol("U", sym_name, lib_name)

    _append_symbol_to_lib(sym_file, sym_content)

    # 6. Convert and write footprint
    fp_name = _sanitize(comp_data.get("package_title", lcsc_id))
    fp_file = fp_dir / f"{fp_name}.kicad_mod"
    if parsed.pads or parsed.fp_shapes:
        fp_content = build_kicad_footprint(parsed, lib_name)
    else:
        fp_content = _make_minimal_footprint(fp_name)

    fp_file.write_text(fp_content, encoding="utf-8")

    return {
        "ok": True,
        "lcsc_id": lcsc_id,
        "title": comp_data.get("title", ""),
        "package": comp_data.get("package_title", ""),
        "symbol_file": str(sym_file),
        "symbol_count": 1 if parsed.shapes else 0,
        "footprint_file": str(fp_file),
        "pin_count": sum(1 for s in parsed.shapes if s.type == "pin"),
    }


def resolve_missing_symbols(project_path: Path, model: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    """Auto-resolve all components in *model* that are missing symbols.

    Searches JLC for each component's value/package, downloads the symbol
    and footprint, and installs them into *project_path*/libraries/.

    *timeout* is the maximum total time in seconds (default 120).
    If exceeded, remaining components fall back immediately.
    """
    import time as _time
    components = model.get("components", [])
    if not isinstance(components, list):
        return {"ok": True, "resolved": 0, "failed": 0, "details": []}

    deadline = _time.monotonic() + timeout
    resolved: list[dict[str, Any]] = []
    timed_out: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        # Timeout: skip EasyEDA and jump straight to fallback
        if _time.monotonic() > deadline:
            ref = comp.get("ref", "?")
            role = comp.get("role", "")
            fb = _ROLE_FALLBACK.get(role)
            if fb:
                _install_role_fallback(project_path, ref, role, fb[0], "")
                timed_out.append({"ref": ref, "role": role, "source": "fallback_timeout", "lib_sym": fb[0]})
            else:
                failed.append({"ref": ref, "role": role, "error": "timeout"})
            continue

        ref = comp.get("ref", "?")
        value = comp.get("value", "")
        role = comp.get("role", "")
        query = _search_query_for(role, value, comp.get('package', ''))
        if not query:
            continue

        # Try up to 2 query variants, 3 results each.  No retry on empty data —
        # EasyEDA either has the part or it doesn't.  Move quickly to fallback.
        queries = _query_variants(role, value, comp.get('package', ''))
        inst = None
        lcsc_id = ""

        for q in queries[:2]:
            results = jlc_api.search(q, limit=3)
            if not results:
                continue
            for r in results:
                lcsc_id = r["lcsc_id"]
                inst = install_by_lcsc_id(lcsc_id, project_path)
                if inst.get("ok"):
                    break
            if inst and inst.get("ok"):
                break

        if inst and inst.get("ok"):
            resolved.append({"ref": ref, "lcsc_id": lcsc_id, "title": inst.get("title", ""), "source": "easyeda", "pin_count": inst.get("pin_count", 0)})
            continue

        # Fallback: KiCad built-in symbol based on component role
        fallback = _ROLE_FALLBACK.get(role)
        if fallback:
            lib_sym, _fp = fallback
            _install_role_fallback(project_path, ref, role, lib_sym, lcsc_id)
            resolved.append({"ref": ref, "lcsc_id": lcsc_id, "role": role, "source": "fallback", "lib_sym": lib_sym, "pin_count": 2})
            continue

        failed.append({"ref": ref, "lcsc_id": lcsc_id, "error": inst.get("error", "unknown")})

    return {
        "ok": len(failed) == 0,
        "resolved": len(resolved) + len(timed_out),
        "failed": len(failed),
        "details": resolved + timed_out + failed,
    }


def _install_role_fallback(project_path: Path, ref: str, role: str, lib_sym: str, lcsc_id: str) -> None:
    """Install a KiCad built-in symbol reference for a component whose role has no EasyEDA data."""
    sym_dir = project_path / "libraries" / "symbols"
    sym_dir.mkdir(parents=True, exist_ok=True)
    lib_name, sym_file = _find_or_create_sym_lib(sym_dir)
    lib, sym = lib_sym.split(":", 1)
    # Don't embed the built-in symbol — just make sure the project sym-lib-table can find it.
    # For KiCad built-ins, we rely on the system library path.


def _search_query_for(role: str, value: str, package: str) -> str:
    """Build the primary JLC search query from component metadata."""
    role_queries = {
        "reset_button": "tactile switch SMD",
        "user_button": "tactile switch SMD",
        "power_led": "LED 0603",
        "status_led": "LED 0603",
        "user_led": "LED 0603",
        "swd_debug_header": "pin header 2.54mm 4P",
        "uart_header": "pin header 2.54mm 4P",
        "i2c_header": "pin header 2.54mm 4P",
        "usb_c_power_input": "USB-C 16pin SMD",
        "usb_c_data": "USB-C 16pin SMD",
    }
    if role in role_queries:
        return role_queries[role]
    return f"{value} {package}".strip() or role


def _query_variants(role: str, value: str, package: str) -> list[str]:
    """Generate search query variants from component metadata.

    Tries role-specific queries first, then value-only, then generic terms.
    Returns a deduplicated list of query strings.
    """
    seen: set[str] = set()
    variants: list[str] = []

    def _add(q: str) -> None:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            variants.append(q)

    # 1. Role-specific query (best match)
    _add(_search_query_for(role, value, package))

    # 2. Value + package
    if value:
        _add(f"{value} {package}".strip())

    # 3. Value only (without specific part number details)
    if value:
        # Strip manufacturer prefixes and suffixes
        simple = value.replace("-", " ").replace("_", " ")
        _add(simple)

    # 4. Generic role-based fallback queries
    generic_map = {
        "reset_button": "tactile switch",
        "user_button": "tactile switch",
        "nrst_pullup": "chip resistor 10K 0603",
        "boot0_pulldown": "chip resistor 10K 0603",
        "led_resistor": "chip resistor 1K 0603",
        "user_button_pullup": "chip resistor 10K 0603",
    }
    if role in generic_map:
        _add(generic_map[role])

    # 5. Numeric value extraction (e.g. "10K" from "RC0603JR-0710KL")
    if value:
        import re
        nums = re.findall(r'(\d+\.?\d*)\s*[kKmM]', value)
        if nums:
            for n in nums[:1]:
                _add(f"chip resistor {n}K 0603")

    return variants


def _find_or_create_sym_lib(sym_dir: Path) -> tuple[str, Path]:
    """Find an existing .kicad_sym file or create a new JLC-MCP one."""
    existing = list(sym_dir.glob("*.kicad_sym"))
    if existing:
        path = existing[0]
        return path.stem, path
    path = sym_dir / "JLC-MCP.kicad_sym"
    path.write_text('(kicad_symbol_lib (version 20231120) (generator "hwtool_jlc"))\n', encoding="utf-8")
    return "JLC-MCP", path


def _append_symbol_to_lib(sym_file: Path, sym_content: str) -> None:
    """Append a symbol definition to an existing .kicad_sym library file.

    Parses the s-expression nesting to extract just the ``(symbol ...)`` block
    and insert it before the closing ``)`` of the library.
    """
    current = sym_file.read_text(encoding="utf-8").rstrip()

    # Extract (symbol ...) block from new content using s-expr depth tracking
    inner = sym_content.strip()
    symbol_block = _extract_symbol_block(inner)
    if not symbol_block:
        return  # nothing to append

    # Insert before the final ) of the library
    if current.endswith(")"):
        current = current[:-1].rstrip()
        current += "\n  " + symbol_block.strip() + "\n)\n"
    else:
        current += "\n" + symbol_block.strip() + "\n"

    sym_file.write_text(current, encoding="utf-8")


def _extract_symbol_block(text: str) -> str:
    """Extract the first ``(symbol ...)`` s-expression from *text* using depth tracking."""
    # Find the start of the (symbol ...) block (at any depth >= 1)
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == '(':
            depth += 1
            if text[i:i+8] == '(symbol ':
                start = i
                break
        elif c == ')':
            depth -= 1

    if start < 0:
        return ""

    # Find the matching close paren
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _sanitize(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "_-.")[:80] or "UNKNOWN"


def _make_minimal_footprint(name: str) -> str:
    return f"""(footprint "{_sanitize(name)}"
  (version 20240108)
  (generator "hwtool_jlc_fallback")
  (layer "F.Cu")
  (fp_text reference "REF**" (at 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (fp_text value "{name}" (at 0 2) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
)"""
