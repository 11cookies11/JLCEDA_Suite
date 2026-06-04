"""Application service for project footprint and library readiness."""

from __future__ import annotations

import json
import locale
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..adapters.kicad_cli import resolve_kicad_cli
from ..adapters.kicad_project_writer import DEFAULT_ERC_PIN_MAP, DEFAULT_ERC_RULE_SEVERITIES
from ..shared.env_utils import env, repo_root


REPO_ROOT = repo_root()


class FootprintResolutionService:
    """Normalize, upgrade, register, and validate project-local footprint assets."""

    def prepare_project_footprints(self, project_dir: str | Path) -> dict[str, Any]:
        project = Path(project_dir)
        return {
            "library_sync": self.sync_source_libraries(project),
            "footprint_sanitization": self.sanitize_footprint_libraries(project),
            "footprint_upgrade": self.upgrade_footprint_libraries(project),
            "library_registration": self.register_jlc_libraries(project),
            "project_library_pins": self.pin_project_libraries(project),
            "gui_asset_validation": self.validate_gui_assets(project),
        }

    def sync_source_libraries(self, project_dir: str | Path) -> dict[str, Any]:
        """Copy pre-imported EasyEDA/JLC assets from the source project into output."""
        project = Path(project_dir)
        source_project = env("KICAD_SOURCE_PROJECT_DIR", "")
        if not source_project:
            return {"attempted": False, "reason": "KICAD_SOURCE_PROJECT_DIR not set"}
        source_libraries = Path(source_project) / "libraries"
        if not source_libraries.exists():
            return {
                "attempted": True,
                "copied": False,
                "reason": "source libraries missing",
                "source": str(source_libraries),
            }

        target_libraries = project / "libraries"
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

        return {
            "attempted": True,
            "copied": True,
            "source": str(source_libraries),
            "target": str(target_libraries),
            "counts": counts,
        }

    def sanitize_footprint_libraries(self, project_dir: str | Path) -> dict[str, Any]:
        """Normalize copied footprint files so KiCad GUI can enumerate the library."""
        project = Path(project_dir)
        patched_files: list[str] = []
        footprints_dir = project / "libraries" / "footprints"
        if not footprints_dir.exists():
            return {"patched_files": patched_files, "count": 0}

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
                path.write_text(patched, encoding="utf-8")
                patched_files.append(str(path))

        return {"patched_files": patched_files, "count": len(patched_files)}

    def upgrade_footprint_libraries(self, project_dir: str | Path) -> dict[str, Any]:
        """Best-effort KiCad CLI footprint library upgrade for copied local libs."""
        project = Path(project_dir)
        footprints_dir = project / "libraries" / "footprints"
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
            results.append({
                "library": str(pretty_dir),
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "stdout": process.stdout.replace("\ufffd", ""),
                "stderr": process.stderr.replace("\ufffd", ""),
            })

        return {
            "attempted": True,
            "success": all(item["success"] for item in results),
            "executable": executable,
            "results": results,
        }

    def register_jlc_libraries(self, project_dir: str | Path) -> dict[str, Any]:
        """Register JLC-MCP libraries after schematic generation."""
        project = Path(project_dir)
        install_script = str(repo_root() / "scripts" / "install_jlc_mcp_parts.py")
        try:
            process = subprocess.run(
                [sys.executable, install_script, "--project-dir", str(project), "--register-only"],
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

    def pin_project_libraries(self, project_dir: str | Path) -> dict[str, Any]:
        """Ensure KiCad project JSON pins project-local symbol and footprint libraries."""
        project = Path(project_dir)
        project_files = sorted(project.glob("*.kicad_pro"))
        if not project_files:
            return {"attempted": True, "success": False, "reason": "no .kicad_pro found"}

        project_file = project_files[0]
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"attempted": True, "success": False, "project": str(project_file), "reason": str(exc)}

        proj_libs = _find_project_libraries_dir(project)
        sym_table_entries: list[tuple[str, str]] = []
        fp_table_entries: list[tuple[str, str]] = []
        pinned_symbols: list[dict[str, Any]] = []
        pinned_footprints: list[dict[str, Any]] = []
        project_resolved = project.resolve()

        def _project_uri(path: Path) -> str:
            try:
                return path.resolve().relative_to(project_resolved).as_posix()
            except ValueError:
                return path.resolve().as_posix()

        if proj_libs:
            symbols_dir = proj_libs / "symbols"
            if symbols_dir.is_dir():
                for sym_file in sorted(symbols_dir.glob("*.kicad_sym")):
                    uri = _project_uri(sym_file)
                    name = sym_file.stem
                    sym_table_entries.append((name, uri))
                    pinned_symbols.append({
                        "name": name,
                        "type": "KiCad",
                        "uri": uri,
                        "options": "",
                        "description": f"JLC-MCP {name}",
                    })

            footprints_dir = proj_libs / "footprints"
            if footprints_dir.is_dir():
                for pretty_dir in sorted(footprints_dir.glob("*.pretty")):
                    uri = _project_uri(pretty_dir)
                    name = pretty_dir.stem
                    fp_table_entries.append((name, uri))
                    pinned_footprints.append({
                        "name": name,
                        "type": "KiCad",
                        "uri": uri,
                        "options": "",
                        "description": "JLC-MCP footprints",
                    })

        ref_libs = _scan_schematic_libraries(project)
        system_sym_dir = _find_kicad_system_symbol_dir()
        for lib_name in sorted(ref_libs):
            if lib_name not in dict(sym_table_entries) and system_sym_dir:
                sym_file = system_sym_dir / f"{lib_name}.kicad_sym"
                if sym_file.is_file():
                    sym_table_entries.append((lib_name, sym_file.as_posix()))

        sym_table_path = _write_sym_lib_table(project, sym_table_entries) if sym_table_entries else None
        fp_table_path = _write_fp_lib_table(project, fp_table_entries) if fp_table_entries else None
        if not sym_table_entries and project.joinpath("sym-lib-table").exists():
            project.joinpath("sym-lib-table").unlink()

        data["libraries"] = {
            "pinned_footprint_libs": pinned_footprints,
            "pinned_symbol_libs": pinned_symbols,
        }
        data.setdefault("erc", {
            "erc_exclusions": [],
            "meta": {"version": 0},
            "pin_map": DEFAULT_ERC_PIN_MAP,
            "rule_severities": DEFAULT_ERC_RULE_SEVERITIES,
        })
        project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return {
            "attempted": True,
            "success": True,
            "project": str(project_file),
            "proj_libs": str(proj_libs) if proj_libs else None,
            "sym_lib_table": str(sym_table_path) if sym_table_path else None,
            "fp_lib_table": str(fp_table_path) if fp_table_path else None,
            "pinned_symbol_libs": len(pinned_symbols),
            "pinned_footprint_libs": len(pinned_footprints),
            "system_library_refs": sorted(ref_libs),
        }

    def validate_gui_assets(self, project_dir: str | Path) -> dict[str, Any]:
        """Check assets KiCad GUI needs for update-PCB and 3D viewer workflows."""
        project = Path(project_dir)
        issues: list[str] = []
        symbol_bom_files: list[str] = []
        missing_models: list[str] = []

        symbols_dir = project / "libraries" / "symbols"
        if symbols_dir.exists():
            for path in sorted(symbols_dir.glob("*.kicad_sym")):
                raw = path.read_bytes()
                if raw.startswith(b"\xef\xbb\xbf"):
                    symbol_bom_files.append(str(path))
                if raw[:1] != b"(":
                    issues.append(f"symbol library does not start with '(' after sanitization: {path}")

        fp_table = project / "fp-lib-table"
        if not fp_table.exists():
            issues.append("missing project fp-lib-table")
        else:
            table_text = fp_table.read_text(encoding="utf-8", errors="replace")
            if 'name "JLC-MCP"' not in table_text:
                issues.append("project fp-lib-table does not register JLC-MCP")

        footprint_upgrade = self.upgrade_footprint_libraries(project)
        if footprint_upgrade.get("attempted") and not footprint_upgrade.get("success", False):
            issues.append("kicad-cli could not load/upgrade at least one footprint library")

        model_pattern = re.compile(r'\(model\s+"([^"]+)"')
        for footprint in sorted((project / "libraries" / "footprints").glob("*.pretty/*.kicad_mod")):
            text = footprint.read_text(encoding="utf-8", errors="replace")
            for match in model_pattern.finditer(text):
                model_path = match.group(1)
                resolved = Path(model_path)
                if not resolved.is_absolute():
                    resolved = project / model_path
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


