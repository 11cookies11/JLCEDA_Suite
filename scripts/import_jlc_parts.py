"""Import EasyEDA/LCSC parts into project-local KiCad library.

Reads a circuit-model.json, extracts LCSC IDs, runs easyeda2kicad for each,
merges into project libs/, and outputs a mapping for schematic generation.

Usage:
  python scripts/import_jlc_parts.py <circuit-model.json> <project-dir>
  python scripts/import_jlc_parts.py <circuit-model.json> <project-dir> --delay 3.0
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def run_easyeda2kicad(lcsc_id: str, sym_lib: Path) -> dict[str, str]:
    """Run easyeda2kicad for one LCSC ID. Returns {lcsc_id, symbol, footprint, model_dir, error}."""
    cmd = ["easyeda2kicad", "--full", f"--lcsc_id={lcsc_id}", "--output", str(sym_lib), "--overwrite"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = proc.stdout + proc.stderr

        # Parse symbol name and footprint name from output
        symbol_name = ""
        footprint_name = ""
        for line in output.splitlines():
            if "Symbol name" in line:
                symbol_name = line.split(":")[-1].strip()
            if "Footprint name:" in line:
                footprint_name = line.split(":")[-1].strip()

        return {
            "lcsc_id": lcsc_id,
            "symbol": symbol_name,
            "footprint": footprint_name,
            "success": proc.returncode == 0,
            "error": "" if proc.returncode == 0 else output[-200:],
        }
    except Exception as exc:
        return {"lcsc_id": lcsc_id, "symbol": "", "footprint": "", "success": False, "error": str(exc)}


def import_parts_from_model(model_path: str, project_dir: str, delay: float = 2.0) -> dict:
    """Import all LCSC parts from a circuit model into project-local libraries."""
    model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    project = Path(project_dir)
    lib_dir = project / "libs"
    lib_dir.mkdir(parents=True, exist_ok=True)

    # Collect unique LCSC IDs from components
    lcsc_parts: dict[str, dict] = {}  # lcsc_id -> {ref, role, value, package}
    for comp in model.get("components", []):
        sp = comp.get("selected_part", {})
        lcsc = str(sp.get("lcsc_id", ""))
        if lcsc and lcsc not in lcsc_parts:
            lcsc_parts[lcsc] = {
                "ref": str(comp.get("ref", "")),
                "role": str(comp.get("role", "")),
                "value": str(comp.get("value", "")),
                "package": str(sp.get("package", "")),
                "mpn": str(sp.get("mpn", "")),
            }

    if not lcsc_parts:
        print("No LCSC parts found in circuit model.")
        return {"imported": 0, "parts": {}}

    print(f"Importing {len(lcsc_parts)} unique LCSC parts...")

    # Import each part to the project library
    sym_lib = lib_dir / "jlc_symbols.kicad_sym"
    imported: dict[str, dict] = {}
    success_count = 0

    for i, (lcsc_id, info) in enumerate(lcsc_parts.items(), 1):
        ref = info["ref"]
        print(f"  [{i}/{len(lcsc_parts)}] {ref:5s} {lcsc_id} ...", end=" ", flush=True)
        result = run_easyeda2kicad(lcsc_id, sym_lib)
        if result["success"]:
            print(f"OK  sym={result['symbol']}  fp={result['footprint']}")
            result.update(info)
            imported[lcsc_id] = result
            success_count += 1
        else:
            print(f"FAIL: {result['error'][:80]}")
        time.sleep(delay)

    # Rename footprint and 3d directories to our standard names
    default_fp = lib_dir / "jlc_symbols.pretty"
    target_fp = lib_dir / "jlc_footprints.pretty"
    if default_fp.exists() and default_fp != target_fp:
        if target_fp.exists():
            # Merge: copy new footprints into existing
            for mod in default_fp.glob("*.kicad_mod"):
                shutil.copy2(str(mod), str(target_fp / mod.name))
            shutil.rmtree(str(default_fp), ignore_errors=True)
        else:
            default_fp.rename(target_fp)

    default_3d = lib_dir / "jlc_symbols.3dshapes"
    target_3d = lib_dir / "3dmodels"
    if default_3d.exists() and default_3d != target_3d:
        if target_3d.exists():
            for f in default_3d.iterdir():
                shutil.copy2(str(f), str(target_3d / f.name))
            shutil.rmtree(str(default_3d), ignore_errors=True)
        else:
            default_3d.rename(target_3d)

    # Generate fp-lib-table
    fp_table = project / "fp-lib-table"
    fp_table.write_text(
        f'(fp_lib_table\n'
        f'  (lib (name "jlc_footprints")(type "KiCad")(uri "${{KIPRJMOD}}/../libs/jlc_footprints.pretty")(options "")(descr "JLC/LCSC imported footprints"))\n'
        f')\n',
        encoding="utf-8",
    )

    print(f"\nImported {success_count}/{len(lcsc_parts)} parts.")
    print(f"  Symbol lib:    {sym_lib}")
    print(f"  Footprint dir: {target_fp}")
    print(f"  3D model dir:  {target_3d}")
    print(f"  fp-lib-table:  {fp_table}")

    return {
        "imported": success_count,
        "total": len(lcsc_parts),
        "parts": imported,
        "sym_lib": str(sym_lib),
        "fp_dir": str(target_fp),
        "model_dir": str(target_3d),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python import_jlc_parts.py <circuit-model.json> <project-dir> [--delay 3.0]")
        sys.exit(1)

    delay = 2.0
    for i, arg in enumerate(sys.argv):
        if arg == "--delay" and i + 1 < len(sys.argv):
            delay = float(sys.argv[i + 1])

    result = import_parts_from_model(sys.argv[1], sys.argv[2], delay=delay)
    print(json.dumps({k: v for k, v in result.items() if k != "parts"}, indent=2, ensure_ascii=False))
