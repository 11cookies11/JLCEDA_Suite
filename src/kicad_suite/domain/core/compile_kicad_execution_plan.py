#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ...shared.env_utils import env, to_int_env
from .kicad_layout_config import (
    configured_block_order,
    configured_role_rotation,
    layout_numeric_setting,
    load_layout_profiles,
)
from .net_utils import normalize_net_kind
from .netlist_builder import build_netlist
from ...shared.schema_versions import (
    CIRCUIT_MODEL_SCHEMA_VERSION,
    KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
    NETLIST_SCHEMA_VERSION,
)
from ...shared.env_utils import repo_root
from ...adapters.symbol_footprint_resolver import (
    footprint_exists,
    resolve_footprint as _resolve_footprint,
    symbol_mapping_for,
)

REPO_ROOT = repo_root()


@dataclass
class KiCadPoint:
    x: float
    y: float
    rotation: float = 0.0


@dataclass
class KiCadPin:
    number: str
    name: str
    net: str


@dataclass
class KiCadSymbol:
    ref: str
    role: str
    value: str
    lib_id: str
    footprint: str
    at: KiCadPoint
    pins: list[KiCadPin]
    notes: list[str] = field(default_factory=list)
    lcsc: str = ""
    mpn: str = ""
    manufacturer: str = ""


@dataclass
class KiCadNet:
    name: str
    kind: str
    members: list[str]


@dataclass
class KiCadTarget:
    project_name: str
    output_dir: str
    schematic_file: str
    project_file: str


@dataclass
class KiCadDiagnostics:
    warnings: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


@dataclass
class KiCadExecutionPlan:
    schema_version: str
    request_id: str
    target: KiCadTarget
    symbols: list[KiCadSymbol]
    nets: list[KiCadNet]
    diagnostics: KiCadDiagnostics


def load_json_from_env(json_name: str, file_name: str) -> dict[str, Any]:
    raw = env(json_name)
    if raw:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f'{json_name} must decode to a JSON object.')
        return payload

    file_path = env(file_name)
    if not file_path:
        raise ValueError(f'{json_name} or {file_name} is required.')
    with Path(file_path).open('r', encoding='utf-8') as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f'{file_name} must contain a JSON object.')
    return payload


