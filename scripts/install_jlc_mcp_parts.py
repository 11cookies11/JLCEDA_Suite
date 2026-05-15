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
    try:
        rel = target.resolve().relative_to(project_dir.resolve())
        return "${KIPRJMOD}/" + rel.as_posix()
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
        '  (lib (name "AIAgent")(type "KiCad")(uri "${KIPRJMOD}/../../../resources/kicad/footprints/AIAgent.pretty")(options "")(descr "AIAgent custom footprints"))'
    ]
    if footprints_dir.exists():
        uri = _project_uri(project_dir, footprints_dir)
        fp_entries.append(
            f'  (lib (name "JLC-MCP")(type "KiCad")(uri "{uri}")(options "")(descr "JLC-MCP footprints"))'
        )
    fp_lines = ["(fp_lib_table", *fp_entries, ")"]
    (project_dir / "fp-lib-table").write_text("\n".join(fp_lines) + "\n", encoding="utf-8")

    return {
        "symbol_lib_count": len(symbol_libs),
        "symbol_libs": [path.stem for path in symbol_libs],
        "footprint_lib_registered": footprints_dir.exists(),
        "sym_lib_table": str(project_dir / "sym-lib-table") if symbol_libs else "",
        "fp_lib_table": str(project_dir / "fp-lib-table"),
    }


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
        report = {
            "ok": True,
            "project_dir": str(project_dir),
            "register_only": True,
            "library_tables": lib_tables,
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
        "results": results,
    }

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    output_path = Path(output_raw) if output_raw else project_dir / "jlc-mcp-install-report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
