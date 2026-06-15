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
            "model_path_normalization": self.normalize_3d_model_paths(project),
            "library_registration": self.register_jlc_libraries(project),
            "project_library_pins": self.pin_project_libraries(project),
            "gui_asset_validation": self.validate_gui_assets(project, normalize=False),
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

    def normalize_3d_model_paths(self, project_dir: str | Path) -> dict[str, Any]:
        """Rewrite project-local 3D model references to stable ${KIPRJMOD} paths."""
        project = Path(project_dir)
        footprints_dir = project / "libraries" / "footprints"
        changed_files: list[str] = []
        updated_references = 0
        unresolved_references: list[str] = []

        if not footprints_dir.exists():
            return {
                "attempted": False,
                "reason": "no project-local footprint libraries",
                "changed_files": changed_files,
                "updated_references": updated_references,
                "unresolved_references": unresolved_references,
            }

        pcb_files = sorted(project.glob("*.kicad_pcb"))
        for path in [*sorted(footprints_dir.glob("*.pretty/*.kicad_mod")), *pcb_files]:
            original = path.read_text(encoding="utf-8", errors="replace")
            rewritten, delta, unresolved, changed = _rewrite_3d_model_paths(project, original)
            if changed:
                path.write_text(rewritten, encoding="utf-8")
                changed_files.append(str(path))
                updated_references += delta
            unresolved_references.extend(f"{path.name}: {item}" for item in unresolved)

        return {
            "attempted": True,
            "success": not unresolved_references,
            "changed_files": changed_files,
            "updated_references": updated_references,
            "unresolved_references": unresolved_references,
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

    def validate_gui_assets(self, project_dir: str | Path, *, normalize: bool = True) -> dict[str, Any]:
        """Check assets KiCad GUI needs for update-PCB and 3D viewer workflows."""
        project = Path(project_dir)
        issues: list[str] = []
        symbol_bom_files: list[str] = []
        missing_models: list[str] = []
        non_project_model_refs: list[str] = []

        normalization = self.normalize_3d_model_paths(project) if normalize else {
            "attempted": False,
            "changed_files": [],
            "updated_references": 0,
            "unresolved_references": [],
        }

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

        model_pattern = re.compile(r'\(model\s+"([^"]+)"')
        model_sources = [
            *sorted((project / "libraries" / "footprints").glob("*.pretty/*.kicad_mod")),
            *sorted(project.glob("*.kicad_pcb")),
        ]
        for model_source in model_sources:
            text = model_source.read_text(encoding="utf-8", errors="replace")
            for match in model_pattern.finditer(text):
                model_path = match.group(1)
                resolved = _resolve_3d_model_reference(project, model_path)
                if not model_path.startswith("${KIPRJMOD}/"):
                    non_project_model_refs.append(f"{model_source.name}: {model_path}")
                if resolved is None:
                    missing_models.append(f"{model_source.name}: {model_path}")

        if symbol_bom_files:
            issues.append(f"symbol libraries still contain UTF-8 BOM: {len(symbol_bom_files)}")
        if normalization.get("unresolved_references"):
            missing_models.extend(str(item) for item in normalization["unresolved_references"])
        if non_project_model_refs:
            issues.append(f"non-project 3D model references: {len(non_project_model_refs)}")
        if missing_models:
            issues.append(f"missing 3D model references: {len(missing_models)}")

        return {
            "attempted": True,
            "success": not issues,
            "issues": issues,
            "normalization": normalization,
            "symbol_bom_files": symbol_bom_files,
            "missing_models": missing_models,
            "non_project_model_refs": non_project_model_refs,
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


def _known_system_3dmodel_dirs() -> list[Path]:
    candidates = [
        Path("D:/Program Files/KiCad/10.0/share/kicad/3dmodels"),
        Path("C:/Program Files/KiCad/10.0/share/kicad/3dmodels"),
        Path("D:/Program Files/KiCad/9.0/share/kicad/3dmodels"),
        Path("C:/Program Files/KiCad/9.0/share/kicad/3dmodels"),
        Path("/usr/share/kicad/3dmodels"),
    ]
    return [candidate for candidate in candidates if candidate.is_dir()]


def _resolve_3d_model_reference(project_dir: Path, model_path: str) -> tuple[Path | None, Path | None]:
    text = model_path.strip()
    if not text:
        return None, None

    project_root = project_dir.resolve()
    normalized = text
    if normalized.startswith("${KIPRJMOD}/"):
        candidate = project_root / normalized.removeprefix("${KIPRJMOD}/")
        return (candidate, project_root) if candidate.exists() else (None, None)

    candidate = Path(normalized)
    if candidate.is_absolute():
        if candidate.exists():
            try:
                candidate.resolve().relative_to(project_root)
            except ValueError:
                return candidate, None
            return candidate, project_root

    candidate = project_root / normalized.lstrip("/")
    if candidate.exists():
        return candidate, project_root

    model_root = project_root / "libraries" / "3dmodels"
    basename = Path(normalized).name
    if basename:
        for match in sorted(model_root.glob(f"**/{basename}")):
            if match.is_file():
                return match, project_root
        stem = Path(basename).stem
        if stem:
            for match in sorted(model_root.glob(f"**/{stem}.*")):
                if match.is_file():
                    return match, project_root

    for system_root in _known_system_3dmodel_dirs():
        if basename:
            for match in sorted(system_root.glob(f"**/{basename}")):
                if match.is_file():
                    return match, system_root
            if stem:
                for match in sorted(system_root.glob(f"**/{stem}.*")):
                    if match.is_file():
                        return match, system_root

    return None, None


def _rewrite_3d_model_paths(project_dir: Path, text: str) -> tuple[str, int, list[str], bool]:
    pattern = re.compile(r'(\n?\s*\(model\s+")([^"]+)(".*?\n\s*\)\s*\))', re.DOTALL)
    unresolved: list[str] = []
    updates = 0
    changed = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal updates, changed
        original = match.group(2)
        resolved, source_root = _resolve_3d_model_reference(project_dir, original)
        if resolved is None:
            unresolved.append(original)
            changed = True
            return ""
        if source_root is None:
            try:
                relative = resolved.resolve().relative_to(project_dir.resolve()).as_posix()
            except ValueError:
                unresolved.append(original)
                changed = True
                return ""
        else:
            if source_root != project_dir.resolve():
                relative_to_source = resolved.resolve().relative_to(source_root.resolve())
                target = project_dir.resolve() / "libraries" / "3dmodels" / relative_to_source
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(resolved, target)
                resolved = target
            try:
                relative = resolved.resolve().relative_to(project_dir.resolve()).as_posix()
            except ValueError:
                relative = resolved.as_posix()
        rewritten = f"${{KIPRJMOD}}/{relative}"
        if rewritten != original:
            updates += 1
            changed = True
        return f'{match.group(1)}{rewritten}{match.group(3)}'

    rewritten = pattern.sub(_replace, text)
    return rewritten, updates, unresolved, changed


def _sanitize_kicad_text_line(line: str) -> str:
    if "(property " not in line:
        return line
    if line.count('"') >= 4:
        return line
    match = re.match(r'^(\s*\(property\s+"[^"]+")', line)
    if not match:
        return line
    return f'{match.group(1)} "sanitized"'
