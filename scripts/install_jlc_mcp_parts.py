"""Install selected LCSC parts through the repository JLC MCP bridge.

Usage:
  python scripts/install_jlc_mcp_parts.py --selections selections.json --project-dir .where/my-project
  python scripts/install_jlc_mcp_parts.py --selections selections.json --project-dir .where/my-project --include-review --include-3d
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _insert_before_table_end(content: str, entry: str) -> str:
    """Insert a KiCad library-table entry before the table's final closing paren."""
    index = content.rfind(")")
    if index < 0:
        return content.rstrip() + "\n" + entry + ")\n"
    return content[:index].rstrip() + "\n" + entry + content[index:]


def _arg_value(name: str) -> str:
    for idx, arg in enumerate(sys.argv):
        if arg == name and idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return ""


def _has_flag(name: str) -> bool:
    return name in sys.argv


def _selected_entries(data: list[dict[str, Any]], *, include_review: bool) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        selected = item.get("selected")
        if not isinstance(selected, dict):
            continue
        lcsc_id = str(selected.get("lcsc_id", ""))
        if not lcsc_id or lcsc_id in seen:
            continue
        if selected.get("needs_review") and not include_review:
            continue
        seen.add(lcsc_id)
        entries.append({
            "requirement_id": item.get("requirement_id", ""),
            "lcsc_id": lcsc_id,
            "mpn": selected.get("mpn", ""),
            "needs_review": bool(selected.get("needs_review", False)),
        })
    return entries


def _run_install(
    bridge_script: Path,
    entry: dict[str, Any],
    project_dir: Path,
    *,
    include_3d: bool,
    force: bool,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    command = [
        "node",
        str(bridge_script),
        "install",
        "--id",
        str(entry["lcsc_id"]),
        "--project-path",
        str(project_dir),
    ]
    if include_3d:
        command.append("--include-3d")
    if force:
        command.append("--force")

    last_result: dict[str, Any] | None = None
    for attempt in range(max(retries, 0) + 1):
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_result = {
                **entry,
                "ok": False,
                "attempt": attempt + 1,
                "error": str(exc),
            }
            continue

        payload: object
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"stdout": proc.stdout, "stderr": proc.stderr}

        ok = proc.returncode == 0 and isinstance(payload, dict) and bool(payload.get("ok", False))
        last_result = {
            **entry,
            "ok": ok,
            "attempt": attempt + 1,
            "returncode": proc.returncode,
            "result": payload,
            "stderr": proc.stderr,
        }
        if ok:
            return last_result

    if _installed_asset_exists(project_dir, str(entry["lcsc_id"])):
        return {
            **entry,
            "ok": True,
            "installed_existing": True,
            "warning": "Install command failed, but project-local JLC MCP assets already contain this LCSC ID.",
            "last_result": last_result,
        }
    return last_result or {**entry, "ok": False, "error": "Install command did not return a result."}


def _installed_asset_exists(project_dir: Path, lcsc_id: str) -> bool:
    libraries = project_dir / "libraries"
    if not libraries.exists():
        return False
    for path in libraries.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".kicad_sym", ".kicad_mod"}:
            continue
        try:
            if lcsc_id in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _project_uri(project_dir: Path, target: Path) -> str:
    """Return a project-relative URI for portable KiCad project library tables."""
    try:
        relative = target.resolve().relative_to(project_dir.resolve())
        return relative.as_posix()
    except ValueError:
        return target.resolve().as_posix()


