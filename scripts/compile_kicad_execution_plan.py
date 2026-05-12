#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from env_utils import env, to_int_env


MODEL_SCHEMA_VERSION = 'circuit-model.v1'
NETLIST_SCHEMA_VERSION = 'netlist.v1'
KICAD_PLAN_SCHEMA_VERSION = 'kicad-execution-plan.v1'


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


def normalize_net_kind(name: str) -> str:
    normalized = name.strip().upper()
    if normalized in {'GND', 'AGND', 'DGND', 'PGND', 'SGND'}:
        return 'ground'
    if normalized.startswith('+') or any(token in normalized for token in ('VCC', 'VDD', 'VIN', 'VOUT', 'VBAT', 'PWR')):
        return 'power'
    return 'signal'


def to_float_env(name: str, fallback: float) -> float:
    raw = env(name)
    if not raw:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def symbol_mapping_for(component: dict[str, Any]) -> tuple[str, str, list[str]]:
    role = str(component.get('role', '')).strip().lower()
    ref = str(component.get('ref', '')).strip().upper()
    value = str(component.get('value', '')).strip().lower()
    selected = component.get('selected_part', {})
    package = str(selected.get('package', '') if isinstance(selected, dict) else '').strip()
    notes: list[str] = []

    if ref.startswith('R') or 'resistor' in role or value.endswith('r') or 'ohm' in value:
        return 'Device:R', package, notes
    if ref.startswith('C') or 'capacitor' in role or value.endswith('f'):
        return 'Device:C', package, notes
    if 'indicator' in role or 'led' in role or ref.startswith('LED'):
        return 'Device:LED', package, notes
    if ('esp32' in role or 'esp32' in value) and any(token in role for token in ('bare', 'chip', 'qfn', '裸')):
        notes.append('Mapped ESP32-C3 bare-chip role to KiCad official MCU_Espressif:ESP32-C3 symbol.')
        return 'MCU_Espressif:ESP32-C3', package or 'Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.7x3.7mm', notes
    if 'crystal' in role or 'xtal' in role or ref.startswith('Y'):
        return 'Device:Crystal', package, notes
    if 'esp32' in role or 'esp32' in value:
        notes.append('Mapped ESP32-C3 role to local AIAgent:ESP32_C3_Module placeholder symbol.')
        return 'AIAgent:ESP32_C3_Module', package, notes
    if ref.startswith('SW') or 'button' in role or 'switch' in role or 'boot' in role or 'reset' in role:
        return 'Switch:SW_Push', package, notes
    if 'antenna' in role:
        return 'Connector:Conn_Coaxial', package or 'Connector_Coaxial:SMA_Amphenol_132134-10_Vertical', notes
    if ref.startswith('J') or 'connector' in role or 'header' in role:
        if 'usb' in role:
            return 'Connector_Generic:Conn_01x04', package or 'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical', notes
        if 'uart' in role or 'programming' in role:
            return 'Connector_Generic:Conn_01x04', package or 'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical', notes
        notes.append('Mapped connector role to local AIAgent:Conn_01x04 placeholder symbol.')
        return 'AIAgent:Conn_01x04', package, notes
    if ref.startswith('L') or 'inductor' in role:
        return 'Device:L', package, notes
    if ref.startswith('D') or 'diode' in role:
        return 'Device:D', package, notes
    if 'buck' in role or ref.startswith('U'):
        notes.append('Mapped complex regulator role to local AIAgent:Buck_Regulator placeholder symbol.')
        return 'AIAgent:Buck_Regulator', package, notes

    notes.append(f'Mapped unknown role "{role}" to local AIAgent:Generic_2Pin placeholder symbol.')
    return 'AIAgent:Generic_2Pin', package, notes


def build_netlist_from_circuit_model(model: dict[str, Any]) -> dict[str, Any]:
    pin_map: dict[str, list[dict[str, str]]] = {}
    netlist_nets: list[dict[str, Any]] = []
    for net in model.get('nets', []):
        if not isinstance(net, dict):
            continue
        name = str(net.get('name', '')).strip()
        members = [str(item).strip() for item in net.get('members', []) if str(item).strip()]
        for member in members:
            if '.' not in member:
                continue
            ref, pin = member.split('.', 1)
            pin_map.setdefault(ref, []).append({'pin': pin, 'net': name, 'pin_name': ''})
        netlist_nets.append({'name': name, 'kind': normalize_net_kind(name), 'members': members})

    components: list[dict[str, Any]] = []
    for component in model.get('components', []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get('ref', '')).strip()
        selected = component.get('selected_part', {})
        if not isinstance(selected, dict):
            selected = {}
        components.append(
            {
                'ref': ref,
                'role': str(component.get('role', '')),
                'value': str(component.get('value', '')),
                'part': {
                    'part_id': str(selected.get('part_id', '')),
                    'display_name': str(selected.get('display_name', '')),
                    'library_uuid': str(selected.get('library_uuid', '')),
                    'symbol_uuid': str(selected.get('symbol_uuid', '')),
                    'pin_count': int(selected.get('pin_count', 0) or 0),
                    'named_pin_count': int(selected.get('named_pin_count', 0) or 0),
                },
                'pins': sorted(pin_map.get(ref, []), key=lambda item: item['pin']),
                'availability_status': str(component.get('availability_status', 'unknown')),
            }
        )

    return {
        'schema_version': NETLIST_SCHEMA_VERSION,
        'request_id': str(model.get('request_id', '')),
        'project_id': str(model.get('project_id', '')),
        'source_model': {
            'schema_version': str(model.get('schema_version', '')),
            'request_id': str(model.get('request_id', '')),
        },
        'components': components,
        'nets': netlist_nets,
    }


