"""PCB placement planning service.

This service translates ``pcb_layout.regions`` from the circuit model into a
structured placement plan that can be inspected by the main pipeline, reports,
and future placement engines.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..shared.env_utils import normalize_text


PLACEMENT_PLAN_SCHEMA_VERSION = "placement-plan.v1"


@dataclass
class PlacementSize:
    width_mm: float
    height_mm: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_mm(value: Any, fallback: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return fallback
    match = re.search(r"([-+]?\d*\.?\d+)", text)
    if not match:
        return fallback
    try:
        return float(match.group(1))
    except ValueError:
        return fallback


def _extract_board_size(model: dict[str, Any], region_count: int) -> tuple[float, float, str]:
    constraints = model.get("constraints", [])
    if isinstance(constraints, list):
        for item in constraints:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).strip() != "board_size":
                continue
            rules = item.get("rules", [])
            if not isinstance(rules, list):
                continue
            width = None
            height = None
            for rule in rules:
                text = str(rule)
                if "max_width" in text:
                    width = _parse_mm(text.split(":", 1)[-1], 0.0)
                elif "max_height" in text:
                    height = _parse_mm(text.split(":", 1)[-1], 0.0)
            if width and height:
                return width, height, "constraints.board_size"

    regions = model.get("pcb_layout", {}).get("regions", {})
    max_x = 0.0
    max_y = 0.0
    if isinstance(regions, dict):
        for region in regions.values():
            if not isinstance(region, dict):
                continue
            max_x = max(max_x, _parse_mm(region.get("x", 0.0), 0.0))
            max_y = max(max_y, _parse_mm(region.get("y", 0.0), 0.0))

    width = max(100.0, max_x + max(20.0, region_count * 12.0))
    height = max(80.0, max_y + max(20.0, region_count * 10.0))
    return width, height, "inferred"


def _component_priority(component: dict[str, Any]) -> tuple[int, str]:
    role = normalize_text(component.get("role", ""))
    package = normalize_text(component.get("package", ""))
    value = normalize_text(component.get("value", ""))
    role_priority_map = {
        "mcu": 0,
        "soc": 0,
        "clock": 1,
        "crystal": 1,
        "power": 1,
        "regulator": 1,
        "ldo": 1,
        "connector": 2,
        "usb": 2,
        "debug": 2,
        "reset": 3,
        "boot": 3,
        "decoupling": 4,
        "capacitor": 4,
        "resistor": 5,
        "indicator": 6,
    }
    priority = 9
    for key, value_score in role_priority_map.items():
        if key in role or key in package or key in value:
            priority = min(priority, value_score)
    return priority, role


def _estimate_component_size(component: dict[str, Any]) -> PlacementSize:
    role = normalize_text(component.get("role", ""))
    package = normalize_text(component.get("package", ""))
    selected_part = component.get("selected_part", {})
    if isinstance(selected_part, dict):
        package = normalize_text(selected_part.get("package", package))
    value = normalize_text(component.get("value", ""))

    def size(width: float, height: float) -> PlacementSize:
        return PlacementSize(width_mm=width, height_mm=height)

    if any(token in role for token in ("connector", "usb", "jack", "terminal")) or "connector" in package:
        return size(14.0, 8.0)
    if any(token in role for token in ("mcu", "soc", "fpga", "pmic", "regulator", "ldo", "driver")):
        return size(10.0, 10.0)
    if "qfn" in package or "bga" in package:
        return size(10.0, 10.0)
    if any(token in role for token in ("crystal", "oscillator", "clock")) or "crystal" in value:
        return size(4.0, 3.0)
    if any(token in role for token in ("capacitor", "decoupling", "cap")) or package in {"0402", "0603", "0805"}:
        return size(2.0, 2.0)
    if any(token in role for token in ("resistor", "pullup", "pulldown")) or package in {"0402", "0603", "0805"}:
        return size(2.0, 1.0)
    if any(token in role for token in ("inductor", "ferrite", "bead")):
        return size(4.0, 3.0)
    if any(token in role for token in ("switch", "button", "reset", "boot", "indicator", "led")):
        return size(5.0, 5.0)
    if "sot" in package or "soic" in package or "tssop" in package:
        return size(6.0, 4.0)
    return size(4.0, 3.0)


def _pack_region(
    *,
    region_name: str,
    region: dict[str, Any],
    components: list[dict[str, Any]],
    board_width: float,
    board_height: float,
) -> dict[str, Any]:
    anchor_x = _parse_mm(region.get("x", 0.0), 0.0)
    anchor_y = _parse_mm(region.get("y", 0.0), 0.0)
    spacing = _parse_mm(region.get("spacing", 4.0), 4.0)
    rotation = _parse_mm(region.get("rotation", 0.0), 0.0)
    ordered = sorted(components, key=_component_priority)
    if not ordered:
        return {
            "name": region_name,
            "source": "pcb_layout.regions",
            "synthetic": False,
            "anchor": {"x": anchor_x, "y": anchor_y},
            "spacing_mm": spacing,
            "rotation_deg": rotation,
            "components": [],
            "placements": [],
            "bbox": {"x": anchor_x, "y": anchor_y, "width": 0.0, "height": 0.0},
            "warnings": [],
        }

    columns = max(1, math.ceil(math.sqrt(len(ordered))))
    rows = max(1, math.ceil(len(ordered) / columns))
    grid: list[list[dict[str, Any] | None]] = [[None for _ in range(columns)] for _ in range(rows)]
    for index, component in enumerate(ordered):
        grid[index // columns][index % columns] = component

    col_widths = [0.0 for _ in range(columns)]
    row_heights = [0.0 for _ in range(rows)]
    sizes: dict[str, PlacementSize] = {}
    for row in range(rows):
        for col in range(columns):
            component = grid[row][col]
            if not component:
                continue
            size = _estimate_component_size(component)
            sizes[str(component.get("ref", ""))] = size
            col_widths[col] = max(col_widths[col], size.width_mm)
            row_heights[row] = max(row_heights[row], size.height_mm)

    x_offsets = [anchor_x]
    for col in range(1, columns):
        x_offsets.append(x_offsets[-1] + col_widths[col - 1] + spacing)
    y_offsets = [anchor_y]
    for row in range(1, rows):
        y_offsets.append(y_offsets[-1] + row_heights[row - 1] + spacing)

    placements: list[dict[str, Any]] = []
    for row in range(rows):
        for col in range(columns):
            component = grid[row][col]
            if not component:
                continue
            ref = str(component.get("ref", "")).strip()
            size = sizes.get(ref, PlacementSize(width_mm=4.0, height_mm=3.0))
            placements.append(
                {
                    "ref": ref,
                    "role": str(component.get("role", "")),
                    "x": round(x_offsets[col], 2),
                    "y": round(y_offsets[row], 2),
                    "width_mm": round(size.width_mm, 2),
                    "height_mm": round(size.height_mm, 2),
                    "rotation_deg": rotation,
                    "slot_index": row * columns + col,
                }
            )

    width = sum(col_widths) + spacing * max(columns - 1, 0)
    height = sum(row_heights) + spacing * max(rows - 1, 0)
    warnings: list[str] = []
    if anchor_x + width > board_width:
        warnings.append(f"region '{region_name}' exceeds board width")
    if anchor_y + height > board_height:
        warnings.append(f"region '{region_name}' exceeds board height")

    return {
        "name": region_name,
        "source": "pcb_layout.regions",
        "synthetic": False,
        "anchor": {"x": anchor_x, "y": anchor_y},
        "spacing_mm": spacing,
        "rotation_deg": rotation,
        "components": [str(component.get("ref", "")) for component in ordered],
        "placements": placements,
        "bbox": {
            "x": anchor_x,
            "y": anchor_y,
            "width": round(width, 2),
            "height": round(height, 2),
        },
        "warnings": warnings,
    }


def _bbox_overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ax1 = float(a.get("x", 0.0))
    ay1 = float(a.get("y", 0.0))
    ax2 = ax1 + float(a.get("width", 0.0))
    ay2 = ay1 + float(a.get("height", 0.0))
    bx1 = float(b.get("x", 0.0))
    by1 = float(b.get("y", 0.0))
    bx2 = bx1 + float(b.get("width", 0.0))
    by2 = by1 + float(b.get("height", 0.0))
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


def build_placement_plan(model: dict[str, Any]) -> dict[str, Any]:
    components = [
        item for item in model.get("components", [])
        if isinstance(item, dict)
    ]
    component_by_ref = {str(component.get("ref", "")).strip(): component for component in components if str(component.get("ref", "")).strip()}
    pcb_layout = model.get("pcb_layout", {})
    regions = pcb_layout.get("regions", {}) if isinstance(pcb_layout, dict) else {}
    region_items = list(regions.items()) if isinstance(regions, dict) else []
    board_width, board_height, board_source = _extract_board_size(model, len(region_items))

    plan_regions: list[dict[str, Any]] = []
    placed_refs: set[str] = set()
    warnings: list[str] = []

    for region_name, region in region_items:
        if not isinstance(region, dict):
            continue
        refs = [
            ref for ref in region.get("components", [])
            if isinstance(ref, str) and ref.strip() in component_by_ref
        ]
        missing = [
            str(ref)
            for ref in region.get("components", [])
            if isinstance(ref, str) and ref.strip() not in component_by_ref
        ]
        if missing:
            warnings.append(f"region '{region_name}' references unknown components: {', '.join(missing)}")
        region_components = [component_by_ref[ref] for ref in refs]
        plan_region = _pack_region(
            region_name=region_name,
            region=region,
            components=region_components,
            board_width=board_width,
            board_height=board_height,
        )
        plan_regions.append(plan_region)
        placed_refs.update(refs)
        warnings.extend(plan_region["warnings"])

    unassigned_components = [
        component_by_ref[ref]
        for ref in component_by_ref
        if ref not in placed_refs
    ]
    unassigned_region: dict[str, Any] | None = None
    if unassigned_components:
        fallback_region = {
            "x": max(0.0, board_width * 0.55),
            "y": max(0.0, board_height * 0.08),
            "rotation": 0.0,
            "spacing": 4.0,
        }
        unassigned_region = _pack_region(
            region_name="unassigned",
            region=fallback_region,
            components=unassigned_components,
            board_width=board_width,
            board_height=board_height,
        )
        unassigned_region["synthetic"] = True
        warnings.append(
            "some components were not assigned to pcb_layout.regions; they were packed into the fallback region"
        )
        plan_regions.append(unassigned_region)

    overlaps: list[tuple[str, str]] = []
    for index, region in enumerate(plan_regions):
        for other in plan_regions[index + 1:]:
            if _bbox_overlaps(region.get("bbox", {}), other.get("bbox", {})):
                overlaps.append((str(region.get("name", "")), str(other.get("name", ""))))
    for left, right in overlaps:
        warnings.append(f"region overlap detected between '{left}' and '{right}'")

    summary = {
        "region_count": len(region_items),
        "synthetic_region_count": 1 if unassigned_region else 0,
        "component_count": len(component_by_ref),
        "placed_count": sum(len(region.get("placements", [])) for region in plan_regions),
        "unassigned_count": len(unassigned_components),
        "overlap_count": len(overlaps),
    }

    return {
        "schema_version": PLACEMENT_PLAN_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "project_id": str(model.get("project_id", "")),
        "topology": str(model.get("topology", "")),
        "board": {
            "width_mm": round(board_width, 2),
            "height_mm": round(board_height, 2),
            "source": board_source,
        },
        "regions": plan_regions,
        "summary": summary,
        "warnings": warnings,
    }


def write_placement_plan(project_path: str | Path, model: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(project_path)
    build_dir = project_root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    plan = build_placement_plan(model)
    plan_file = build_dir / "placement-plan.json"
    plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_file = build_dir / "placement-plan.md"
    report_file.write_text(render_placement_plan_markdown(plan), encoding="utf-8")
    return {
        "ok": True,
        "plan_file": str(plan_file),
        "report_file": str(report_file),
        "plan": plan,
    }


def render_placement_plan_markdown(plan: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# PCB Placement Plan")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Project: `{plan.get('project_id', '')}`")
    lines.append(f"- Topology: `{plan.get('topology', '')}`")
    lines.append(f"- Board: {plan.get('board', {}).get('width_mm', 0)} mm x {plan.get('board', {}).get('height_mm', 0)} mm")
    summary = plan.get("summary", {})
    lines.append(f"- Regions: {summary.get('region_count', 0)}")
    lines.append(f"- Placed components: {summary.get('placed_count', 0)}")
    lines.append(f"- Unassigned components: {summary.get('unassigned_count', 0)}")
    lines.append(f"- Region overlaps: {summary.get('overlap_count', 0)}")
    lines.append("")
    lines.append("## Regions")
    lines.append("| Region | Anchor X | Anchor Y | Components | BBox W | BBox H |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for region in plan.get("regions", []):
        if not isinstance(region, dict):
            continue
        bbox = region.get("bbox", {})
        lines.append(
            f"| {region.get('name', '')} | {float(region.get('anchor', {}).get('x', 0.0)):.1f} | "
            f"{float(region.get('anchor', {}).get('y', 0.0)):.1f} | {len(region.get('placements', []))} | "
            f"{float(bbox.get('width', 0.0)):.1f} | {float(bbox.get('height', 0.0)):.1f} |"
        )
    if plan.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for warning in plan.get("warnings", []):
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"
