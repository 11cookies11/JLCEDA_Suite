"""Generate KiCad PCB boards from execution plans."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .kicad_cli import resolve_kicad_cli
from ..shared.env_utils import is_truthy_env


def _resolve_kicad_python() -> str:
    explicit = os.environ.get("KICAD_PYTHON_BIN", "")
    if explicit:
        return explicit
    cli = resolve_kicad_cli()
    if cli:
        candidate = Path(cli).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return ""


def generate_board_from_plan(
    plan_file: str,
    project_dir: Path,
    source_project_dir: str | Path | None = None,
) -> dict[str, Any]:
    if not is_truthy_env("KICAD_GENERATE_PCB", "true"):
        return {"attempted": False, "enabled": False}
    python_bin = _resolve_kicad_python()
    if not python_bin:
        return {
            "attempted": True,
            "success": False,
            "warnings": ["KiCad Python was not found; PCB was not generated."],
        }
    from .pcb_generator import _BOARD_SCRIPT

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as temp_script:
        temp_script.write(_BOARD_SCRIPT)
        script = temp_script.name
    try:
        board_file = project_dir / f"{project_dir.name}.kicad_pcb"
        source_project_arg = str(source_project_dir or "")
        process = subprocess.run(
            [python_bin, script, plan_file, str(board_file), source_project_arg],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    finally:
        try:
            Path(script).unlink()
        except OSError:
            pass
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(process.stdout)
    except Exception:
        payload = {}
    warnings: list[str] = []
    if process.stderr:
        warnings.append(process.stderr.strip())
    if process.returncode != 0:
        warnings.append(process.stdout.strip() or "PCB generation failed.")
    if payload.get("skipped"):
        warnings.extend(str(item) for item in payload.get("skipped", []))
    return {
        "attempted": True,
        "success": process.returncode == 0,
        "return_code": process.returncode,
        "python": python_bin,
        "board_file": payload.get("board", str(board_file)),
        "footprints": int(payload.get("footprints", 0) or 0),
        "nets": int(payload.get("nets", 0) or 0),
        "warnings": warnings,
    }
