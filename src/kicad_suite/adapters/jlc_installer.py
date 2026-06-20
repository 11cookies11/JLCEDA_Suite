"""Install JLC components into project libraries — fetch, convert, save."""

from __future__ import annotations

import json
from dataclasses import dataclass
import re
import random
import time as _time
from pathlib import Path
from typing import Any

from . import jlc_api
from ..domain.core.circuit_model_io import save_resolved_circuit_model
from .easyeda_parser import parse_easyeda_component, ParsedComponent
from .easyeda_converter import build_kicad_symbol, build_kicad_footprint, make_two_pin_symbol

# KiCad library section template for sym-lib-table / fp-lib-table
_SYM_LIB_TEMPLATE = """(sym_lib_table
  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))
)
"""

_installed_lcsc_cache: dict[str, dict[str, str]] = {}
_CACHE_FILENAME = "easyeda-download-cache.json"


def _persistent_cache_path(project_path: Path) -> Path:
    return project_path / "build" / _CACHE_FILENAME


def _load_persistent_cache(project_path: Path) -> dict[str, dict[str, str]]:
    """Load previously downloaded component metadata from disk into memory."""
    global _installed_lcsc_cache
    cache_file = _persistent_cache_path(project_path)
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Merge into in-memory cache (only for entries not already loaded)
            for key, value in data.items():
                if isinstance(value, dict) and key not in _installed_lcsc_cache:
                    _installed_lcsc_cache[key] = value
            return {k: v for k, v in data.items() if isinstance(v, dict)}
    except (json.JSONDecodeError, OSError):
        return {}
    return {}


