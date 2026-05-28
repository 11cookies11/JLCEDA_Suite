#!/usr/bin/env python3
"""Post-processing helpers for KiCad pipeline output."""

from __future__ import annotations

import json
import subprocess
import sys
import shutil
import re
import locale
from pathlib import Path
from typing import Any

from .adapters.kicad_cli import resolve_kicad_cli
from .env_utils import env
from .kicad_project_writer import DEFAULT_ERC_PIN_MAP, DEFAULT_ERC_RULE_SEVERITIES, find_matching_paren, sanitize_symbol_block

from .env_utils import repo_root

REPO_ROOT = repo_root()


def pin_project_libraries(project_dir: Path) -> dict[str, Any]:
    """Ensure KiCad's project JSON pins the project-local JLC libraries."""
    project_files = sorted(project_dir.glob("*.kicad_pro"))
    if not project_files:
        return {"attempted": True, "success": False, "reason": "no .kicad_pro found"}

    project_file = project_files[0]
    try:
        data = json.loads(project_file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"attempted": True, "success": False, "project": str(project_file), "reason": str(exc)}

    symbols_dir = project_dir / "libraries" / "symbols"
    symbol_files = sorted(symbols_dir.glob("*.kicad_sym")) if symbols_dir.exists() else []
    pinned_symbols = [
        {
            "name": path.stem,
            "type": "KiCad",
            "uri": f"libraries/symbols/{path.name}",
            "options": "",
            "description": f"JLC-MCP {path.stem}",
        }
        for path in symbol_files
    ]
    data["libraries"] = {
        "pinned_footprint_libs": [
            {
                "name": "JLC-MCP",
                "type": "KiCad",
                "uri": "libraries/footprints/JLC-MCP.pretty",
                "options": "",
                "description": "JLC-MCP footprints",
            }
        ],
        "pinned_symbol_libs": pinned_symbols,
    }
    data.setdefault("erc", {
        "erc_exclusions": [],
        "meta": {
            "version": 0,
        },
        "pin_map": DEFAULT_ERC_PIN_MAP,
        "rule_severities": DEFAULT_ERC_RULE_SEVERITIES,
    })
    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "attempted": True,
        "success": True,
        "project": str(project_file),
        "pinned_footprint_libs": 1,
        "pinned_symbol_libs": len(pinned_symbols),
    }


def inject_jlc_symbols(schematic_path: Path) -> bool:
    """Replace JLC-MCP 2-pin stubs with full symbol definitions from library files."""
    import re

    sym_dir = schematic_path.parent / "libraries" / "symbols"
    if not sym_dir.exists():
        return False

    sch = schematic_path.read_text(encoding="utf-8")
    lib_start = sch.find("(lib_symbols")
    if lib_start < 0:
        return False

    depth = 0
    lib_end = lib_start
    for index in range(lib_start, len(sch)):
        if sch[index] == "(":
            depth += 1
        elif sch[index] == ")":
            depth -= 1
            if depth == 0:
                lib_end = index + 1
                break
    lib_section = sch[lib_start:lib_end]

    replaced = 0
    for lib_file in sorted(sym_dir.glob("JLC-MCP-*.kicad_sym")):
        lib_name = lib_file.stem
        lib_content = lib_file.read_text(encoding="utf-8")
        for sym_match in re.finditer(r'\(symbol\s+"([^"]+)"', lib_content):
            sym_name = sym_match.group(1)
            if re.search(r"_\d+_\d+$", sym_name):
                continue
            full_lib_id = lib_name + ":" + sym_name
            if '(symbol "' + full_lib_id + '"' not in lib_section:
                continue
            start = sym_match.start()
            depth2, end = 0, start
            for index in range(start, len(lib_content)):
                if lib_content[index] == "(":
                    depth2 += 1
                elif lib_content[index] == ")":
                    depth2 -= 1
                    if depth2 == 0:
                        end = index + 1
                        break
            full_def = lib_content[start:end]
            derived: list[tuple[str, str]] = []
            pattern = re.compile(r'\(symbol\s+"' + re.escape(sym_name) + r'_\d+_\d+"')
            for derived_match in pattern.finditer(lib_content):
                derived_start = derived_match.start()
                depth3, derived_end = 0, derived_start
                for index in range(derived_start, len(lib_content)):
                    if lib_content[index] == "(":
                        depth3 += 1
                    elif lib_content[index] == ")":
                        depth3 -= 1
                        if depth3 == 0:
                            derived_end = index + 1
                            break
                derived_name = derived_match.group(0).split('"')[1]
                derived.append((derived_name, lib_content[derived_start:derived_end]))
            stub_start = lib_section.find('(symbol "' + full_lib_id + '"')
            if stub_start < 0:
                continue
            depth4, stub_end = 0, stub_start
            for index in range(stub_start, len(lib_section)):
                if lib_section[index] == "(":
                    depth4 += 1
                elif lib_section[index] == ")":
                    depth4 -= 1
                    if depth4 == 0:
                        stub_end = index + 1
                        break
            old_stub = lib_section[stub_start:stub_end]
            new_content = full_def.replace('(symbol "' + sym_name + '"', '(symbol "' + full_lib_id + '"', 1)
            for derived_name, derived_def in derived:
                prefixed = lib_name + ":" + derived_name
                derived_def2 = derived_def.replace('(symbol "' + derived_name + '"', '(symbol "' + prefixed + '"', 1)
                new_content += "\n" + derived_def2
            lib_section = lib_section.replace(old_stub, new_content.strip(), 1)
            replaced += 1

    if replaced > 0:
        schematic_path.write_text(sch[:lib_start] + lib_section + sch[lib_end:], encoding="utf-8")
    return replaced > 0


