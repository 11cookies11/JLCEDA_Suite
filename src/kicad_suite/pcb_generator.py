"""Generate a .kicad_pcb board file from the KiCad execution plan via pcbnew."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# The generate_pcb_from_plan.py script, embedded so it doesn't need to be
# distributed separately.  Written to a temp file and executed by KiCad's
# bundled Python (which has the pcbnew module).
_BOARD_SCRIPT = r'''
import json, re, sys
from pathlib import Path
from typing import Any
import pcbnew

def _footprint_library_dir(project_dir: Path, lib_name: str) -> Path | None:
    if lib_name == "JLC-MCP":
        for base in [project_dir, project_dir.parent, project_dir.parent.parent]:
            candidate = base / "libraries" / "footprints" / "JLC-MCP.pretty"
            if candidate.is_dir():
                return candidate
        return None
    if lib_name == "AIAgent":
        for base in [project_dir, project_dir.parent, project_dir.parent.parent]:
            candidate = base / "resources" / "kicad" / "footprints" / "AIAgent.pretty"
            if candidate.is_dir():
                return candidate
        return None
    return None

def _pin_tokens(pin_number: str) -> set[str]:
    text = str(pin_number).strip()
    if not text:
        return set()
    tokens = set(re.findall(r"[A-Za-z]+\d+|\d+", text))
    tokens.add(text)
    return tokens

def _pad_net_map(symbol: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pin in symbol.get("pins", []):
        if not isinstance(pin, dict):
            continue
        net = str(pin.get("net", "")).strip()
        if not net:
            continue
        for token in _pin_tokens(str(pin.get("number", ""))):
            mapping[token] = net
    return mapping

def _net(board, nets, net_name):
    if net_name not in nets:
        item = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(item)
        nets[net_name] = item
    return nets[net_name]

def generate_board(plan_path, output_path):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    project_dir = Path(output_path).parent
    board = pcbnew.BOARD()
    nets = {}
    loaded = 0
    skipped = []

    for index, symbol in enumerate(plan.get("symbols", [])):
        if not isinstance(symbol, dict):
            continue
        ref = str(symbol.get("ref", "")).strip()
        footprint = str(symbol.get("footprint", "")).strip()
        if not ref or ":" not in footprint:
            skipped.append(f"{ref or '<unknown>'}: no footprint")
            continue
        lib_name, footprint_name = footprint.split(":", 1)
        lib_dir = _footprint_library_dir(project_dir, lib_name)
        if lib_dir is None or not lib_dir.exists():
            skipped.append(f"{ref}: footprint library not found: {footprint}")
            continue
        fp = pcbnew.FootprintLoad(str(lib_dir), footprint_name)
        if fp is None:
            skipped.append(f"{ref}: footprint not found: {footprint}")
            continue

        fp.SetReference(ref)
        fp.SetValue(str(symbol.get("value", "")))
        at = symbol.get("at", {}) if isinstance(symbol.get("at"), dict) else {}
        x_mm = float(at.get("x", 0.0)) + (index % 8) * 6.0
        y_mm = float(at.get("y", 0.0)) + (index // 8) * 6.0
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
        fp.SetOrientationDegrees(float(at.get("rotation", 0.0)))

        pad_map = _pad_net_map(symbol)
        for pad in fp.Pads():
            net_name = pad_map.get(str(pad.GetNumber()).strip())
            if net_name:
                pad.SetNet(_net(board, nets, net_name))
        board.Add(fp)
        loaded += 1

    board.BuildListOfNets()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)
    return {"board": str(output_path), "footprints": loaded, "nets": len(nets), "skipped": skipped}

if __name__ == "__main__":
    print(json.dumps(generate_board(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
'''


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


def generate_pcb(plan: dict[str, Any], project_path: str | Path | None = None) -> dict[str, Any]:
    """Create a ``.kicad_pcb`` file via KiCad pcbnew.

    Writes the plan to a temp file and runs the embedded board-generation
    script under KiCad's bundled Python (which has ``pcbnew``).
    """
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

    # Write the embedded script to a temp file so KiCad's Python can run it
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as sf:
        sf.write(_BOARD_SCRIPT)
        script_file = sf.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as pf:
        json.dump(plan, pf)
        plan_file = pf.name

    try:
        proc = subprocess.run(
            [python_bin, script_file, plan_file, str(board_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    finally:
        for tmp in [plan_file, script_file]:
            try:
                Path(tmp).unlink()
            except OSError:
                pass

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "PCB generation failed",
            "stderr": proc.stderr.strip() if proc.stderr else "",
            "stdout": proc.stdout.strip() if proc.stdout else "",
        }

    result: dict[str, Any] = {"ok": True, "board_file": str(board_file)}
    try:
        payload = json.loads(proc.stdout)
        result.update(payload)
    except json.JSONDecodeError:
        result["raw_output"] = proc.stdout
    result.setdefault("ok", True)
    return result
