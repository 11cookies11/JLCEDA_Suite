"""Generate a .kicad_pcb board file from the KiCad execution plan + footprint libraries."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .env_utils import env


PCB_FILE_VERSION = "20250119"


def generate_pcb(plan: dict[str, Any], project_path: str | Path | None = None) -> dict[str, Any]:
    """Create a ``.kicad_pcb`` file with components placed in rows by sheet.

    Reads symbol footprints from the plan and places them on a grid.
    Returns a dict with ``board_file`` path and ``component_count``.
    """
    proj = Path(project_path) if project_path else None
    target = plan.get("target", {})
    if not isinstance(target, dict):
        return {"ok": False, "error": "plan has no target"}
    output_dir = Path(str(target.get("output_dir", ".")))
    project_name = str(target.get("project_name", "kicad_project"))
    board_file = output_dir / (project_name + ".kicad_pcb")

    symbols = [s for s in plan.get("symbols", []) if isinstance(s, dict)]
    nets = [n for n in plan.get("nets", []) if isinstance(n, dict)]

    # Read PCB layout from DSL if present
    regions = _read_pcb_regions(project_path)

    # Place symbols: regions first, remaining in rows
    placements = _compute_placements(symbols, regions)

    # Generate board content
    board_lines = _build_board(board_file, symbols, nets, placements, project_name, proj)
    board_file.write_text("\n".join(board_lines) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "board_file": str(board_file),
        "component_count": len(symbols),
        "net_count": len(nets),
        "regions": len(regions) if regions else 0,
    }


def _read_pcb_regions(project_path: str | Path | None) -> dict[str, dict[str, Any]] | None:
    """Read pcb_layout.regions from circuit-model.json, return {ref: {x, y}} or None."""
    if not project_path:
        return None
    model_file = Path(project_path) / "circuit-model.json"
    if not model_file.is_file():
        return None
    try:
        model = json.loads(model_file.read_text(encoding="utf-8"))
        pcb = model.get("pcb_layout", {})
        if not isinstance(pcb, dict):
            return None
        regions = pcb.get("regions", {})
        if not isinstance(regions, dict):
            return None
        result: dict[str, dict[str, Any]] = {}
        for _name, region in regions.items():
            if not isinstance(region, dict):
                continue
            rx = float(region.get("x", 25))
            ry = float(region.get("y", 25))
            comps = region.get("components", [])
            if not isinstance(comps, list):
                continue
            spacing = float(region.get("spacing", 18))
            for idx, ref in enumerate(comps):
                result[str(ref)] = {"x": rx + idx * spacing, "y": ry}
        return result if result else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _compute_placements(
    symbols: list[dict[str, Any]], regions: dict[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return [(ref, footprint, x, y, height)] for every symbol.
    Region-placed symbols go first, rest auto-laid in rows.
    """
    placed: list[dict[str, Any]] = []
    auto_refs: list[str] = []

    for sym in symbols:
        ref = str(sym.get("ref", ""))
        fp = _resolve_footprint(sym)
        fp_path = _find_footprint_file(fp)
        h = _estimate_footprint_height(fp_path)
        if regions and ref in regions:
            r = regions[ref]
            placed.append({"ref": ref, "fp": fp, "x": r["x"], "y": r["y"], "h": h, "fp_path": fp_path, "sym": sym})
        else:
            placed.append({"ref": ref, "fp": fp, "x": 0, "y": 0, "h": h, "fp_path": fp_path, "sym": sym})
            auto_refs.append(ref)

    # Auto-layout remaining symbols in rows
    if auto_refs:
        max_ry = max((p["y"] + p["h"] + 5 for p in placed if p["x"] > 0), default=25)
        cursor_x = 25.0
        cursor_y = max_ry + 20
        row_height = 0.0
        for p in placed:
            if p["ref"] in auto_refs:
                p["x"] = cursor_x
                p["y"] = cursor_y
                cursor_x += 20
                row_height = max(row_height, p["h"])
                if cursor_x > 160:
                    cursor_x = 25
                    cursor_y += row_height + 25
                    row_height = 0

    return placed