def _resolve_block(role: str) -> str:
    from schematic_layout_rules import build_default_layout_rules, _resolve_wiring_block
    return _resolve_wiring_block(role, build_default_layout_rules().block_layout)


_KNOWN_SYMBOL_SIZES: dict[str, tuple[float, float]] = {
    'AIAgent:ESP32_C3_Module': (35.56, 38.1),
    'AIAgent:ESP32_C3_Bare_QFN32': (45.72, 55.88),
    'AIAgent:Buck_Regulator': (22.86, 17.78),
    'AIAgent:Conn_01x04': (15.24, 17.78),
    'AIAgent:Generic_2Pin': (12.7, 10.16),
    'MCU_Espressif:ESP32-C3': (50.8, 55.88),
    'Connector:USB_C_Receptacle': (20.32, 17.78),
}


def _estimate_symbol_size(lib_id: str) -> tuple[float, float]:
    """Estimate symbol width/height in mm from real KiCad pin positions."""
    if lib_id in _KNOWN_SYMBOL_SIZES:
        return _KNOWN_SYMBOL_SIZES[lib_id]

    from kicad_project_writer import parse_symbol_pin_map
    pins = parse_symbol_pin_map(lib_id)
    if not pins:
        return 12.7, 10.16
    xs = [p['x'] for p in pins.values()]
    ys = [p['y'] for p in pins.values()]
    if not xs:
        return 12.7, 10.16
    w = max(xs) - min(xs) + 7.62
    h = max(ys) - min(ys) + 7.62
    return max(w, 10.0), max(h, 8.0)


_GRID = 2.54

def _snap(value: float) -> float:
    return round(value / _GRID) * _GRID


_BLOCK_GAP = 20.32
_VSLOT_PITCH = 17.78
_LAYOUT_ORIGIN_X = 35.56
_LAYOUT_ORIGIN_Y = 38.1
_BLOCK_FLOW = ['power', 'indicator', 'reset', 'mcu', 'boot', 'io']

def _compute_block_layout(
    components: list[tuple[str, str, str]],
) -> dict[str, tuple[float, float]]:
    """Two-pass auto-layout: group by block, measure symbol widths, place columns.

    Args:
        components: list of (ref, role, lib_id) tuples.

    Returns:
        Dict mapping block_name → (center_x, next_y_slot).
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

    block_order = [b for b in _BLOCK_FLOW if b in blocks]
    for b in blocks:
        if b not in block_order:
            block_order.append(b)

    layout: dict[str, tuple[float, float]] = {}
    cursor = _LAYOUT_ORIGIN_X
    for block in block_order:
        half_w = block_widths[block] / 2.0
        center_x = _snap(cursor + half_w)
        layout[block] = (center_x, _LAYOUT_ORIGIN_Y)
        cursor = _snap(cursor + block_widths[block] + _BLOCK_GAP)
    return layout


_ROLE_ROTATION: dict[str, float] = {
    'power_indicator': 90.0,
}


def _auto_position(
    ref: str, role: str, lib_id: str,
    block_x: dict[str, float], block_slot: dict[str, int],
) -> KiCadPoint:
    block = _resolve_block(role)
    x = block_x.get(block, _LAYOUT_ORIGIN_X)
    slot = block_slot.get(block, 0)
    block_slot[block] = slot + 1
    _, h = _estimate_symbol_size(lib_id)
    y = _snap(_LAYOUT_ORIGIN_Y + slot * max(_VSLOT_PITCH, h + 5.0))
    rotation = _ROLE_ROTATION.get(role, 0.0)
    return KiCadPoint(x=x, y=y, rotation=rotation)


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
    block_slot: dict[str, int] | None = None,
) -> KiCadPoint:
    ref = str(component.get('ref', '')).strip().upper()
    role = str(component.get('role', '')).strip().lower()
    lib_id = str(component.get('_lib_id', ''))

    if block_x is not None and block_slot is not None:
        return _auto_position(ref, role, lib_id, block_x, block_slot)

    col = index % columns
    row = index // columns
    return KiCadPoint(x=origin_x + col * pitch_x, y=origin_y + row * pitch_y, rotation=0.0)


def load_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    model = load_json_from_env('BRIDGE_CIRCUIT_MODEL_JSON', 'BRIDGE_CIRCUIT_MODEL_FILE')
    schema_version = str(model.get('schema_version', ''))
    if schema_version != MODEL_SCHEMA_VERSION:
        raise ValueError(f'Unsupported circuit schema_version: {schema_version}')

    try:
        netlist = load_json_from_env('BRIDGE_NETLIST_JSON', 'BRIDGE_NETLIST_FILE')
    except ValueError:
        netlist = build_netlist_from_circuit_model(model)
    if str(netlist.get('schema_version', '')) != NETLIST_SCHEMA_VERSION:
        raise ValueError(f'Unsupported netlist schema_version: {netlist.get("schema_version", "")}')
    return model, netlist


def compile_plan(model: dict[str, Any], netlist: dict[str, Any]) -> KiCadExecutionPlan:
    request_id = str(model.get('request_id') or netlist.get('request_id') or uuid.uuid4())
    project_name = slugify_project_name(env('KICAD_PROJECT_NAME', str(model.get('topology', '') or request_id)))
    output_root = Path(env('KICAD_OUTPUT_DIR', '.where/kicad-output'))
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

    # Compute block layout from real symbol dimensions
    comp_info = [(ref, role, lib_id) for ref, role, lib_id, _fp, _n in preflight]
    block_layout = _compute_block_layout(comp_info)
    block_x = {b: x for b, (x, _y) in block_layout.items()}
    block_slot: dict[str, int] = {}

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
            block_slot=block_slot,
        )
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

    return KiCadExecutionPlan(
        schema_version=KICAD_PLAN_SCHEMA_VERSION,
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
