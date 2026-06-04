"""Project-local KiCad resource helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..shared.env_utils import env, repo_root

REPO_ROOT = repo_root()


def find_jlc_footprint_lib(output_dir: Path) -> Path | None:
    """Find the JLC footprint library directory relative to the project."""
    for candidate in [
        output_dir / "libraries" / "footprints" / "JLC-MCP.pretty",
        output_dir / "libs" / "JLC-MCP.pretty",
        output_dir.parent / "libs" / "JLC-MCP.pretty",
        Path(env("KICAD_SOURCE_PROJECT_DIR", "")) / "libraries" / "footprints" / "JLC-MCP.pretty",
    ]:
        if candidate.exists():
            return candidate
    return None


def find_jlc_symbol_lib(output_dir: Path) -> Path | None:
    """Find the JLC symbol library file relative to the project."""
    for candidate in [
        output_dir / "libraries" / "symbols" / "EasyEDA-local.kicad_sym",
        output_dir / "libs" / "jlc_symbols.kicad_sym",
        output_dir.parent / "libs" / "jlc_symbols.kicad_sym",
        Path(env("KICAD_SOURCE_PROJECT_DIR", "")) / "libraries" / "symbols" / "EasyEDA-local.kicad_sym",
    ]:
        if candidate.exists():
            return candidate
    return None


def write_fp_lib_table(output_dir: Path) -> None:
    """Write fp-lib-table and sym-lib-table with project-relative paths."""
    lines = ["(fp_lib_table", "  (version 7)"]

    repo_fp = REPO_ROOT / "resources" / "kicad" / "footprints"
    if repo_fp.exists():
        for pretty_dir in sorted(repo_fp.glob("*.pretty")):
            lib_name = pretty_dir.name.rsplit(".", 1)[0]
            uri = f"libraries/footprints/{pretty_dir.name}"
            lines.append(
                f'  (lib (name "{lib_name}")(type "KiCad")(uri "{uri}")(options "")(descr "AIAgent custom footprints"))'
            )

    lines.append(
        '  (lib (name "JLC-MCP")(type "KiCad")(uri "libraries/footprints/JLC-MCP.pretty")(options "")(descr "JLC-MCP footprints"))'
    )
    lines.append(")\n")
    (output_dir / "fp-lib-table").write_text("\n".join(lines), encoding="utf-8")
    write_sym_lib_table(output_dir)


def write_sym_lib_table(output_dir: Path) -> None:
    """Write sym-lib-table registering project-local symbol libraries."""
    output_resolved = output_dir.resolve()
    lines = ["(sym_lib_table", "  (version 7)"]
    registered: set[str] = set()

    def _register(sym_dir: Path) -> None:
        if not sym_dir.exists():
            return
        for sym_file in sorted(sym_dir.glob("*.kicad_sym")):
            lib_name = sym_file.stem
            if lib_name in registered:
                continue
            registered.add(lib_name)
            try:
                rel = Path(os.path.relpath(str(sym_file.resolve()), str(output_resolved)))
            except ValueError:
                rel = sym_file
            uri = str(rel).replace("\\", "/")
            lines.append(f'  (lib (name "{lib_name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))')

    _register(output_dir / "libraries" / "symbols")
    workspace = env("KICAD_WORKSPACE", "")
    if workspace:
        _register(Path(workspace) / "libraries" / "symbols")
    _register(REPO_ROOT / "resources" / "kicad" / "symbols")

    lines.append(")\n")
    (output_dir / "sym-lib-table").write_text("\n".join(lines), encoding="utf-8")


def load_project_dsl_sheets(project_path: Path) -> list[dict[str, Any]] | None:
    """Load DSL sheet assignments from the project source model if available."""
    model_file = project_path / "source" / "circuit-model.source.json"
    if not model_file.is_file():
        return None
    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sheets = model.get("sheets", [])
    if isinstance(sheets, list) and sheets:
        return sheets
    return None
