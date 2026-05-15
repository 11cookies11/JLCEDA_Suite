#!/usr/bin/env python3
"""Post-processing helpers for KiCad pipeline output."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


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
    install_script = str(Path(__file__).resolve().parents[2] / "scripts" / "install_jlc_mcp_parts.py")
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


def apply_postprocess(schematic_file: Path, project_dir: Path) -> dict[str, Any]:
    """Run post-processing after KiCad file generation."""
    symbols_injected = False
    inject_error = ""
    if schematic_file.exists():
        try:
            symbols_injected = inject_jlc_symbols(schematic_file)
        except Exception as exc:  # noqa: BLE001
            inject_error = str(exc)

    registration = register_jlc_libraries(project_dir)
    return {
        "symbols_injected": symbols_injected,
        "symbol_injection_error": inject_error,
        "library_registration": registration,
    }
