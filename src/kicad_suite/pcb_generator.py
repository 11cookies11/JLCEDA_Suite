"""Generate a .kicad_pcb board file from the KiCad execution plan via pcbnew."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _kicad_python() -> str | None:
    explicit = os.environ.get("KICAD_PYTHON_BIN", "")
    if explicit and Path(explicit).exists():
        return explicit
    cli = os.environ.get("KICAD_CLI", "")
    if not cli:
        for candidate in [
            r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
            r"D:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
        ]:
            if Path(candidate).exists():
                cli = candidate
                break
    if cli:
        py = str(Path(cli).with_name("python.exe"))
        if Path(py).exists():
            return py
    return None


def _board_script() -> Path:
    """Locate the generate_pcb_from_plan.py helper script."""
    env_root = os.environ.get("KICAD_AGENT_SUITE_ROOT", "")
    if env_root:
        p = Path(env_root) / "scripts" / "generate_pcb_from_plan.py"
        if p.is_file():
            return p
    for base in [
        Path(__file__).resolve().parents[2],
        Path.cwd(),
        Path.cwd().parent,
    ]:
        p = base / "scripts" / "generate_pcb_from_plan.py"
        if p.is_file():
            return p
    raise FileNotFoundError(
        "Cannot find scripts/generate_pcb_from_plan.py. "
        "Set KICAD_AGENT_SUITE_ROOT to the repository root."
    )


def generate_pcb(plan: dict[str, Any], project_path: str | Path | None = None) -> dict[str, Any]:
    """Create a ``.kicad_pcb`` file via KiCad pcbnew."""
    target = plan.get("target", {})
    if not isinstance(target, dict):
        return {"ok": False, "error": "plan has no target"}
    output_dir = Path(str(target.get("output_dir", ".")))
    project_name = str(target.get("project_name", "kicad_project"))
    board_file = output_dir / (project_name + ".kicad_pcb")

    python_bin = _kicad_python()
    if not python_bin:
        return {
            "ok": False,
            "error": (
                "KiCad Python not found. Set KICAD_PYTHON_BIN env var "
                'e.g. KICAD_PYTHON_BIN="D:/Program Files/KiCad/10.0/bin/python.exe"'
            ),
        }

    script = _board_script()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(plan, f)
        plan_file = f.name

    try:
        proc = subprocess.run(
            [python_bin, str(script), plan_file, str(board_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    finally:
        try:
            Path(plan_file).unlink()
        except OSError:
            pass

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "PCB generation failed",
            "stderr": proc.stderr.strip(),
            "stdout": proc.stdout.strip(),
        }

    result: dict[str, Any] = {"ok": True, "board_file": str(board_file)}
    try:
        payload = json.loads(proc.stdout)
        result.update(payload)
    except json.JSONDecodeError:
        result["raw_output"] = proc.stdout
    result.setdefault("ok", True)
    return result
