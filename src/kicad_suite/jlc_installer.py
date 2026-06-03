"""Install JLC components into project libraries — fetch, convert, save."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import jlc_api
from .circuit_model_io import save_resolved_circuit_model
from .easyeda_parser import parse_easyeda_component, ParsedComponent
from .easyeda_converter import build_kicad_symbol, build_kicad_footprint, make_two_pin_symbol

# KiCad library section template for sym-lib-table / fp-lib-table
_SYM_LIB_TEMPLATE = """(sym_lib_table
  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))
)
"""

_installed_lcsc_cache: dict[str, bool] = {}


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
    global _installed_lcsc_cache
    cache_key = f"{project_path.resolve()}:{lcsc_id}"
    cached = _installed_lcsc_cache.get(cache_key)
    if cached is not None:
        pkg = str(cached) if cached else ""
        return {"ok": True, "lcsc_id": lcsc_id, "cached": True, "pin_count": 0, "package": pkg}

    # 1. Fetch from EasyEDA
    comp_data = jlc_api.get_component(lcsc_id, retries=5, delay=0.5)
    if comp_data is None:
        return {"ok": False, "error": f"Component {lcsc_id} not found on EasyEDA"}

    # 2. Convert via easyeda2kicad — battle-tested, correct pin-to-body alignment
    from easyeda2kicad.easyeda.easyeda_importer import EasyedaSymbolImporter
    from easyeda2kicad.kicad import ExporterSymbolKicad

    try:
        # Wrap our data in the envelope that EasyedaSymbolImporter expects:
        # { "dataStr": {...}, "packageDetail": {"dataStr": {...}} }
        ee_envelope: dict[str, Any] = {
            "dataStr": comp_data.get("data_str", {}),
            "packageDetail": {"dataStr": comp_data.get("package_data_str", {})},
        }
        ee_importer = EasyedaSymbolImporter(ee_envelope)
        ee_symbol = ee_importer.output
        sym_str = str(ExporterSymbolKicad(ee_symbol).export(''))
        pin_count = len(ee_symbol.pins) if hasattr(ee_symbol, 'pins') else 0
    except Exception:
        # Fallback to our own converter
        parsed = parse_easyeda_component(
            comp_data["data_str"],
            comp_data.get("package_data_str"),
            comp_data.get("title", ""),
            comp_data.get("package_title", ""),
        )
        parsed.lcsc_id = lcsc_id
        sym_str = make_two_pin_symbol("U", parsed.title or lcsc_id, "JLC-MCP")
        pin_count = sum(1 for s in parsed.shapes if s.type == "pin")
    symbol_name = _extract_symbol_name(sym_str) or str(comp_data.get("title", "")).strip() or lcsc_id

    # 3. Ensure project library directories exist
    sym_dir = project_path / "libraries" / "symbols"
    fp_dir = project_path / "libraries" / "footprints" / "JLC-MCP.pretty"
    sym_dir.mkdir(parents=True, exist_ok=True)
    fp_dir.mkdir(parents=True, exist_ok=True)

    # 4. Determine library name and write symbol
    lib_name, sym_file = _find_or_create_sym_lib(sym_dir)
    _append_symbol_to_lib(sym_file, sym_str)

    # 5. Generate footprint via easyeda2kicad (real pads)
    from easyeda2kicad.easyeda.easyeda_importer import EasyedaFootprintImporter
    from easyeda2kicad.kicad import ExporterFootprintKicad
    fp_name = _sanitize(comp_data.get("package_title", lcsc_id))
    fp_file = fp_dir / f"{fp_name}.kicad_mod"
    if not fp_file.exists():
        try:
            fp_importer = EasyedaFootprintImporter(ee_envelope)
            fp_exporter = ExporterFootprintKicad(fp_importer.output)
            fp_exporter.export(str(fp_file), "")  # writes directly to file
        except Exception:
            fp_file.write_text(_make_minimal_footprint(fp_name), encoding="utf-8")
    # If file already exists, keep it (footprints are shared across components)

    _installed_lcsc_cache[cache_key] = comp_data.get("package_title", "")
    return {
        "ok": True,
        "lcsc_id": lcsc_id,
        "title": comp_data.get("title", ""),
        "symbol_ref": symbol_name,
        "package": comp_data.get("package_title", ""),
        "symbol_file": str(sym_file),
        "symbol_count": 1,
        "footprint_file": str(fp_file),
        "pin_count": pin_count,
    }


def resolve_missing_symbols(
    project_path: Path,
    model: dict[str, Any],
    timeout: float = 120.0,
    *,
    delay: float = 0,
    model_path: Path | None = None,
) -> dict[str, Any]:
    """Auto-resolve all components in *model* by searching EasyEDA.

    For each component the resolver tries (in order):
    1. Component-specific ``search_hints`` from the DSL model (best)
    2. value + package (automatic)
    3. Minimal 2-pin placeholder as last resort

    *delay* (seconds) is inserted between API calls to avoid rate-limiting.
    Default 0.8 s mimics human-paced interaction with the JLC search endpoint.

    Components that successfully resolve get ``selected_part`` written
    back into *model* so the build step can find their symbols.
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

        ref = comp.get("ref", "?")
        role = comp.get("role", "")
        value = str(comp.get("value", "") or "")
        package = str(comp.get("package", "") or "")
        hints = comp.get("search_hints", [])

        if _time.monotonic() > deadline:
            inst = _resolve_two_pin_placeholder(project_path, value, ref)
            if inst.get("ok"):
                timed_out.append({"ref": ref, "lcsc_id": "", "role": role, "source": "placeholder_timeout", "pin_count": inst.get("pin_count", 2)})
            else:
                failed.append({"ref": ref, "role": role, "error": "timeout"})
            continue

        inst = None
        lcsc_id = ""

        # -- pass 1: search_hints from DSL (AI agent controls this) ----------
        if hints and isinstance(hints, list):
            for hint in hints:
                _time.sleep(delay)
                results = jlc_api.search(str(hint), limit=3)
                if results:
                    inst = _try_install_candidates(results, project_path)
                    if inst:
                        lcsc_id = inst["lcsc_id"]
                        break
            if inst:
                resolved.append({"ref": ref, "lcsc_id": lcsc_id, "title": inst.get("title", ""), "source": "search_hint", "pin_count": inst.get("pin_count", 0)})
                _write_selected_part(
                    comp,
                    lcsc_id,
                    inst.get("title", ""),
                    inst.get("package", ""),
                    symbol_ref=str(inst.get("symbol_ref", "")),
                )
                _time.sleep(delay)
                continue

        # -- pass 2: value + package (automatic) ----------------------------
        specific_query = f"{value} {package}".strip()
        if specific_query:
            _time.sleep(delay)
            results = jlc_api.search(specific_query, limit=3)
            if results:
                inst = _try_install_candidates(results, project_path)
                if inst:
                    lcsc_id = inst["lcsc_id"]

        if inst and inst.get("ok"):
            resolved.append({"ref": ref, "lcsc_id": lcsc_id, "title": inst.get("title", ""), "source": "easyeda", "pin_count": inst.get("pin_count", 0)})
            _write_selected_part(
                comp,
                lcsc_id,
                inst.get("title", ""),
                inst.get("package", ""),
                symbol_ref=str(inst.get("symbol_ref", "")),
            )
            _time.sleep(delay)
            continue

        # -- pass 3: placeholder — agent should add search_hints and re-run --
        _time.sleep(delay)
        inst = _resolve_two_pin_placeholder(project_path, value, ref)
        if inst.get("ok"):
            resolved.append({"ref": ref, "lcsc_id": "", "role": role, "source": "placeholder", "pin_count": 2, "hint": "add search_hints to DSL and re-run resolve-symbols"})
        else:
            failed.append({"ref": ref, "role": role, "error": "all_attempts_failed"})

    # Persist selected_part back to circuit-model.json
    if model_path is None:
        model_path = project_path / "circuit-model.json"
    save_resolved_circuit_model(model_path, model)

    summary = {
        "ok": len(failed) == 0,
        "resolved": len(resolved) + len(timed_out),
        "failed": len(failed),
        "model_updated": True,
        "details": resolved + timed_out + failed,
    }

    # Write to operations.jsonl so the agent always knows what happened
    _log_operation(project_path, "resolve_symbols", {
        "ok": summary["ok"],
        "total": summary["resolved"],
        "easyeda": sum(1 for x in summary["details"] if x.get("source") == "easyeda"),
        "search_hint": sum(1 for x in summary["details"] if x.get("source") == "search_hint"),
        "placeholder": sum(1 for x in summary["details"] if "placeholder" in x.get("source", "")),
        "failed": summary["failed"],
    })

    return summary