def _save_persistent_cache(project_path: Path, cache: dict[str, dict[str, str]]) -> None:
    """Persist download cache to disk so subsequent runs skip already-downloaded parts."""
    cache_file = _persistent_cache_path(project_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    # Only persist entries that have meaningful metadata (title + package)
    slim: dict[str, dict[str, str]] = {}
    for key, value in cache.items():
        if isinstance(value, dict) and value.get("title"):
            slim[key] = {
                "title": str(value.get("title", "")),
                "package": str(value.get("package", "")),
                "pin_count": str(value.get("pin_count", "0")),
                "symbol_ref": str(value.get("symbol_ref", "")),
            }
    cache_file.write_text(json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _verify_cached_symbols_exist(project_path: Path, cache_entry: dict[str, str]) -> bool:
    """Check that this specific component's symbol, footprint and 3D model files still exist on disk."""
    package = str(cache_entry.get("package", ""))
    if not package:
        # Fallback: at least some library files must exist
        sym_dir = project_path / "libraries" / "symbols"
        fp_dir = project_path / "libraries" / "footprints" / "JLC-MCP.pretty"
        return any(sym_dir.glob("*.kicad_sym")) and any(fp_dir.glob("*.kicad_mod"))

    fp_dir = project_path / "libraries" / "footprints" / "JLC-MCP.pretty"
    fp_file = fp_dir / f"{package}.kicad_mod"
    if not fp_file.exists():
        return False
    # Check that the 3D model directory has at least one file (only relevant if models were previously generated)
    model_dir = project_path / "libraries" / "3dmodels" / "JLC-MCP.3dshapes"
    if model_dir.exists() and not any(model_dir.iterdir()):
        # Models dir exists but is empty — footprint may reference models that don't exist
        # Don't fail the cache hit over this; models are non-critical
        pass
    return True


def _looks_rate_limited(text: str) -> bool:
    lowered = text.lower()
    return "403" in lowered or "forbidden" in lowered or "rate limit" in lowered or "too many requests" in lowered


@dataclass(frozen=True)
class EasyedaAccessPolicy:
    """Shared retry and pacing rules for EasyEDA access."""

    delay_range: tuple[float, float] = (3.0, 8.0)
    rate_limit_cooldown: float = 30.0
    max_attempts: int = 2
    install_retries: int = 2
    install_delay: float = 30.0
    search_limit: int = 3

    def search(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        last_error = ""
        limit_value = limit if limit is not None else self.search_limit
        for attempt in range(self.max_attempts):
            _time.sleep(random.uniform(*self.delay_range))
            try:
                return jlc_api.search(query, limit=limit_value)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt < self.max_attempts - 1 and _looks_rate_limited(last_error):
                    _time.sleep(self.rate_limit_cooldown)
                    continue
                break
        if last_error and not _looks_rate_limited(last_error):
            raise RuntimeError(last_error) from None
        return []

    def install(self, lcsc_id: str, project_path: Path) -> dict[str, Any]:
        return install_by_lcsc_id(
            lcsc_id,
            project_path,
            retries=self.install_retries,
            delay=self.install_delay,
            initial_delay_range=self.delay_range,
        )


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


def install_by_lcsc_id(
    lcsc_id: str,
    project_path: Path,
    *,
    retries: int = 5,
    delay: float = 0.5,
    initial_delay_range: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Download component data from EasyEDA and install symbol + footprint into *project_path*.

    Cache hits (in-memory or persistent disk cache) skip the network call entirely.
    Previously downloaded components are re-used across process invocations.
    """
    global _installed_lcsc_cache
    cache_key = f"{project_path.resolve()}:{lcsc_id}"

    # 1) In-memory cache (same process)
    cached = _installed_lcsc_cache.get(cache_key)
    if cached is not None and isinstance(cached, dict):
        if _verify_cached_symbols_exist(project_path, cached):
            return {
                "ok": True,
                "lcsc_id": lcsc_id,
                "cached": True,
                "pin_count": int(cached.get("pin_count", 0)),
                "package": str(cached.get("package", "")),
                "title": str(cached.get("title", "")),
                "symbol_ref": str(cached.get("symbol_ref", "")),
            }
        else:
            # Library files missing — evict stale cache entry
            del _installed_lcsc_cache[cache_key]

    # 2) Persistent disk cache (survives process restarts)
    _load_persistent_cache(project_path)
    cached = _installed_lcsc_cache.get(cache_key)
    if cached is not None and isinstance(cached, dict):
        if _verify_cached_symbols_exist(project_path, cached):
            return {
                "ok": True,
                "lcsc_id": lcsc_id,
                "cached": True,
                "pin_count": int(cached.get("pin_count", 0)),
                "package": str(cached.get("package", "")),
                "title": str(cached.get("title", "")),
                "symbol_ref": str(cached.get("symbol_ref", "")),
            }
        else:
            del _installed_lcsc_cache[cache_key]

    if initial_delay_range is not None:
        _time.sleep(random.uniform(*initial_delay_range))

    # 3) Network fetch from EasyEDA
    comp_data = jlc_api.get_component(lcsc_id, retries=retries, delay=delay)
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
    raw_symbol_name = _extract_symbol_name(sym_str) or str(comp_data.get("title", "")).strip() or lcsc_id
    symbol_name = _sanitize_symbol_name(raw_symbol_name)
    if raw_symbol_name and raw_symbol_name != symbol_name:
        sym_str = _rename_symbol_block(sym_str, raw_symbol_name, symbol_name)

    # 3. Ensure project library directories exist
    sym_dir = project_path / "libraries" / "symbols"
    fp_dir = project_path / "libraries" / "footprints" / "JLC-MCP.pretty"
    sym_dir.mkdir(parents=True, exist_ok=True)
    fp_dir.mkdir(parents=True, exist_ok=True)

    # 4. Determine library name and write symbol
    lib_name, sym_file = _find_or_create_sym_lib(sym_dir)
    _append_symbol_to_lib(sym_file, sym_str, library_name=lib_name)

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

    # 6. Generate 3D model from EasyEDA data (if available)
    model_dir = project_path / "libraries" / "3dmodels" / "JLC-MCP.3dshapes"
    try:
        from easyeda2kicad.easyeda.easyeda_importer import Easyeda3dModelImporter  # noqa: PLC0415
        from easyeda2kicad.kicad import Exporter3dModelKicad  # noqa: PLC0415
        model_importer = Easyeda3dModelImporter(ee_envelope, download_raw_3d_model=True)
        if model_importer.output:
            model_dir.mkdir(parents=True, exist_ok=True)
            model_exporter = Exporter3dModelKicad(model_importer.output)
            model_exporter.export(str(model_dir))
    except Exception:
        # 3D model data may be unavailable for some components — non-critical
        pass

    # 6b. Normalize 3D model paths in the footprint to ${KIPRJMOD} relative format
    if fp_file.exists():
        _normalize_footprint_3d_paths(fp_file)

    # Cache both in-memory and on disk so subsequent runs skip the network call
    # Store the *sanitized* package name so it matches the footprint filename on disk
    cache_entry = {
        "title": str(comp_data.get("title", "")),
        "package": _sanitize(str(comp_data.get("package_title", lcsc_id))),
        "pin_count": str(pin_count),
        "symbol_ref": str(symbol_name),
    }
    _installed_lcsc_cache[cache_key] = cache_entry
    _save_persistent_cache(project_path, _installed_lcsc_cache)
    return {
        "ok": True,
        "lcsc_id": lcsc_id,
        "title": cache_entry["title"],
        "symbol_ref": symbol_name,
        "package": cache_entry["package"],
        "symbol_file": str(sym_file),
        "symbol_count": 1,
        "footprint_file": str(fp_file),
        "pin_count": pin_count,
    }


def _resolve_missing_symbols_legacy(
    project_path: Path,
    model: dict[str, Any],
    timeout: float = 120.0,
    *,
    policy: EasyedaAccessPolicy | None = None,
    model_path: Path | None = None,
) -> dict[str, Any]:
    """Auto-resolve all components in *model* by searching EasyEDA.

    For each component the resolver tries (in order):
    1. Component-specific ``search_hints`` from the DSL model (best)
    2. value + package (automatic)
    3. Minimal 2-pin placeholder as last resort

    The default policy uses random 3-8 second delays and a 30 second
    cooldown after rate-limit responses.

    Components that successfully resolve get ``selected_part`` written
    back into *model* so the build step can find their symbols.
    """
    access = policy or EasyedaAccessPolicy()
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
        selected = comp.get("selected_part", {}) if isinstance(comp.get("selected_part"), dict) else {}
        selected_lcsc_id = str(selected.get("lcsc_id", "")).strip()

        # If the DSL already resolved this component to a concrete LCSC ID,
        # trust that selection and skip the search-based path entirely.
        # This avoids re-searching known parts and hitting rate/403 limits.
        if selected_lcsc_id:
            inst = access.install(selected_lcsc_id, project_path)
            if inst.get("ok"):
                resolved.append(
                    {
                        "ref": ref,
                        "lcsc_id": selected_lcsc_id,
                        "title": inst.get("title", ""),
                        "source": "selected_part_lcsc_id",
                        "pin_count": inst.get("pin_count", 0),
                    }
                )
                _write_selected_part(
                    comp,
                    selected_lcsc_id,
                    inst.get("title", ""),
                    inst.get("package", ""),
                    symbol_ref=str(inst.get("symbol_ref", "")),
                )
            else:
                failed.append(
                    {
                        "ref": ref,
                        "role": role,
                        "lcsc_id": selected_lcsc_id,
                        "error": str(inst.get("error", "selected_part_install_failed")),
                    }
                )
            continue

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
                results = access.search(str(hint))
                if results:
                    inst = _try_install_candidates(results, project_path, access)
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
                continue

        # -- pass 2: value + package (automatic) ----------------------------
        specific_query = f"{value} {package}".strip()
        if specific_query:
            results = access.search(specific_query)
            if results:
                inst = _try_install_candidates(results, project_path, access)
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
            continue

        # -- pass 3: placeholder — agent should add search_hints and re-run --
        inst = _resolve_two_pin_placeholder(project_path, value, ref)
        if inst.get("ok"):
            resolved.append({"ref": ref, "lcsc_id": "", "role": role, "source": "placeholder", "pin_count": 2, "hint": "add search_hints to DSL and re-run resolve-symbols"})
        else:
            failed.append({"ref": ref, "role": role, "error": "all_attempts_failed"})

    # Persist selected_part back to the source circuit model.
    if model_path is None:
        model_path = project_path / "source" / "circuit-model.source.json"
    save_resolved_circuit_model(model_path, model)

    summary = {
        "ok": len(failed) == 0,
        "resolved": len(resolved) + len(timed_out),
        "failed": len(failed),
        "model_updated": True,
        "details": resolved + timed_out + failed,
    }

    return summary


def resolve_missing_symbols(
    project_path: Path,
    model: dict[str, Any],
    timeout: float = 120.0,
    *,
    policy: EasyedaAccessPolicy | None = None,
    model_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve components into project-local libraries.

    ``resolved`` counts only real EasyEDA downloads. Components without a
    selected_part.lcsc_id are reported as ``needs_selection``.
    """
    access = policy or EasyedaAccessPolicy()
    components = model.get("components", [])
    if not isinstance(components, list):
        return {
            "ok": True,
            "resolved": 0,
            "downloaded": 0,
            "needs_selection": 0,
            "failed": 0,
            "details": [],
        }

    deadline = _time.monotonic() + timeout
    resolved: list[dict[str, Any]] = []
    needs_selection: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    install_cache: dict[str, dict[str, Any]] = {}

    for comp in components:
        if not isinstance(comp, dict):
            continue

        ref = comp.get("ref", "?")
        role = comp.get("role", "")
        value = str(comp.get("value", "") or "")
        selected = comp.get("selected_part", {}) if isinstance(comp.get("selected_part"), dict) else {}
        selected_lcsc_id = str(selected.get("lcsc_id", "")).strip()

        skip_reason = _lcsc_exemption_reason(comp)
        if skip_reason and not selected_lcsc_id:
            skipped.append({"ref": ref, "role": role, "value": value, "reason": skip_reason})
            continue

        if selected_lcsc_id:
            inst = install_cache.get(selected_lcsc_id)
            if inst is None and _time.monotonic() > deadline:
                needs_selection.append({"ref": ref, "role": role, "value": value, "reason": "timeout"})
                continue
            if inst is None:
                inst = access.install(selected_lcsc_id, project_path)
                install_cache[selected_lcsc_id] = inst
            if inst.get("ok"):
                resolved.append(
                    {
                        "ref": ref,
                        "lcsc_id": selected_lcsc_id,
                        "title": inst.get("title", ""),
                        "source": "selected_part_lcsc_id",
                        "pin_count": inst.get("pin_count", 0),
                    }
                )
                _write_selected_part(
                    comp,
                    selected_lcsc_id,
                    inst.get("title", ""),
                    inst.get("package", ""),
                    symbol_ref=str(inst.get("symbol_ref", "")),
                )
            else:
                failed.append(
                    {
                        "ref": ref,
                        "role": role,
                        "lcsc_id": selected_lcsc_id,
                        "error": str(inst.get("error", "selected_part_install_failed")),
                    }
                )
            continue

        needs_selection.append({"ref": ref, "role": role, "value": value, "reason": "missing_selected_part_lcsc_id"})

    if model_path is None:
        model_path = project_path / "source" / "circuit-model.source.json"
    save_resolved_circuit_model(model_path, model)

    return {
        "ok": len(failed) == 0 and len(needs_selection) == 0,
        "resolved": len(resolved),
        "downloaded": len(resolved),
        "needs_selection": len(needs_selection),
        "failed": len(failed),
        "skipped": len(skipped),
        "model_updated": True,
        "details": resolved + skipped + needs_selection + failed,
    }


def _try_install_candidates(results: list[dict[str, Any]], project_path: Path, access: EasyedaAccessPolicy) -> dict[str, Any] | None:
    """Try installing each candidate; return the first successful result or None."""
    for r in results:
        result = access.install(r["lcsc_id"], project_path)
        if result.get("ok"):
            return result
    return None


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
    existing = component.get("selected_part", {})
    sp: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    sp["lcsc_id"] = lcsc_id
    sp["display_name"] = display_name

    existing_fp = str(sp.get("kicad_footprint_hint", "")).strip()
    if existing_fp:
        sp["kicad_footprint_hint"] = existing_fp
    elif fp_hint:
        sp["kicad_footprint_hint"] = fp_hint

    existing_symbol_ref = str(sp.get("symbol_ref", "")).strip()
    if existing_symbol_ref:
        sp["symbol_ref"] = existing_symbol_ref
    elif symbol_ref:
        sp["symbol_ref"] = symbol_ref
    component["selected_part"] = sp


def _lcsc_exemption_reason(component: dict[str, Any]) -> str:
    selected = component.get("selected_part", {}) if isinstance(component.get("selected_part"), dict) else {}
    if _truthy(component.get("bom_exclude")) or _truthy(selected.get("bom_exclude")):
        return "bom_exclude"
    if _truthy(component.get("dnp")) or _truthy(component.get("do_not_populate")):
        return "dnp"
    assembly = str(component.get("assembly", selected.get("assembly", "")) or "").strip().lower()
    if assembly in {"dnp", "do_not_populate", "do-not-populate", "not_populated", "not-fitted", "not_fitted"}:
        return "dnp"
    part_source = str(component.get("part_source", selected.get("part_source", "")) or "").strip().lower()
    if part_source in {"internal", "local", "project_local", "project-local", "pcb"}:
        return "internal"
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _extract_symbol_name(sym_str: str) -> str:
    match = re.match(r'\(symbol\s+"([^"]+)"', sym_str.strip())
    if match:
        return match.group(1)
    return ""


def _sanitize_symbol_name(name: str) -> str:
    cleaned = name.replace(" ", "_").replace(":", "_").replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", cleaned)
    return cleaned.strip("._-") or "UNKNOWN"


def _rename_symbol_block(sym_str: str, raw_name: str, safe_name: str) -> str:
    """Rename the primary and nested symbol names inside a KiCad symbol block."""
    renamed = sym_str.replace(raw_name, safe_name)
    renamed = renamed.replace(f'(symbol "{safe_name}"', f'(symbol "{safe_name}"', 1)
    return renamed


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


def _append_symbol_to_lib(sym_file: Path, sym_content: str, *, library_name: str = "") -> bool:
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
    normalized_current = _qualify_symbol_footprint_references(current, library_name)
    if f'(symbol "{sym_name}"' in current:
        if normalized_current != current:
            sym_file.write_text(normalized_current + "\n", encoding="utf-8")
        return False  # already exists, skip

    if normalized_current.endswith(")"):
        normalized_current = normalized_current[:-1].rstrip()
        normalized_current += "\n" + symbol_block + "\n)\n"
    else:
        normalized_current += "\n" + symbol_block + "\n"

    sym_file.write_text(normalized_current, encoding="utf-8")
    return True


def _qualify_symbol_footprint_references(text: str, library_name: str) -> str:
    """Expand KiCad's local ``:footprint`` shorthand for portable exports."""
    if not library_name:
        return text
    prefix = f"{library_name}:"
    patched = re.sub(
        r'(\(property\s+"Footprint"\s+"):(?=[^"]*")',
        rf'\1{prefix}',
        text,
    )
    return re.sub(
        r'(^\s*"Footprint"\s*\r?\n\s*"):(?=[^"]*")',
        rf'\1{prefix}',
        patched,
        flags=re.MULTILINE,
    )


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


def _normalize_footprint_3d_paths(fp_file: Path) -> None:
    """Rewrite 3D model paths in *fp_file* to ${KIPRJMOD} relative format.

    EasyEDA/kicad converters often emit absolute or bare-filename paths;
    this normalizes them so KiCad can resolve models from the project root.
    """
    raw = fp_file.read_text(encoding="utf-8")
    if '(model "' not in raw:
        return

    def _rewrite(m: re.Match) -> str:
        full = m.group(1)
        if full.startswith("${KIPRJMOD}"):
            return m.group(0)  # already normalized
        basename = Path(full).name
        if not basename or not basename.endswith((".step", ".wrl", ".stp")):
            return m.group(0)  # not a 3D model reference
        return f'(model "${{KIPRJMOD}}/libraries/3dmodels/JLC-MCP.3dshapes/{basename}"'

    patched = re.sub(r'\(model\s+"([^"]+)"', _rewrite, raw)
    if patched != raw:
        fp_file.write_text(patched, encoding="utf-8")