def _write_project_lib_tables(project_dir: Path) -> dict[str, Any]:
    libraries = project_dir / "libraries"
    symbols_dir = libraries / "symbols"
    footprints_dir = libraries / "footprints" / "JLC-MCP.pretty"

    symbol_libs = sorted(symbols_dir.glob("*.kicad_sym")) if symbols_dir.exists() else []
    sym_lines = ["(sym_lib_table", "  (version 7)"]
    for sym_file in symbol_libs:
        name = sym_file.stem
        uri = _project_uri(project_dir, sym_file)
        sym_lines.append(
            f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr "JLC-MCP {name}"))'
        )
    sym_lines.append(")")
    if symbol_libs:
        (project_dir / "sym-lib-table").write_text("\n".join(sym_lines) + "\n", encoding="utf-8")

    fp_entries = [
        '  (lib (name "AIAgent")(type "KiCad")(uri "../../../resources/kicad/footprints/AIAgent.pretty")(options "")(descr "AIAgent custom footprints"))'
    ]
    if footprints_dir.exists():
        uri = _project_uri(project_dir, footprints_dir)
        fp_entries.append(
            f'  (lib (name "JLC-MCP")(type "KiCad")(uri "{uri}")(options "")(descr "JLC-MCP footprints"))'
        )
    fp_lines = ["(fp_lib_table", "  (version 7)", *fp_entries, ")"]
    (project_dir / "fp-lib-table").write_text("\n".join(fp_lines) + "\n", encoding="utf-8")

    return {
        "symbol_lib_count": len(symbol_libs),
        "symbol_libs": [path.stem for path in symbol_libs],
        "footprint_lib_registered": footprints_dir.exists(),
        "sym_lib_table": str(project_dir / "sym-lib-table") if symbol_libs else "",
        "fp_lib_table": str(project_dir / "fp-lib-table"),
    }


def _fix_3d_model_paths(project_dir: Path) -> dict[str, Any]:
    """Normalize JLC MCP 3D model paths in copied footprints.

    The generator may leave footprints pointing at old absolute paths, temporary
    easyeda2kicad folders, or legacy KiCad 9 third-party variables. Rewrite any
    .3dshapes reference to the current project's 3dmodels directory so KiCad 10
    can resolve them reliably.
    """
    import re
    model_dir = (project_dir / "libraries" / "3dmodels" / "JLC-MCP.3dshapes").resolve()
    fp_dir = project_dir / "libraries" / "footprints" / "JLC-MCP.pretty"
    if not fp_dir.exists():
        return {"fixed": 0, "footprint_dir_missing": True}

    new_prefix = model_dir.as_posix() + "/"
    fixed = 0
    for fp_file in fp_dir.glob("*.kicad_mod"):
        content = fp_file.read_text(encoding="utf-8", errors="replace")
        patched = re.sub(
            r'(\(model\s+")([^"]*?[\\/][^"\\/]+\.3dshapes[\\/])([^"\\]+)(")',
            rf'\1{new_prefix}\3\4',
            content,
            flags=re.DOTALL,
        )
        patched = patched.replace("${KICAD9_3RD_PARTY}/jlc_mcp/3dmodels/JLC-MCP.3dshapes/", new_prefix)
        if patched != content:
            fp_file.write_text(patched, encoding="utf-8")
            fixed += 1

    return {"fixed": fixed, "model_dir": str(model_dir)}