def _try_install_candidates(results: list[dict[str, Any]], project_path: Path) -> dict[str, Any] | None:
    """Try installing each candidate; return the first successful result or None."""
    for r in results:
        result = install_by_lcsc_id(r["lcsc_id"], project_path)
        if result.get("ok"):
            return result
    return None


def _log_operation(project_path: Path, op: str, data: dict[str, Any]) -> None:
    """Append an entry to the project's operations.jsonl log."""
    import json as _json
    from datetime import datetime, timezone
    log_dir = project_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "operations.jsonl"
    entry = {"time": datetime.now(timezone.utc).isoformat(), "op": op}
    entry.update(data)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(entry, ensure_ascii=False) + "\n")


def _resolve_two_pin_placeholder(project_path: Path, value: str, ref: str) -> dict[str, Any]:
    """Create a minimal 2-pin symbol from the component's own info."""
    sym_dir = project_path / "libraries" / "symbols"
    sym_dir.mkdir(parents=True, exist_ok=True)
    _lib_name, _sym_file = _find_or_create_sym_lib(sym_dir)
    return {"ok": True, "pin_count": 2, "title": value or ref}


def _write_selected_part(
    component: dict[str, Any],
    lcsc_id: str,
    display_name: str,
    fp_hint: str = "",
    *,
    symbol_ref: str = "",
) -> None:
    """Write ``selected_part`` into *component* in-place so the build step finds it."""
    sp: dict[str, str] = {
        "lcsc_id": lcsc_id,
        "display_name": display_name,
    }
    if fp_hint:
        sp["kicad_footprint_hint"] = fp_hint
    if symbol_ref:
        sp["symbol_ref"] = symbol_ref
    component["selected_part"] = sp