def slugify_project_name(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', value.strip())
    cleaned = cleaned.strip('._-')
    return cleaned or 'kicad_agent_project'


def to_float_env(name: str, fallback: float) -> float:
    raw = env(name)
    if not raw:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def load_symbol_map() -> dict[str, Any]:
    """Return an empty compatibility config.

    The old shared symbol rule table has been retired. Resolution now comes
    from ``selected_part`` plus a small set of built-in role templates.
    """
    return {}


def build_netlist_from_circuit_model(model: dict[str, Any]) -> dict[str, Any]:
    return build_netlist(model)


def resolve_footprint(component_package: str, mapping_footprint: str) -> str:
    return _resolve_footprint(component_package, mapping_footprint)


def _resolve_block(role: str) -> str:
    from .schematic_layout_rules import build_default_layout_rules, _resolve_wiring_block
    topology = env('KICAD_TOPOLOGY', '')
    return _resolve_wiring_block(role, build_default_layout_rules(topology).block_layout)



def _estimate_symbol_size_from_pins(lib_id: str) -> tuple[float, float] | None:
    from ...adapters.kicad_symbol_library import parse_symbol_pin_map
    pins = parse_symbol_pin_map(lib_id)
    if not pins:
        return None
    xs = [p['x'] for p in pins.values()]
    ys = [p['y'] for p in pins.values()]
    if not xs:
        return None

    label_extension = 12.0
    body_pad = 3.81
    has_left_labels = any(p['rotation'] == 0 for p in pins.values())
    has_right_labels = any(p['rotation'] == 180 for p in pins.values())
    has_top_labels = any(p['rotation'] == 270 for p in pins.values())
    has_bottom_labels = any(p['rotation'] == 90 for p in pins.values())
    left_margin = label_extension if has_left_labels else body_pad
    right_margin = label_extension if has_right_labels else body_pad
    top_margin = label_extension if has_top_labels else body_pad
    bottom_margin = label_extension if has_bottom_labels else body_pad
    width = (max(xs) - min(xs)) + left_margin + right_margin
    height = (max(ys) - min(ys)) + top_margin + bottom_margin
    return max(width, 10.0), max(height, 8.0)


def _configured_symbol_size(lib_id: str) -> tuple[float, float] | None:
    return None


def _estimate_symbol_size(lib_id: str) -> tuple[float, float]:
    """Estimate symbol envelope from configured and real library geometry."""
    configured_size = _configured_symbol_size(lib_id)
    pin_size = _estimate_symbol_size_from_pins(lib_id)
    if configured_size and pin_size:
        return max(configured_size[0], pin_size[0]), max(configured_size[1], pin_size[1])
    if configured_size:
        return configured_size
    if pin_size:
        return pin_size
    return 12.7, 10.16


_GRID = 2.54

def _snap(value: float) -> float:
    return round(value / _GRID) * _GRID


_BLOCK_GAP = 30.48
_VSLOT_PITCH = 17.78
_LAYOUT_ORIGIN_X = 35.56
_LAYOUT_ORIGIN_Y = 38.1


def _compute_block_layout(
    components: list[tuple[str, str, str]],
) -> dict[str, tuple[float, float]]:
    """Two-pass auto-layout: group by block, measure symbol widths, place columns.

    Args:
        components: list of (ref, role, lib_id) tuples.

    Returns:
        Dict mapping block_name ->(center_x, next_y_slot).
    """
    blocks: dict[str, list[tuple[str, str]]] = {}
    for ref, role, lib_id in components:
        block = _resolve_block(role)
        blocks.setdefault(block, []).append((ref, lib_id))

    block_widths: dict[str, float] = {}
    for block, items in blocks.items():
        max_w = 0.0
        for _ref, lib_id in items:
            w, _h = _estimate_symbol_size(lib_id)
            if w > max_w:
                max_w = w
        block_widths[block] = max_w

    block_order = [b for b in configured_block_order() if b in blocks]
    for b in blocks:
        if b not in block_order:
            block_order.append(b)

    layout: dict[str, tuple[float, float]] = {}
    origin_x = layout_numeric_setting('origin_x', _LAYOUT_ORIGIN_X)
    origin_y = layout_numeric_setting('origin_y', _LAYOUT_ORIGIN_Y)
    block_gap = layout_numeric_setting('block_gap', _BLOCK_GAP)
    cursor = origin_x
    row_y = origin_y
    row_height = 0.0
    max_x = to_float_env('KICAD_SCH_MAX_X_MM', layout_numeric_setting('max_x', 260.0))
    row_gap = to_float_env('KICAD_SCH_ROW_GAP_MM', layout_numeric_setting('row_gap', 63.5))
    for block in block_order:
        half_w = block_widths[block] / 2.0
        block_height = max((_estimate_symbol_size(lib_id)[1] for _ref, lib_id in blocks[block]), default=20.0)
        if cursor > origin_x and cursor + block_widths[block] > max_x:
            cursor = origin_x
            row_y = _snap(row_y + max(row_height + 17.78, row_gap))
            row_height = 0.0
        center_x = _snap(cursor + half_w)
        layout[block] = (center_x, row_y)
        cursor = _snap(cursor + block_widths[block] + block_gap)
        row_height = max(row_height, block_height)
    return layout


def configured_topology_position(topology: str, ref: str) -> KiCadPoint | None:
    profiles = load_layout_profiles().get('profiles', {})
    if not isinstance(profiles, dict):
        return None
    profile = profiles.get(topology, {})
    if not isinstance(profile, dict):
        return None
    positions = profile.get('positions', {})
    if not isinstance(positions, dict):
        return None
    item = positions.get(ref)
    if not isinstance(item, dict):
        return None
    return KiCadPoint(
        x=float(item.get('x', 0.0)),
        y=float(item.get('y', 0.0)),
        rotation=float(item.get('rotation', 0.0)),
    )


def _auto_position(
    ref: str, role: str, lib_id: str,
    block_x: dict[str, float], block_y: dict[str, float], block_slot: dict[str, int],
    block_cursor_y: dict[str, float] | None = None,
) -> KiCadPoint:
    block = _resolve_block(role)
    x = block_x.get(block, layout_numeric_setting('origin_x', _LAYOUT_ORIGIN_X))
    base_y = block_y.get(block, layout_numeric_setting('origin_y', _LAYOUT_ORIGIN_Y))
    _, h = _estimate_symbol_size(lib_id)
    min_pitch = layout_numeric_setting('slot_pitch', _VSLOT_PITCH)
    gap = 12.0
    if block_cursor_y is not None:
        y = _snap(block_cursor_y.get(block, base_y))
        block_cursor_y[block] = y + max(min_pitch, h + gap)
    else:
        slot = block_slot.get(block, 0)
        block_slot[block] = slot + 1
        y = _snap(base_y + slot * max(min_pitch, h + gap))
    rotation = configured_role_rotation(role)
    return KiCadPoint(x=x, y=y, rotation=rotation)


def _symbol_bounds(symbol: KiCadSymbol, padding: float) -> tuple[float, float, float, float]:
    width, height = _estimate_symbol_size(symbol.lib_id)
    rotation = round(float(symbol.at.rotation or 0.0)) % 180
    if rotation == 90:
        width, height = height, width
    half_width = width / 2.0 + padding
    half_height = height / 2.0 + padding
    return (
        symbol.at.x - half_width,
        symbol.at.y - half_height,
        symbol.at.x + half_width,
        symbol.at.y + half_height,
    )


def _bounds_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    overlap_x = min(first[2], second[2]) - max(first[0], second[0])
    overlap_y = min(first[3], second[3]) - max(first[1], second[1])
    if overlap_x <= 0 or overlap_y <= 0:
        return None
    return overlap_x, overlap_y


def _symbol_sheet_name(symbol: KiCadSymbol, topology: str = '') -> str:
    from .schematic_layout_rules import build_default_layout_rules, _resolve_wiring_block
    block = _resolve_wiring_block(symbol.role, build_default_layout_rules(topology).block_layout)
    profiles = load_layout_profiles().get('profiles', {})
    profile = profiles.get(topology, {}) if isinstance(profiles, dict) else {}
    groups = profile.get('sheet_groups', []) if isinstance(profile, dict) else []
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            blocks = group.get('blocks', [])
            if isinstance(blocks, list) and block in {str(item) for item in blocks}:
                return str(group.get('name', '') or block)
    return block


def _resolve_symbol_overlaps_for_group(symbols: list[KiCadSymbol], padding: float, max_passes: int) -> int:
    moves = 0
    ordered = sorted(symbols, key=lambda symbol: (symbol.at.y, symbol.at.x, symbol.ref))
    for _pass_index in range(max_passes):
        changed = False
        for index, current in enumerate(ordered):
            current_bounds = _symbol_bounds(current, padding)
            for later in ordered[index + 1:]:
                later_bounds = _symbol_bounds(later, padding)
                overlap = _bounds_overlap(current_bounds, later_bounds)
                if overlap is None:
                    continue
                _overlap_x, overlap_y = overlap
                later.at.y = _snap(later.at.y + overlap_y + padding)
                changed = True
                moves += 1
        if not changed:
            break
        ordered = sorted(ordered, key=lambda symbol: (symbol.at.y, symbol.at.x, symbol.ref))
    return moves


def resolve_symbol_overlaps(symbols: list[KiCadSymbol], diagnostics: KiCadDiagnostics, topology: str = '') -> None:
    padding = layout_numeric_setting('symbol_padding', 6.35)
    max_passes = max(1, to_int_env('KICAD_SCH_OVERLAP_PASSES', 24))
    moves = 0
    by_sheet: dict[str, list[KiCadSymbol]] = {}
    for symbol in symbols:
        by_sheet.setdefault(_symbol_sheet_name(symbol, topology), []).append(symbol)
    for group_symbols in by_sheet.values():
        moves += _resolve_symbol_overlaps_for_group(group_symbols, padding, max_passes)
    if moves:
        diagnostics.warnings.append(f'Auto schematic layout resolved {moves} symbol overlap(s).')


def role_aware_position(
    model: dict[str, Any],
    component: dict[str, Any],
    index: int,
    origin_x: float,
    origin_y: float,
    pitch_x: float,
    pitch_y: float,
    columns: int,
    block_x: dict[str, float] | None = None,
    block_y: dict[str, float] | None = None,
    block_slot: dict[str, int] | None = None,
    block_cursor_y: dict[str, float] | None = None,
) -> KiCadPoint:
    ref = str(component.get('ref', '')).strip().upper()
    role = str(component.get('role', '')).strip().lower()
    lib_id = str(component.get('_lib_id', ''))
    topology = str(model.get('topology', '')).strip()

    configured_position = configured_topology_position(topology, ref)
    if configured_position is not None:
        return configured_position

    if block_x is not None and block_y is not None and block_slot is not None:
        return _auto_position(ref, role, lib_id, block_x, block_y, block_slot, block_cursor_y)

    col = index % columns
    row = index // columns
    return KiCadPoint(x=origin_x + col * pitch_x, y=origin_y + row * pitch_y, rotation=0.0)


def load_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    model = load_json_from_env('BRIDGE_CIRCUIT_MODEL_JSON', 'BRIDGE_CIRCUIT_MODEL_FILE')
    schema_version = str(model.get('schema_version', ''))
    if schema_version != CIRCUIT_MODEL_SCHEMA_VERSION:
        raise ValueError(f'Unsupported circuit schema_version: {schema_version}')

    try:
        netlist = load_json_from_env('BRIDGE_NETLIST_JSON', 'BRIDGE_NETLIST_FILE')
    except ValueError:
        netlist = build_netlist_from_circuit_model(model)
    if str(netlist.get('schema_version', '')) != NETLIST_SCHEMA_VERSION:
        raise ValueError(f'Unsupported netlist schema_version: {netlist.get("schema_version", "")}')
    return model, netlist


def _validate_symbol_libraries(preflight: list[tuple[str, str, str, str, list[str]]]) -> None:
    """Pre-flight check: verify all symbol libraries can be found on disk.

    If a library file is missing, symbol_block_for_lib_id falls back to a
    hardcoded 2-pin placeholder with pins at ±5.08mm, which silently breaks
    all wire-to-pin connections.  This catches that early.
    """
    from ...adapters.kicad_symbol_library import installed_symbol_block, kicad_symbol_roots

    checked: set[str] = set()
    missing_libs: dict[str, list[str]] = {}  # library ->[refs]

    for ref, _role, lib_id, _footprint, _notes in preflight:
        if lib_id in checked:
            continue
        if ':' not in lib_id:
            continue
        library, symbol_name = lib_id.split(':', 1)
        # Only check JLC-MCP libraries ???KiCad built-in libs use 'extends'
        # which installed_symbol_block doesn't resolve.
        if not library.startswith('JLC-MCP-'):
            continue
        if library in checked:
            continue
        checked.add(library)
        if installed_symbol_block(library, symbol_name):
            continue
        missing_libs.setdefault(library, []).append(ref)

    if not missing_libs:
        return

    roots = kicad_symbol_roots()
    root_lines = '\n'.join(f'    - {r}' for r in roots)
    missing_lines = '\n'.join(
        f'    {lib}.kicad_sym (needed by: {", ".join(refs[:5])}{"..." if len(refs) > 5 else ""})'
        for lib, refs in missing_libs.items()
    )
    raise RuntimeError(
        f'{len(missing_libs)} symbol library file(s) not found.\n'
        f'These will fall back to fake 2-pin symbols (±5.08mm),\n'
        f'breaking all wire-to-pin connections.\n\n'
        f'Missing libraries:\n{missing_lines}\n\n'
        f'Search paths (kicad_symbol_roots):\n{root_lines}\n\n'
        f'Fix: ensure the required .kicad_sym files exist in one of the search paths above.'
    )


def compile_plan(model: dict[str, Any], netlist: dict[str, Any]) -> KiCadExecutionPlan:
    request_id = str(model.get('request_id') or netlist.get('request_id') or uuid.uuid4())
    project_name = slugify_project_name(env('KICAD_PROJECT_NAME', str(model.get('topology', '') or request_id)))
    workspace = env('KICAD_WORKSPACE', '')
    if workspace:
        output_root = Path(workspace) / 'output'
    else:
        output_root = Path(env('KICAD_OUTPUT_DIR', 'tmp'))
    output_dir = output_root / project_name

    origin_x = to_float_env('KICAD_SCH_ORIGIN_X_MM', 38.1)
    origin_y = to_float_env('KICAD_SCH_ORIGIN_Y_MM', 38.1)
    pitch_x = to_float_env('KICAD_SCH_PITCH_X_MM', 25.4)
    pitch_y = to_float_env('KICAD_SCH_PITCH_Y_MM', 25.4)
    columns = max(1, to_int_env('KICAD_SCH_COLUMNS', 3))

    component_by_ref = {
        str(component.get('ref', '')).strip(): component
        for component in model.get('components', [])
        if isinstance(component, dict)
    }
    netlist_by_ref = {
        str(component.get('ref', '')).strip(): component
        for component in netlist.get('components', [])
        if isinstance(component, dict)
    }

    diagnostics = KiCadDiagnostics()

    # Pass 1: resolve lib_ids for auto-layout
    preflight: list[tuple[str, str, str, str, list[str]]] = []
    for ref in component_by_ref:
        component = component_by_ref[ref]
        lib_id, footprint, notes = symbol_mapping_for(component)
        role = str(component.get('role', ''))
        preflight.append((ref, role, lib_id, footprint, notes))
        component['_lib_id'] = lib_id  # stash for role_aware_position

    # Pre-flight symbol library validation: catch missing JLC-MCP libs early
    _validate_symbol_libraries(preflight)

    # Compute block layout from real symbol dimensions
    comp_info = [(ref, role, lib_id) for ref, role, lib_id, _fp, _n in preflight]
    block_layout = _compute_block_layout(comp_info)
    block_x = {b: x for b, (x, _y) in block_layout.items()}
    block_y = {b: y for b, (_x, y) in block_layout.items()}
    block_slot: dict[str, int] = {}
    block_cursor_y = dict(block_y)  # cumulative Y tracker per block for area-aware spacing

    # Pass 2: create symbols with auto positions
    symbols: list[KiCadSymbol] = []
    for ref, role, lib_id, footprint, notes in preflight:
        component = component_by_ref[ref]
        net_component = netlist_by_ref.get(ref, {})
        pins = [
            KiCadPin(
                number=str(pin.get('pin', '')),
                name=str(pin.get('pin_name', '')),
                net=str(pin.get('net', '')),
            )
            for pin in net_component.get('pins', [])
            if isinstance(pin, dict)
        ]
        if not pins:
            diagnostics.warnings.append(f'{ref} has no net pins; symbol will be placed without connectivity labels.')
        if lib_id.startswith('AIAgent:'):
            diagnostics.unsupported.append(f'{ref} uses placeholder symbol {lib_id}; replace with verified KiCad library symbol later.')
        exists = footprint_exists(footprint)
        if exists is False:
            if footprint:
                diagnostics.unsupported.append(f'{ref} footprint {footprint} was not found in the configured KiCad footprint libraries.')
            else:
                diagnostics.unsupported.append(f'{ref} has no KiCad footprint assignment.')

        at = role_aware_position(
            model=model,
            component=component,
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
        )
        sp = component.get('selected_part', {}) if isinstance(component.get('selected_part'), dict) else {}
        symbols.append(
            KiCadSymbol(
                ref=ref,
                role=role,
                value=str(component.get('value', '')),
                lib_id=lib_id,
                footprint=footprint,
                at=at,
                pins=pins,
                notes=notes,
                lcsc=str(sp.get('lcsc_id', '')),
                mpn=str(sp.get('mpn', '')),
                manufacturer=str(sp.get('manufacturer', '')),
            )
        )

    nets = [
        KiCadNet(
            name=str(net.get('name', '')),
            kind=str(net.get('kind', normalize_net_kind(str(net.get('name', ''))))),
            members=[str(member) for member in net.get('members', [])],
        )
        for net in netlist.get('nets', [])
        if isinstance(net, dict)
    ]

    resolve_symbol_overlaps(symbols, diagnostics, str(model.get('topology', '') or project_name))

    return KiCadExecutionPlan(
        schema_version=KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
        request_id=request_id,
        target=KiCadTarget(
            project_name=project_name,
            output_dir=str(output_dir),
            schematic_file=str(output_dir / f'{project_name}.kicad_sch'),
            project_file=str(output_dir / f'{project_name}.kicad_pro'),
        ),
        symbols=symbols,
        nets=nets,
        diagnostics=diagnostics,
    )


def write_output(plan: KiCadExecutionPlan) -> str:
    output_file = env('KICAD_EXECUTION_PLAN_FILE')
    if output_file:
        output_path = Path(output_file)
    else:
        output_path = Path(plan.target.output_dir) / 'kicad-execution-plan.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as file:
        json.dump(asdict(plan), file, ensure_ascii=False, indent=2)
        file.write('\n')
    return str(output_path)


def run() -> None:
    model, netlist = load_inputs()
    plan = compile_plan(model, netlist)
    output_file = write_output(plan)
    print(
        json.dumps(
            {
                'requestId': plan.request_id,
                'schemaVersion': plan.schema_version,
                'symbolCount': len(plan.symbols),
                'netCount': len(plan.nets),
                'outputFile': output_file,
                'projectFile': plan.target.project_file,
                'schematicFile': plan.target.schematic_file,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('Compile KiCad execution plan failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)
