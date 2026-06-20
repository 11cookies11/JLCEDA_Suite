"""KiCad backend: resolve ir.v1 ->KiCadExecutionPlan (EDA-specific rendering).

This module contains *all* KiCad-specific logic ???lib_id resolution, footprint
mapping, block layout, position assignment, and symbol size estimation.
The IR layer has none of this.
"""

from __future__ import annotations

import uuid
from typing import Any

from .compile_kicad_execution_plan import (
    KiCadDiagnostics,
    KiCadExecutionPlan,
    KiCadNet,
    KiCadPin,
    KiCadSymbol,
    KiCadTarget,
    _resolve_symbol_overlaps_for_group,
    _validate_symbol_libraries,
    _symbol_sheet_name,
    slugify_project_name,
    symbol_mapping_for,
    to_float_env,
)
from . import kicad_layout_engine as layout_engine
from .kicad_layout_config import layout_numeric_setting
from ...adapters.symbol_footprint_resolver import footprint_exists, normalize_footprint, resolve_footprint
from ...shared.env_utils import env, to_int_env
from ...shared.schema_versions import KICAD_EXECUTION_PLAN_SCHEMA_VERSION


def ir_to_kicad(ir: dict[str, Any]) -> KiCadExecutionPlan:
    """Resolve an EDA-independent IR dict into a KiCadExecutionPlan.

    This is the **only** function that should import from
    ``compile_kicad_execution_plan`` ???all KiCad coupling lives here.
    """
    request_id = str(ir.get("request_id") or uuid.uuid4())
    topology = str(ir.get("topology", ""))
    project_name = slugify_project_name(env("KICAD_PROJECT_NAME", topology or request_id))
    workspace = env("KICAD_WORKSPACE", "")
    if workspace:
        from pathlib import Path
        output_root = Path(workspace) / "output"
    else:
        from pathlib import Path
        output_root = Path(env("KICAD_OUTPUT_DIR", "tmp"))
    output_dir = output_root / project_name

    origin_x = to_float_env("KICAD_SCH_ORIGIN_X_MM", 38.1)
    origin_y = to_float_env("KICAD_SCH_ORIGIN_Y_MM", 38.1)
    pitch_x = to_float_env("KICAD_SCH_PITCH_X_MM", 25.4)
    pitch_y = to_float_env("KICAD_SCH_PITCH_Y_MM", 25.4)
    columns = max(1, to_int_env("KICAD_SCH_COLUMNS", 3))

    diagnostics = KiCadDiagnostics()

    # Build component lookup from IR.
    ir_component_by_ref = {
        c["ref"]: c for c in ir.get("components", []) if isinstance(c, dict)
    }

    # ---- Pass 1: resolve lib_id / footprint for every component ---------
    preflight: list[tuple[str, str, str, str, list[str]]] = []
    for ref, comp in ir_component_by_ref.items():
        # Build a minimal dict that symbol_mapping_for expects.
        sp = comp.get("selected_part", {})
        component_for_map = {
            "ref": ref,
            "role": comp.get("role", ""),
            "value": comp.get("value", ""),
            "selected_part": dict(sp) if isinstance(sp, dict) else {},
        }
        lib_id, footprint, notes = symbol_mapping_for(component_for_map)
        preflight.append((ref, comp.get("role", ""), lib_id, footprint, notes))
        comp["_lib_id"] = lib_id  # stash for position pass

    # Pre-flight symbol library validation.
    _validate_symbol_libraries(preflight)

    # ---- Block layout ---------------------------------------------------
    comp_info = [(ref, role, lib_id) for ref, role, lib_id, _fp, _n in preflight]
    block_layout = layout_engine._compute_block_layout(comp_info)
    block_x = {b: x for b, (x, _y) in block_layout.items()}
    block_y = {b: y for b, (_x, y) in block_layout.items()}
    block_slot: dict[str, int] = {}
    block_cursor_y = dict(block_y)

    # Build netlist-compatible lookup for pin sources.
    netlist_by_ref: dict[str, dict[str, Any]] = {
        c["ref"]: {
            "pins": [
                {"pin": p["number"], "pin_name": p.get("name", ""), "net": p.get("net", "")}
                for p in c.get("pins", []) if isinstance(p, dict)
            ]
        }
        for c in ir.get("components", []) if isinstance(c, dict)
    }

    # ---- Pass 2: build KiCadSymbols with positions ----------------------
    symbols: list[KiCadSymbol] = []
    for ref, role, lib_id, footprint, notes in preflight:
        comp = ir_component_by_ref.get(ref, {})
        nc = netlist_by_ref.get(ref, {})
        sp = comp.get("selected_part", {})
        pins = [
            KiCadPin(
                number=str(pin.get("pin", "")),
                name=str(pin.get("pin_name", "")),
                net=str(pin.get("net", "")),
            )
            for pin in nc.get("pins", []) if isinstance(pin, dict)
        ]
        if not pins:
            diagnostics.warnings.append(
                f"{ref} has no net pins; symbol will be placed without connectivity labels."
            )
        if lib_id.startswith("AIAgent:"):
            diagnostics.unsupported.append(
                f"{ref} uses placeholder symbol {lib_id}; replace with verified KiCad library symbol later."
            )
        exists = footprint_exists(footprint)
        if exists is False:
            if footprint:
                diagnostics.unsupported.append(
                    f"{ref} footprint {footprint} was not found in the configured KiCad footprint libraries."
                )
            else:
                diagnostics.unsupported.append(
                    f"{ref} has no KiCad footprint assignment."
                )

        at = _resolve_position(
            ir=ir,
            comp=comp,
            index=0,
            origin_x=origin_x,
            origin_y=origin_y,
            pitch_x=pitch_x,
            pitch_y=pitch_y,
            columns=columns,
            block_x=block_x,
            block_y=block_y,
            block_slot=block_slot,
            block_cursor_y=block_cursor_y,
            lib_id=lib_id,
        )
        symbols.append(
            KiCadSymbol(
                ref=ref,
                role=role,
                value=comp.get("value", ""),
                lib_id=lib_id,
                footprint=footprint,
                at=at,
                pins=pins,
                notes=list(notes) if notes else [],
                lcsc=str(sp.get("lcsc_id", "")),
                mpn=str(sp.get("mpn", "")),
                manufacturer=str(sp.get("manufacturer", "")),
                in_bom=bool(comp.get("in_bom", True)),
                on_board=bool(comp.get("on_board", True)),
            )
        )

    ref_to_sheet = {
        str(comp.get("ref", "")).upper(): str(comp.get("assigned_sheet", ""))
        for comp in ir.get("components", [])
        if isinstance(comp, dict) and str(comp.get("ref", "")).strip()
    }
    layout_engine.apply_sheet_aware_schematic_layout(symbols, ref_to_sheet, topology)

    # ---- Sheet-aware overlap resolution --------------------------------
    sheet_groups: dict[str, list[KiCadSymbol]] = {}
    for sym in symbols:
        # Functional layout blocks can coexist on the same source sheet, so
        # only the source-model sheet assignment is a valid isolation boundary.
        sheet = ref_to_sheet.get(sym.ref.upper(), _symbol_sheet_name(sym, topology))
        sheet_groups.setdefault(sheet, []).append(sym)
    overlap_passes = max(1, to_int_env("KICAD_SCH_OVERLAP_PASSES", 64))
    for sheet, group in sheet_groups.items():
        passes = _resolve_symbol_overlaps_for_group(
            group, layout_numeric_setting("block_padding", 5.08), overlap_passes
        )
        if passes >= overlap_passes:
            diagnostics.warnings.append(
                f"Sheet '{sheet}': overlap resolution reached max passes."
            )

    # ---- Nets -----------------------------------------------------------
    nets = [
        KiCadNet(
            name=n["name"],
            kind=n.get("kind", "signal"),
            members=list(n.get("members", [])),
        )
        for n in ir.get("nets", []) if isinstance(n, dict)
    ]

    target = KiCadTarget(
        project_name=project_name,
        output_dir=str(output_dir),
        schematic_file=str(output_dir / f"{project_name}.kicad_sch"),
        project_file=str(output_dir / f"{project_name}.kicad_pro"),
    )

    return KiCadExecutionPlan(
        schema_version=KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
        request_id=request_id,
        target=target,
        symbols=symbols,
        nets=nets,
        diagnostics=diagnostics,
    )