def _group_by_sheet(symbols: list[dict[str, Any]], project_path: str | Path | None) -> dict[str, list[dict[str, Any]]]:
    """Group symbols by their sheet assignment from the DSL."""
    pages: dict[str, list[dict[str, Any]]] = {}
    if project_path:
        model_file = Path(project_path) / "circuit-model.json"
        if model_file.is_file():
            try:
                model = json.loads(model_file.read_text(encoding="utf-8"))
                dsl_sheets = model.get("sheets", [])
                if isinstance(dsl_sheets, list) and dsl_sheets:
                    ref_to_page = {}
                    for sheet in dsl_sheets:
                        for ref in sheet.get("components", []):
                            ref_to_page[str(ref)] = str(sheet.get("name", ""))
                    for sym in symbols:
                        ref = str(sym.get("ref", ""))
                        pages.setdefault(ref_to_page.get(ref, "other"), []).append(sym)
                    return pages
            except (OSError, json.JSONDecodeError):
                pass
    pages["board"] = symbols
    return pages


def _build_board(
    board_file: Path,
    symbols: list[dict[str, Any]],
    nets: list[dict[str, Any]],
    placements: list[dict[str, Any]],
    project_name: str,
    project_path: Path | None = None,
) -> list[str]:
    lines = [
        f'(kicad_pcb (version {PCB_FILE_VERSION}) (generator "hwtool")',
        f"  (general (thickness 1.6))",
    ]
    for idx, net in enumerate(nets, start=1):
        lines.append(f"  (net {idx} {_q(net.get('name', ''))})")

    all_x = [p["x"] for p in placements]
    all_y = [p["y"] for p in placements]
    max_h = max((p.get("h", 10) for p in placements), default=10)
    max_x = max(all_x) + 20 if all_x else 160
    max_y = max(all_y) + max_h + 10 if all_y else 80

    for p in placements:
        ref = p["ref"]
        fp = p["fp"]
        sym = p.get("sym", {})
        comp_uuid = str(uuid.uuid4())
        lines.append(f"  (footprint {_q(fp)} (layer F.Cu) (tedit 0) (tstamp {comp_uuid})")
        lines.append(f"    (at {p['x']:.2f} {p['y']:.2f} 0)")
        lines.append(f"    (attr smd)")
        lines.append(f"    (property \"Reference\" {_q(ref)} (at 0 0 0) (layer F.SilkS) (effects (font (size 1 1) (thickness 0.15))))")
        lines.append(f"    (property \"Value\" {_q(str(sym.get('value', ref)))} (at 0 2 0) (layer F.Fab) (effects (font (size 1 1) (thickness 0.15))))")

        fp_path = p.get("fp_path") or _find_footprint_file(fp, project_path)
        if fp_path:
            lines.extend(_extract_pads(fp_path))
        else:
            lines.append(f"    (pad \"1\" smd rect (at -1.27 0) (size 2.0 1.5) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))")
            lines.append(f"    (pad \"2\" smd rect (at 1.27 0) (size 2.0 1.5) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))")
        lines.append(f"  )")

    # Edge cuts outline
    margin = 5.0
    lines.append(f"  (gr_line (start {25 - margin:.2f} {25 - margin:.2f}) (end {max_x + margin:.2f} {25 - margin:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(f"  (gr_line (start {max_x + margin:.2f} {25 - margin:.2f}) (end {max_x + margin:.2f} {max_y + margin:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(f"  (gr_line (start {max_x + margin:.2f} {max_y + margin:.2f}) (end {25 - margin:.2f} {max_y + margin:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(f"  (gr_line (start {25 - margin:.2f} {max_y + margin:.2f}) (end {25 - margin:.2f} {25 - margin:.2f}) (layer Edge.Cuts) (width 0.1))")
    lines.append(")")
    return lines


def _resolve_footprint(symbol: dict[str, Any]) -> str:
    """Resolve a footprint name for a symbol."""
    fp = str(symbol.get("footprint", ""))
    if fp and ":" in fp:
        return fp.split(":", 1)[-1]
    return fp or _default_fp_for_role(str(symbol.get("role", "")))


def _default_fp_for_role(role: str) -> str:
    """Return a rough default footprint hint based on role."""
    role_lower = role.lower()
    if "mcu" in role_lower:
        return "LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL"
    if any(w in role_lower for w in ("regulator", "ldo", "buck")):
        return "SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR"
    if "crystal" in role_lower or "xtal" in role_lower:
        return "CRYSTAL-SMD_4P-L3.2-W2.5-BL"
    if "capacitor" in role_lower or "decoupling" in role_lower or "bulk" in role_lower or "load_cap" in role_lower or role_lower.startswith("reg_") or role_lower.startswith("vdd_"):
        if "0805" in role_lower or "bulk" in role_lower:
            return "C0805"
        return "C0603"
    if "resistor" in role_lower or "pullup" in role_lower or "pulldown" in role_lower:
        return "R0603"
    if "led" in role_lower:
        return "LED-SMD_L1.6-W0.8-RD_GREEN-1"
    if "usb" in role_lower:
        return "USB-C-SMD_TYPE-C16PIN"
    if "header" in role_lower or "debug" in role_lower or "swd" in role_lower:
        return "HDR-TH_4P-P2.54-V-M"
    if "button" in role_lower or "switch" in role_lower or "reset" in role_lower:
        return "SW-SMD_K5-1617SA-02"
    return "C0603"  # safe fallback


def _find_footprint_file(fp_name: str, project_path: str | Path | None = None) -> Path | None:
    """Search for a footprint .kicad_mod file in the project or system libraries."""
    # 1. Project-local libraries (resolve-symbols output)
    if project_path:
        for pretty in Path(project_path).glob("libraries/footprints/*.pretty"):
            fp_file = pretty / (fp_name + ".kicad_mod")
            if fp_file.is_file():
                return fp_file

    # 2. Output directory parent
    output_root = env("KICAD_OUTPUT_DIR", "")
    if output_root:
        out = Path(output_root)
        for pretty in (out.parent / "libraries" / "footprints").glob("*.pretty"):
            fp_file = pretty / (fp_name + ".kicad_mod")
            if fp_file.is_file():
                return fp_file

    # 3. KICAD_WORKSPACE
    workspace = env("KICAD_WORKSPACE", "")
    if workspace:
        for pretty in Path(workspace).glob("libraries/footprints/*.pretty"):
            fp_file = pretty / (fp_name + ".kicad_mod")
            if fp_file.is_file():
                return fp_file

    # 4. Repo-bundled footprints
    from .kicad_project_writer import REPO_ROOT
    for pretty in (REPO_ROOT / "resources" / "kicad" / "footprints").glob("*.pretty"):
        fp_file = pretty / (fp_name + ".kicad_mod")
        if fp_file.is_file():
            return fp_file

    return None


def _extract_pads(fp_path: Path) -> list[str]:
    """Extract pad definitions from a .kicad_mod file."""
    try:
        text = fp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("(pad "):
            lines.append(f"    {stripped}")
    return lines


def _estimate_footprint_height(fp_path: Path | None) -> float:
    """Return a rough height estimate for a footprint, in mm."""
    if fp_path is None:
        return 10.0
    try:
        text = fp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 10.0
    # Rough: look for pad y-extremes
    import re
    ys = []
    for m in re.finditer(r'\(at\s+[\d.-]+\s+([\d.-]+)', text):
        ys.append(abs(float(m.group(1))))
    if ys:
        return max(ys) * 2 + 5.0
    return 10.0


def _q(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)