def _register_global_libraries(project_dir: Path) -> dict[str, Any]:
    """Copy JLC-MCP symbols and footprints to KiCad global library directory.

    KiCad 10.0 does not reliably load project-level sym-lib-table / fp-lib-table.
    Copying to the global KiCad library directory and registering in the global
    table ensures symbols, footprints, and 3D models are always available.
    """
    import shutil
    home = Path.home()
    kicad_global = home / "AppData" / "Roaming" / "kicad" / "10.0"
    global_libs = kicad_global / "libraries"

    result: dict[str, Any] = {"global_lib_dir": str(global_libs)}

    # Copy symbol libraries
    symbols_dir = project_dir / "libraries" / "symbols"
    if symbols_dir.exists():
        global_libs.mkdir(parents=True, exist_ok=True)
        for sym_file in symbols_dir.glob("JLC-MCP-*.kicad_sym"):
            shutil.copy2(sym_file, global_libs / sym_file.name)
        result["symbols_copied"] = len(list(symbols_dir.glob("JLC-MCP-*.kicad_sym")))

    # Copy footprint libraries
    fp_dir = project_dir / "libraries" / "footprints" / "JLC-MCP.pretty"
    if fp_dir.exists():
        global_fp = global_libs / "JLC-MCP.pretty"
        if global_fp.exists():
            shutil.rmtree(global_fp)
        shutil.copytree(fp_dir, global_fp)
        result["footprints_copied"] = len(list(global_fp.glob("*.kicad_mod")))

    # Copy 3D models
    model_dir = project_dir / "libraries" / "3dmodels" / "JLC-MCP.3dshapes"
    if model_dir.exists():
        global_3d = global_libs / "JLC-MCP.3dshapes"
        global_3d.mkdir(parents=True, exist_ok=True)
        for step_file in model_dir.glob("*.step"):
            shutil.copy2(step_file, global_3d / step_file.name)
        result["models_copied"] = len(list(model_dir.glob("*.step")))

    # Update global sym-lib-table
    sym_table_path = kicad_global / "sym-lib-table"
    if sym_table_path.exists():
        content = sym_table_path.read_text(encoding="utf-8")
        for sym_file in sorted((global_libs).glob("JLC-MCP-*.kicad_sym")):
            name = sym_file.stem
            uri = sym_file.resolve().as_posix()
            entry = f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr "JLC-MCP {name}"))\n'
            if name not in content:
                content = _insert_before_table_end(content, entry)
        sym_table_path.write_text(content, encoding="utf-8")
        result["sym_table_updated"] = True

    # Update global fp-lib-table
    fp_table_path = kicad_global / "fp-lib-table"
    if fp_table_path.exists():
        content = fp_table_path.read_text(encoding="utf-8")
        if "JLC-MCP" not in content:
            uri = (global_libs / "JLC-MCP.pretty").resolve().as_posix()
            entry = f'  (lib (name "JLC-MCP")(type "KiCad")(uri "{uri}")(options "")(descr "JLC-MCP footprints (EasyEDA origin)"))\n'
            content = _insert_before_table_end(content, entry)
            fp_table_path.write_text(content, encoding="utf-8")
        result["fp_table_updated"] = True

    return result


def main() -> None:
    selections_file = _arg_value("--selections")
    project_dir_raw = _arg_value("--project-dir")
    output_raw = _arg_value("--output")
    include_review = _has_flag("--include-review")
    include_3d = _has_flag("--include-3d")
    force = _has_flag("--force")
    register_only = _has_flag("--register-only")
    timeout = float(_arg_value("--timeout") or os.environ.get("JLC_MCP_INSTALL_TIMEOUT_SEC", "120"))
    retries = int(_arg_value("--retries") or os.environ.get("JLC_MCP_INSTALL_RETRIES", "1"))

    if (not selections_file and not register_only) or not project_dir_raw:
        print(__doc__.strip())
        sys.exit(2)

    selections_path = Path(selections_file)
    project_dir = Path(project_dir_raw)
    bridge_script = Path(__file__).resolve().parent / "jlc_mcp_bridge.mjs"

    if register_only:
        lib_tables = _write_project_lib_tables(project_dir)
        model_fix = _fix_3d_model_paths(project_dir)
        global_reg = _register_global_libraries(project_dir)
        report = {
            "ok": True,
            "project_dir": str(project_dir),
            "register_only": True,
            "library_tables": lib_tables,
            "3d_path_fix": model_fix,
            "global_registration": global_reg,
        }
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        output_path = Path(output_raw) if output_raw else project_dir / "jlc-mcp-install-report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return

    data = json.loads(selections_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Selections JSON must be a list.")

    project_dir.mkdir(parents=True, exist_ok=True)
    entries = _selected_entries(data, include_review=include_review)

    results = [
        _run_install(
            bridge_script,
            entry,
            project_dir,
            include_3d=include_3d,
            force=force,
            timeout=timeout,
            retries=retries,
        )
        for entry in entries
    ]

    lib_tables = _write_project_lib_tables(project_dir)
    model_fix = _fix_3d_model_paths(project_dir)
    global_reg = _register_global_libraries(project_dir)

    report = {
        "ok": all(item.get("ok") for item in results) if results else True,
        "project_dir": str(project_dir),
        "include_review": include_review,
        "include_3d": include_3d,
        "retries": retries,
        "requested_count": len(entries),
        "installed_count": sum(1 for item in results if item.get("ok")),
        "failed_count": sum(1 for item in results if not item.get("ok")),
        "library_tables": lib_tables,
        "3d_path_fix": model_fix,
        "global_registration": global_reg,
        "results": results,
    }

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    output_path = Path(output_raw) if output_raw else project_dir / "jlc-mcp-install-report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
