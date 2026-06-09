"""Application service for project symbol normalization."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..adapters.kicad_project_writer import find_matching_paren, sanitize_lib_symbols_section, sanitize_symbol_block
from ..shared.sexpr_parser import parse as parse_sexpr, symbols_in_library


class SymbolNormalizationService:
    """Normalize generated/imported symbol assets after KiCad export."""

    def normalize_project_symbols(self, project_dir: str | Path, schematic_file: str | Path | None = None) -> dict[str, Any]:
        project = Path(project_dir)
        schematic = Path(schematic_file) if schematic_file is not None else _first_schematic(project)
        symbols_injected = False
        inject_error = ""
        if schematic and schematic.exists():
            try:
                symbols_injected = self.inject_jlc_symbols(schematic)
            except Exception as exc:  # noqa: BLE001
                inject_error = str(exc)

        return {
            "symbol_sanitization": self.sanitize_copied_symbol_libraries(project),
            "pin_type_patches": self.patch_known_jlc_symbol_pin_types(project),
            "symbol_cache_sync": self.sync_cached_symbol_libraries(schematic, project) if schematic else {
                "attempted": False,
                "reason": "no schematic file",
            },
            "symbols_injected": symbols_injected,
            "symbol_injection_error": inject_error,
            "schematic_sanitization": self.sanitize_generated_schematics(project),
        }

    def inject_jlc_symbols(self, schematic_path: str | Path) -> bool:
        """Replace JLC-MCP 2-pin stubs with full symbol definitions from library files."""
        schematic = Path(schematic_path)
        proj_libs = _find_project_libraries_dir(schematic.parent)
        sym_dir = (proj_libs / "symbols") if proj_libs else (schematic.parent / "libraries" / "symbols")
        if not sym_dir.exists():
            return False

        lib_files = sorted(sym_dir.glob("JLC-MCP*.kicad_sym"))
        if not lib_files:
            return False

        total_replaced = 0
        for lib_file in lib_files:
            lib_name = lib_file.stem
            lib_content = lib_file.read_text(encoding="utf-8")
            for sch_path in sorted(schematic.parent.glob("*.kicad_sch")):
                total_replaced += _inject_symbols_into_sheet(sch_path, lib_name, lib_content)

        return total_replaced > 0

    def sync_cached_symbol_libraries(self, schematic_file: str | Path, project_dir: str | Path) -> dict[str, Any]:
        """Mirror generated schematic cache symbols into project-local libraries."""
        schematic = Path(schematic_file)
        project = Path(project_dir)
        by_library: dict[str, list[str]] = {}
        seen: set[tuple[str, str]] = set()
        schematic_files = sorted(project.glob("*.kicad_sch"))
        if schematic.exists() and schematic not in schematic_files:
            schematic_files.insert(0, schematic)

        for path in schematic_files:
            text = path.read_text(encoding="utf-8")
            lib_start = text.find("(lib_symbols")
            if lib_start < 0:
                continue
            lib_end = find_matching_paren(text, lib_start)
            if lib_end < 0:
                continue
            lib_section = text[lib_start:lib_end + 1]
            try:
                tree = parse_sexpr(lib_section)
            except Exception:
                continue
            for sym in tree.find("symbol"):
                if len(sym.values) < 1:
                    continue
                full_name = sym.values[0]
                if ":" not in full_name:
                    continue
                library, symbol_name = full_name.split(":", 1)
                key = (library, symbol_name)
                if key in seen:
                    continue
                seen.add(key)
                # Extract the raw S-expression block for this symbol
                start = lib_section.find(f'(symbol "{full_name}"')
                if start < 0:
                    continue
                end = find_matching_paren(lib_section, start)
                if end < 0:
                    continue
                block = lib_section[start:end + 1]
                block = block.replace(f'(symbol "{full_name}"', f'(symbol "{symbol_name}"', 1)
                block = "\n".join(line[4:] if line.startswith("    ") else line for line in block.splitlines())
                by_library.setdefault(library, []).append(block)

        if not by_library:
            return {"attempted": True, "success": False, "reason": "no cached library symbols found"}

        symbols_dir = project / "libraries" / "symbols"
        symbols_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for library, blocks in sorted(by_library.items()):
            path = symbols_dir / f"{library}.kicad_sym"
            existing_blocks: list[str] = []
            existing_names: set[str] = set()
            if path.exists():
                try:
                    existing_text = path.read_text(encoding="utf-8-sig")
                    existing_symbols = symbols_in_library(existing_text)
                except Exception:
                    existing_symbols = {}
                for sym_name, _ in existing_symbols.items():
                    start = existing_text.find(f'(symbol "{sym_name}"')
                    if start < 0:
                        continue
                    end = find_matching_paren(existing_text, start)
                    if end < 0:
                        continue
                    existing_names.add(sym_name)
                    existing_blocks.append(existing_text[start:end + 1])
            merged_blocks = list(existing_blocks)
            for block in blocks:
                try:
                    sym_tree = parse_sexpr(block)
                    symbol_name = sym_tree.values[0] if sym_tree.values else ""
                except Exception:
                    symbol_name = ""
                if symbol_name and symbol_name in existing_names:
                    continue
                if symbol_name:
                    existing_names.add(symbol_name)
                merged_blocks.append(block)
            body = "\n\n".join(merged_blocks)
            content = (
                "(kicad_symbol_lib\n"
                "  (version 20251024)\n"
                '  (generator "kicad_symbol_editor")\n'
                '  (generator_version "10.0")\n'
                f"{body}\n"
                ")\n"
            )
            path.write_text(content, encoding="utf-8")
            written.append(str(path))

        return {
            "attempted": True,
            "success": True,
            "libraries": sorted(by_library),
            "written_files": written,
            "count": len(written),
        }

    def sanitize_copied_symbol_libraries(self, project_dir: str | Path) -> dict[str, Any]:
        """Remove invalid converter artifacts from project-local symbol libraries."""
        project = Path(project_dir)
        patched_files: list[str] = []
        symbols_dir = project / "libraries" / "symbols"
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

    def patch_known_jlc_symbol_pin_types(self, project_dir: str | Path) -> dict[str, Any]:
        """Apply narrow ERC pin-type corrections for known EasyEDA/JLC symbol issues."""
        project = Path(project_dir)
        patched_files: list[str] = []
        memory_symbol = project / "libraries" / "symbols" / "JLC-MCP-Memory.kicad_sym"
        mcu_symbol = project / "libraries" / "symbols" / "JLC-MCP-MCUs.kicad_sym"
        schematic_files = list(project.glob("*.kicad_sch"))
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

    def sanitize_generated_schematics(self, project_dir: str | Path) -> dict[str, Any]:
        """Final pass to keep generated schematic lib_symbols parseable by KiCad."""
        project = Path(project_dir)
        patched_files: list[str] = []
        for path in sorted(project.glob("*.kicad_sch")):
            text = path.read_text(encoding="utf-8")
            patched = sanitize_lib_symbols_section(text)
            if patched != text:
                path.write_text(patched, encoding="utf-8")
                patched_files.append(str(path))
        return {"patched_files": patched_files, "count": len(patched_files)}


def _inject_symbols_into_sheet(sch_path: Path, lib_name: str, lib_content: str) -> int:
    """Replace schematic cache stubs for one JLC symbol library."""
    sch = sch_path.read_text(encoding="utf-8")
    lib_start = sch.find("(lib_symbols")
    if lib_start < 0:
        return 0

    lib_end = find_matching_paren(sch, lib_start)
    if lib_end < 0:
        return 0
    lib_section = sch[lib_start:lib_end + 1]

    replaced = 0
    try:
        lib_symbols = symbols_in_library(lib_content)
    except Exception:
        lib_symbols = {}
    for sym_name in lib_symbols:
        if not sym_name or sym_name.endswith("_0_1"):
            continue
        full_lib_id = lib_name + ":" + sym_name
        if '(symbol "' + full_lib_id + '"' not in lib_section:
            continue
        start = lib_content.find(f'(symbol "{sym_name}"')
        if start < 0:
            continue
        end = find_matching_paren(lib_content, start)
        if end < 0:
            continue
        full_def = lib_content[start:end + 1]

        stub_start = lib_section.find('(symbol "' + full_lib_id + '"')
        if stub_start < 0:
            continue
        stub_end = find_matching_paren(lib_section, stub_start)
        if stub_end < 0:
            continue
        old_stub = lib_section[stub_start:stub_end + 1]
        new_content = full_def.replace('(symbol "' + sym_name + '"', '(symbol "' + full_lib_id + '"', 1)
        lib_section = lib_section.replace(old_stub, new_content.strip(), 1)
        replaced += 1

    if replaced > 0:
        sch_path.write_text(sch[:lib_start] + lib_section + sch[lib_end + 1:], encoding="utf-8")
    return replaced


def _find_project_libraries_dir(project_dir: Path) -> Path | None:
    candidates = [
        project_dir / "libraries",
        project_dir.parent.parent / "libraries",
        project_dir.parent / "libraries",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _first_schematic(project_dir: Path) -> Path | None:
    schematics = sorted(project_dir.glob("*.kicad_sch"))
    return schematics[0] if schematics else None