def _write_sym_lib_table(project_dir: Path, symbol_uris: list[tuple[str, str]]) -> Path:
    lines = ["(sym_lib_table", "  (version 7)"]
    for name, uri in symbol_uris:
        lines.append(f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))')
    lines.append(")")
    table_path = project_dir / "sym-lib-table"
    table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return table_path


def _write_fp_lib_table(project_dir: Path, fp_uris: list[tuple[str, str]]) -> Path:
    lines = ["(fp_lib_table", "  (version 7)"]
    for name, uri in fp_uris:
        lines.append(f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))')
    lines.append(")")
    table_path = project_dir / "fp-lib-table"
    table_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return table_path


def _find_kicad_system_symbol_dir() -> Path | None:
    candidates = [
        Path("D:/Program Files/KiCad/10.0/share/kicad/symbols"),
        Path("C:/Program Files/KiCad/10.0/share/kicad/symbols"),
        Path("/usr/share/kicad/symbols"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _scan_schematic_libraries(project_dir: Path) -> set[str]:
    lib_names: set[str] = set()
    for sch_file in project_dir.glob("*.kicad_sch"):
        text = sch_file.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'\(symbol\s+"([^"]+):', text):
            lib_names.add(match.group(1))
    return lib_names


def _sanitize_kicad_text_line(line: str) -> str:
    if "(property " not in line:
        return line
    if line.count('"') >= 4:
        return line
    match = re.match(r'^(\s*\(property\s+"[^"]+")', line)
    if not match:
        return line
    return f'{match.group(1)} "sanitized"'