# ---------------------------------------------------------------------------
# Internal: position resolution adapted for IR input
# ---------------------------------------------------------------------------

def _resolve_position(
    *,
    ir: dict[str, Any],
    comp: dict[str, Any],
    index: int,
    origin_x: float, origin_y: float,
    pitch_x: float, pitch_y: float,
    columns: int,
    block_x: dict[str, float],
    block_y: dict[str, float],
    block_slot: dict[str, int],
    block_cursor_y: dict[str, float],
    lib_id: str,
) -> layout_engine.KiCadPoint:
    """Resolve KiCadPoint for a single component, preferring configured position."""
    ref = comp.get("ref", "")
    role = comp.get("role", "")
    topology = ir.get("topology", "")

    # 1. Configured position (exact override from layout profiles).
    configured = layout_engine.configured_schematic_position(topology, ref)
    if configured is not None:
        return configured

    # 2. Auto-position inside a wiring block.
    block = layout_engine._resolve_block(role)
    if block and block in block_x and block in block_y:
        return layout_engine._auto_position(
            ref=ref,
            role=role,
            lib_id=lib_id,
            block_x=block_x,
            block_y=block_y,
            block_slot=block_slot,
            block_cursor_y=block_cursor_y,
        )

    # 3. Grid fallback.
    col = index % columns
    row = index // columns
    return layout_engine.KiCadPoint(
        x=layout_engine._snap(origin_x + col * pitch_x),
        y=layout_engine._snap(origin_y - row * pitch_y),
        rotation=layout_engine.configured_role_rotation(role),
    )