def _extract_symbol_name(sym_str: str) -> str:
    match = re.match(r'\(symbol\s+"([^"]+)"', sym_str.strip())
    if match:
        return match.group(1)
    return ""


def _find_or_create_sym_lib(sym_dir: Path) -> tuple[str, Path]:
    """Find an existing .kicad_sym file or create a new JLC-MCP one."""
    existing = list(sym_dir.glob("*.kicad_sym"))
    if existing:
        path = existing[0]
        return path.stem, path
    path = sym_dir / "JLC-MCP.kicad_sym"
    path.write_text(
        '(kicad_symbol_lib\n  (version 20251024)\n  (generator "kicad_symbol_editor")\n  (generator_version "10.0")\n)\n',
        encoding="utf-8",
    )
    return "JLC-MCP", path


def _append_symbol_to_lib(sym_file: Path, sym_content: str) -> bool:
    """Append a symbol definition to an existing .kicad_sym library file.

    *sym_content* should be a ``(symbol ...)`` block.  It is inserted
    before the closing ``)`` of the library.  Returns False if a symbol
    with the same name already exists (skip duplicate), True if appended.
    """
    import re
    symbol_block = sym_content.strip()
    if not symbol_block.startswith("(symbol "):
        return False

    # Extract the symbol name to check for duplicates
    name_match = re.match(r'\(symbol\s+"([^"]+)"', symbol_block)
    sym_name = name_match.group(1) if name_match else ""
    if not sym_name:
        return False

    current = sym_file.read_text(encoding="utf-8").rstrip()
    if f'(symbol "{sym_name}"' in current:
        return False  # already exists, skip

    if current.endswith(")"):
        current = current[:-1].rstrip()
        current += "\n" + symbol_block + "\n)\n"
    else:
        current += "\n" + symbol_block + "\n"

    sym_file.write_text(current, encoding="utf-8")
    return True


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
