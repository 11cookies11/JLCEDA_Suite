"""Generate a .kicad_pcb board file from the KiCad execution plan + footprint libraries."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

PCB_FILE_VERSION = "20250119"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, fallback: str = "") -> str:
    v = os.environ.get(name)
    return v if isinstance(v, str) and v else fallback


def _q(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def generate_pcb(plan: dict[str, Any], project_path: str | Path | None = None) -> dict[str, Any]:
    """Create a ``.kicad_pcb`` file with components placed by DSL pcb_layout.regions."""
    if not project_path:
        output_root = _env("KICAD_OUTPUT_DIR", "")
        if output_root:
            project_path = str(Path(output_root).parent)
    proj = Path(project_path) if project_path else None
    target = plan.get("target", {})
    if not isinstance(target, dict):
        return {"ok": False, "error": "plan has no target"}
    output_dir = Path(str(target.get("output_dir", ".")))
    project_name = str(target.get("project_name", "kicad_project"))
    board_file = output_dir / (project_name + ".kicad_pcb")

    symbols = [s for s in plan.get("symbols", []) if isinstance(s, dict)]
    nets = [n for n in plan.get("nets", []) if isinstance(n, dict)]
    regions = _read_regions(proj)
    placements = _compute_placements(symbols, regions)

    lines = [
        f'(kicad_pcb (version {PCB_FILE_VERSION}) (generator "hwtool"))',
        f"  (general (thickness 1.6))",
    ]
    for idx, net in enumerate(nets, start=1):
        lines.append(f"  (net {idx} {_q(net.get('name', ''))})")

    for p in placements:
        x, y = float(p["x"]), float(p["y"])
        rot = int(p.get("rotation", 0))
        ref, fp = p["ref"], p["fp"]
        sym = p.get("sym", {})
        lines.append(f"  (footprint {_q(fp)} (layer F.Cu) (tedit 0) (tstamp {str(uuid.uuid4())})")
        lines.append(f"    (at {x:.2f} {y:.2f} {rot})")
        lines.append(f"    (attr smd)")
        lines.append(f"    (property \"Reference\" {_q(ref)} (at 0 0 0) (layer F.SilkS) (effects (font (size 1 1) (thickness 0.15))))")
        lines.append(f"    (property \"Value\" {_q(str(sym.get('value', ref)))} (at 0 2 0) (layer F.Fab) (effects (font (size 1 1) (thickness 0.15))))")

        fp_path = p.get("fp_path") or _find_footprint_file(fp, proj)
        if fp_path:
            for pad_line in _extract_pads(fp_path):
                lines.append(f"    {pad_line}")
        else:
            lines.append(f"    (pad \"1\" smd rect (at -1.27 0) (size 2.0 1.5) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))")
            lines.append(f"    (pad \"2\" smd rect (at 1.27 0) (size 2.0 1.5) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))")
        lines.append("  )")

    # Edge cuts
    all_x = [p["x"] for p in placements]
    all_y = [p["y"] for p in placements]
    max_h = max((p.get("h", 10) for p in placements), default=10)
    max_x = max(all_x) + 25 if all_x else 160
    max_y = max(all_y) + max_h + 15 if all_y else 80
    m = 5.0
    lines.append(f"  (gr_line (start {25-m:.2f} {25-m:.2f}) (end {max_x+m:.2f} {25-m:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(f"  (gr_line (start {max_x+m:.2f} {25-m:.2f}) (end {max_x+m:.2f} {max_y+m:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(f"  (gr_line (start {max_x+m:.2f} {max_y+m:.2f}) (end {25-m:.2f} {max_y+m:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(f"  (gr_line (start {25-m:.2f} {max_y+m:.2f}) (end {25-m:.2f} {25-m:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(")")

    board_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    placement_refs = [{"ref": p["ref"], "x": float(p["x"]), "y": float(p["y"]), "rotation": int(p.get("rotation", 0))} for p in placements]
    return {"ok": True, "board_file": str(board_file), "component_count": len(symbols), "net_count": len(nets), "regions": len(regions) if regions else 0, "placements": placement_refs}


def _read_regions(project_path: Path | None) -> dict[str, dict[str, Any]] | None:
    if not project_path:
        return None
    model_file = project_path / "circuit-model.json"
    if not model_file.is_file():
        return None
    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
        regions = model.get("pcb_layout", {}).get("regions", {})
        if not isinstance(regions, dict):
            return None
        result: dict[str, dict[str, Any]] = {}
        for _name, region in regions.items():
            if not isinstance(region, dict):
                continue
            rx, ry = float(region.get("x", 25)), float(region.get("y", 25))
            comps = region.get("components", [])
            if not isinstance(comps, list):
                continue
            spacing = float(region.get("spacing", 18))
            for idx, ref in enumerate(comps):
                result[str(ref)] = {"x": rx + idx * spacing, "y": ry}
        return result if result else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _compute_placements(symbols: list[dict[str, Any]], regions: dict[str, dict[str, Any]] | None) -> list[dict[str, Any]]:
    placed: list[dict[str, Any]] = []
    auto_refs: list[str] = []
    ref_to_sym = {str(s.get("ref", "")): s for s in symbols}

    if regions:
        for ref, r in regions.items():
            if ref not in ref_to_sym:
                continue
            sym = ref_to_sym[ref]
            fp = _resolve_footprint(sym)
            fp_path = _find_footprint_file(fp)
            placed.append({"ref": ref, "fp": fp, "x": r["x"], "y": r["y"], "rotation": r.get("rotation", 0), "h": _fp_height(fp_path), "fp_path": fp_path, "sym": sym})

    for sym in symbols:
        ref = str(sym.get("ref", ""))
        if regions and ref in regions:
            continue
        fp = _resolve_footprint(sym)
        fp_path = _find_footprint_file(fp)
        placed.append({"ref": ref, "fp": fp, "x": 0, "y": 0, "rotation": 0, "h": _fp_height(fp_path), "fp_path": fp_path, "sym": sym})
        auto_refs.append(ref)

    if auto_refs:
        grid_x, grid_y = 25.0, max((p["y"] + p.get("h", 10) + 10 for p in placed if p.get("y", 0) > 0), default=25) + 20
        row_h = 0.0
        for p in placed:
            if p["ref"] not in auto_refs:
                continue
            p["x"], p["y"] = grid_x, grid_y
            grid_x += 20
            row_h = max(row_h, p.get("h", 10))
            if grid_x > 160:
                grid_x, grid_y = 25, grid_y + row_h + 15
                row_h = 0
    return placed


def _resolve_footprint(symbol: dict[str, Any]) -> str:
    fp = str(symbol.get("footprint", ""))
    if fp and ":" in fp:
        return fp.split(":", 1)[-1]
    if fp:
        return fp
    role = str(symbol.get("role", "")).lower()
    for kw, fp_name in [("mcu", "LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL"), ("regulator", "SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR"), ("crystal", "OSC-SMD_4P-L3.2-W2.5-BL"), ("capacitor", "C0603"), ("0805", "C0805"), ("resistor", "R0603"), ("led", "LED-SMD_L1.6-W0.8-RD_GREEN-1"), ("usb", "USB-C-SMD_USB-TYPE-C-006"), ("header", "HDR-TH_2P-P2.54-V-M"), ("button", "SW-SMD_K5-1617SA-02"), ("switch", "SW-SMD_K5-1617SA-02")]:
        if kw in role:
            return fp_name
    return "C0603"


def _find_footprint_file(fp_name: str, project_path: Path | None = None) -> Path | None:
    if project_path:
        for pretty in project_path.glob("libraries/footprints/*.pretty"):
            fp_file = pretty / (fp_name + ".kicad_mod")
            if fp_file.is_file():
                return fp_file
    out_env = _env("KICAD_OUTPUT_DIR", "")
    if out_env:
        for pretty in Path(out_env).parent.glob("libraries/footprints/*.pretty"):
            fp_file = pretty / (fp_name + ".kicad_mod")
            if fp_file.is_file():
                return fp_file
    for pretty in (_REPO_ROOT / "resources" / "kicad" / "footprints").glob("*.pretty"):
        fp_file = pretty / (fp_name + ".kicad_mod")
        if fp_file.is_file():
            return fp_file
    return None


def _extract_pads(fp_path: Path) -> list[str]:
    try:
        text = fp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [line.strip() for line in text.splitlines() if line.strip().startswith("(pad ")]


def _fp_height(fp_path: Path | None) -> float:
    if fp_path is None:
        return 10.0
    try:
        ys = [abs(float(m.group(1))) for m in re.finditer(r'\(at\s+[\d.-]+\s+([\d.-]+)', fp_path.read_text(encoding="utf-8"))]
        return max(ys) * 2 + 5 if ys else 10.0
    except (OSError, UnicodeDecodeError):
        return 10.0