def register_jlc_libraries(project_dir: Path) -> dict[str, Any]:
    """Register JLC-MCP libraries after schematic generation."""
    install_script = str(repo_root() / 'scripts' / 'install_jlc_mcp_parts.py')
    try:
        process = subprocess.run(
            [sys.executable, install_script, "--project-dir", str(project_dir), "--register-only"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {
            "attempted": True,
            "success": process.returncode == 0,
            "return_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "script": install_script,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "attempted": True,
            "success": False,
            "return_code": None,
            "stdout": "",
            "stderr": str(exc),
            "script": install_script,
        }


def sync_cached_symbol_libraries(schematic_file: Path, project_dir: Path) -> dict[str, Any]:
    """Mirror generated schematic cache symbols into project-local libraries.

    KiCad ERC reports lib_symbol_mismatch when the schematic cache has been
    intentionally normalized (for example passive connector pins) but the
    referenced source library still has the original imported symbol.  For
    generated projects the cache is the source of truth, so keep the local
    symbol libraries aligned with it.
    """
    by_library: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    schematic_files = sorted(project_dir.glob("*.kicad_sch"))
    if schematic_file.exists() and schematic_file not in schematic_files:
        schematic_files.insert(0, schematic_file)

    for path in schematic_files:
        text = path.read_text(encoding="utf-8")
        lib_start = text.find("(lib_symbols")
        if lib_start < 0:
            continue
        lib_end = find_matching_paren(text, lib_start)
        if lib_end < 0:
            continue
        lib_section = text[lib_start:lib_end + 1]
        for match in re.finditer(r'\(symbol\s+"([^":]+):([^"]+)"', lib_section):
            start = match.start()
            end = find_matching_paren(lib_section, start)
            if end < 0:
                continue
            library = match.group(1)
            symbol_name = match.group(2)
            key = (library, symbol_name)
            if key in seen:
                continue
            seen.add(key)
            block = lib_section[start:end + 1]
            block = block.replace(f'(symbol "{library}:{symbol_name}"', f'(symbol "{symbol_name}"', 1)
            block = "\n".join(line[4:] if line.startswith("    ") else line for line in block.splitlines())
            by_library.setdefault(library, []).append(block)

    if not by_library:
        return {"attempted": True, "success": False, "reason": "no cached library symbols found"}

    symbols_dir = project_dir / "libraries" / "symbols"
    symbols_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for library, blocks in sorted(by_library.items()):
        body = "\n\n".join(blocks)
        content = (
            "(kicad_symbol_lib\n"
            "  (version 20231120)\n"
            '  (generator "kicad_suite")\n'
            f"{body}\n"
            ")\n"
        )
        path = symbols_dir / f"{library}.kicad_sym"
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    return {
        "attempted": True,
        "success": True,
        "libraries": sorted(by_library),
        "written_files": written,
        "count": len(written),
    }


def sync_source_libraries(project_dir: Path) -> dict[str, Any]:
    """Copy pre-imported EasyEDA/JLC assets from the source project into output."""
    source_project = env("KICAD_SOURCE_PROJECT_DIR", "")
    if not source_project:
        return {"attempted": False, "reason": "KICAD_SOURCE_PROJECT_DIR not set"}
    source_libraries = Path(source_project) / "libraries"
    if not source_libraries.exists():
        return {"attempted": True, "copied": False, "reason": "source libraries missing", "source": str(source_libraries)}
    target_libraries = project_dir / "libraries"
    target_libraries.mkdir(parents=True, exist_ok=True)
    stale_footprints = target_libraries / "footprints"
    for stale_name in ("jlc_footprints.pretty", "jlc_symbols.pretty"):
        stale_dir = stale_footprints / stale_name
        if stale_dir.exists():
            shutil.rmtree(stale_dir, ignore_errors=True)
    counts: dict[str, int] = {}
    for name in ("symbols", "footprints", "3dmodels"):
        source = source_libraries / name
        target = target_libraries / name
        if source.exists():
            if name == "footprints":
                shutil.copytree(
                    source,
                    target,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("jlc_footprints.pretty", "jlc_symbols.pretty"),
                )
            else:
                shutil.copytree(source, target, dirs_exist_ok=True)
            counts[name] = len([path for path in target.rglob("*") if path.is_file()])
    supplemental_root = REPO_ROOT / "resources" / "kicad" / "footprints"
    if supplemental_root.exists():
        supplemental_total = 0
        for pretty_dir in sorted(supplemental_root.glob("*.pretty")):
            target = target_libraries / "footprints" / pretty_dir.name
            target.mkdir(parents=True, exist_ok=True)
            for footprint in pretty_dir.glob("*.kicad_mod"):
                shutil.copy2(footprint, target / footprint.name)
            supplemental_total += len(list(pretty_dir.glob("*.kicad_mod")))
        counts["supplemental_footprints"] = supplemental_total
        counts["footprints"] = len([path for path in (target_libraries / "footprints").rglob("*") if path.is_file()])
    return {"attempted": True, "copied": True, "source": str(source_libraries), "target": str(target_libraries), "counts": counts}


def sanitize_copied_symbol_libraries(project_dir: Path) -> dict[str, Any]:
    """Remove invalid converter artifacts from project-local symbol libraries."""
    patched_files: list[str] = []
    symbols_dir = project_dir / "libraries" / "symbols"
    if not symbols_dir.exists():
        return {"patched_files": patched_files, "count": 0}
    for path in sorted(symbols_dir.glob("*.kicad_sym")):
        raw = path.read_bytes()
        had_bom = raw.startswith(b"\xef\xbb\xbf")
        text = path.read_text(encoding="utf-8-sig")
        patched = sanitize_symbol_block(text)
        if had_bom or patched != text:
            path.write_text(patched, encoding="utf-8")
            patched_files.append(str(path))
    return {"patched_files": patched_files, "count": len(patched_files)}


def _sanitize_kicad_text_line(line: str) -> str:
    """Repair one-line KiCad property records damaged by mojibake/truncation."""
    if "(property " not in line:
        return line
    if line.count('"') >= 4:
        return line
    match = re.match(r'^(\s*\(property\s+"[^"]+")', line)
    if not match:
        return line
    return f'{match.group(1)} "sanitized"'


def sanitize_footprint_libraries(project_dir: Path) -> dict[str, Any]:
    """Normalize copied footprint files so KiCad GUI can enumerate the library."""
    patched_files: list[str] = []
    footprints_dir = project_dir / "libraries" / "footprints"
    if not footprints_dir.exists():
        return {"patched_files": patched_files, "count": 0}

    utf8_no_bom = "utf-8"
    for path in sorted(footprints_dir.glob("*.pretty/*.kicad_mod")):
        raw = path.read_bytes()
        had_bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw.decode("utf-8-sig")
            had_decode_error = False
        except UnicodeDecodeError:
            text = raw.decode("utf-8-sig", errors="replace")
            had_decode_error = True

        patched = text.replace("\ufffd", "")
        patched = "\n".join(_sanitize_kicad_text_line(line) for line in patched.splitlines())
        if text.endswith(("\n", "\r\n")):
            patched += "\n"

        if had_bom or had_decode_error or patched != text:
            path.write_text(patched, encoding=utf8_no_bom)
            patched_files.append(str(path))

    return {"patched_files": patched_files, "count": len(patched_files)}


def upgrade_footprint_libraries(project_dir: Path) -> dict[str, Any]:
    """Best-effort KiCad CLI footprint library upgrade for copied local libs."""
    footprints_dir = project_dir / "libraries" / "footprints"
    pretty_dirs = sorted(footprints_dir.glob("*.pretty")) if footprints_dir.exists() else []
    if not pretty_dirs:
        return {"attempted": False, "reason": "no project-local footprint libraries"}

    executable = resolve_kicad_cli()
    if not executable:
        return {
            "attempted": True,
            "success": False,
            "error": "kicad-cli was not found",
            "libraries": [str(path) for path in pretty_dirs],
        }

    results: list[dict[str, Any]] = []
    for pretty_dir in pretty_dirs:
        process = subprocess.run(
            [executable, "fp", "upgrade", str(pretty_dir), "--force"],
            capture_output=True,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="ignore",
            timeout=60,
            check=False,
        )
        stdout = process.stdout.replace("\ufffd", "")
        stderr = process.stderr.replace("\ufffd", "")
        results.append(
            {
                "library": str(pretty_dir),
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    return {
        "attempted": True,
        "success": all(item["success"] for item in results),
        "executable": executable,
        "results": results,
    }


def validate_gui_assets(project_dir: Path) -> dict[str, Any]:
    """Check the assets KiCad GUI needs for update-PCB and 3D viewer workflows."""
    issues: list[str] = []
    symbol_bom_files: list[str] = []
    missing_models: list[str] = []

    symbols_dir = project_dir / "libraries" / "symbols"
    if symbols_dir.exists():
        for path in sorted(symbols_dir.glob("*.kicad_sym")):
            raw = path.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                symbol_bom_files.append(str(path))
            if raw[:1] != b"(":
                issues.append(f"symbol library does not start with '(' after sanitization: {path}")

    fp_table = project_dir / "fp-lib-table"
    if not fp_table.exists():
        issues.append("missing project fp-lib-table")
    else:
        table_text = fp_table.read_text(encoding="utf-8", errors="replace")
        if 'name "JLC-MCP"' not in table_text:
            issues.append("project fp-lib-table does not register JLC-MCP")

    footprint_upgrade = upgrade_footprint_libraries(project_dir)
    if footprint_upgrade.get("attempted") and not footprint_upgrade.get("success", False):
        issues.append("kicad-cli could not load/upgrade at least one footprint library")

    model_pattern = re.compile(r'\(model\s+"([^"]+)"')
    for footprint in sorted((project_dir / "libraries" / "footprints").glob("*.pretty/*.kicad_mod")):
        text = footprint.read_text(encoding="utf-8", errors="replace")
        for match in model_pattern.finditer(text):
            model_path = match.group(1)
            resolved = Path(model_path)
            if not resolved.is_absolute():
                resolved = project_dir / model_path
            if not resolved.exists():
                missing_models.append(f"{footprint.name}: {model_path}")

    if symbol_bom_files:
        issues.append(f"symbol libraries still contain UTF-8 BOM: {len(symbol_bom_files)}")
    if missing_models:
        issues.append(f"missing 3D model references: {len(missing_models)}")

    return {
        "attempted": True,
        "success": not issues,
        "issues": issues,
        "symbol_bom_files": symbol_bom_files,
        "missing_models": missing_models,
        "footprint_upgrade": footprint_upgrade,
    }


def patch_known_jlc_symbol_pin_types(project_dir: Path) -> dict[str, Any]:
    """Apply narrow ERC pin-type corrections for known EasyEDA/JLC symbol issues."""
    patched_files: list[str] = []
    memory_symbol = project_dir / "libraries" / "symbols" / "JLC-MCP-Memory.kicad_sym"
    mcu_symbol = project_dir / "libraries" / "symbols" / "JLC-MCP-MCUs.kicad_sym"
    schematic_files = list(project_dir.glob("*.kicad_sch"))
    for path in [memory_symbol, mcu_symbol, *schematic_files]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        patched = re.sub(
            r'(\(pin\s+)output(\s+line(?:(?!\(pin\s).)*?\(name\s+"SCLK")',
            r'\1input\2',
            text,
            count=0,
            flags=re.DOTALL,
        )
        patched = re.sub(
            r'(\(pin\s+)input(\s+line(?:(?!\(pin\s).)*?\(name\s+"U0RXD")',
            r'\1bidirectional\2',
            patched,
            count=0,
            flags=re.DOTALL,
        )
        if patched != text:
            path.write_text(patched, encoding="utf-8")
            patched_files.append(str(path))
    return {"patched_files": patched_files, "count": len(patched_files)}


def apply_postprocess(schematic_file: Path, project_dir: Path) -> dict[str, Any]:
    """Run post-processing after KiCad file generation."""
    library_sync = sync_source_libraries(project_dir)
    symbols_injected = False
    inject_error = ""
    if schematic_file.exists():
        try:
            symbols_injected = inject_jlc_symbols(schematic_file)
        except Exception as exc:  # noqa: BLE001
            inject_error = str(exc)

    symbol_sanitization = sanitize_copied_symbol_libraries(project_dir)
    footprint_sanitization = sanitize_footprint_libraries(project_dir)
    footprint_upgrade = upgrade_footprint_libraries(project_dir)
    pin_type_patches = patch_known_jlc_symbol_pin_types(project_dir)
    symbol_cache_sync = sync_cached_symbol_libraries(schematic_file, project_dir)
    registration = register_jlc_libraries(project_dir)
    project_library_pins = pin_project_libraries(project_dir)
    gui_asset_validation = validate_gui_assets(project_dir)
    return {
        "library_sync": library_sync,
        "symbol_sanitization": symbol_sanitization,
        "footprint_sanitization": footprint_sanitization,
        "footprint_upgrade": footprint_upgrade,
        "pin_type_patches": pin_type_patches,
        "symbol_cache_sync": symbol_cache_sync,
        "symbols_injected": symbols_injected,
        "symbol_injection_error": inject_error,
        "library_registration": registration,
        "project_library_pins": project_library_pins,
        "gui_asset_validation": gui_asset_validation,
    }
