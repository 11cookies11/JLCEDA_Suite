#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from .env_utils import env
from .schematic_layout_rules import BlockLayoutRule, build_default_layout_rules, _resolve_wiring_block


KICAD_PLAN_SCHEMA_VERSION = 'kicad-execution-plan.v1'
KICAD_SCHEMATIC_FILE_VERSION = '20250114'
REPO_ROOT = Path(__file__).resolve().parents[2]
SYMBOL_PIN_CACHE: dict[str, dict[str, dict[str, float]]] = {}


def new_uuid() -> str:
    return str(uuid.uuid4())


def load_plan() -> dict[str, Any]:
    raw = env('KICAD_EXECUTION_PLAN_JSON')
    if raw:
        payload = json.loads(raw)
    else:
        file_path = env('KICAD_EXECUTION_PLAN_FILE')
        if not file_path:
            raise ValueError('KICAD_EXECUTION_PLAN_JSON or KICAD_EXECUTION_PLAN_FILE is required.')
        with Path(file_path).open('r', encoding='utf-8') as file:
            payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError('KiCad execution plan must be a JSON object.')
    if str(payload.get('schema_version', '')) != KICAD_PLAN_SCHEMA_VERSION:
        raise ValueError(f'Unsupported KiCad plan schema_version: {payload.get("schema_version", "")}')
    return payload


def q(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def fmt(value: float) -> str:
    text = f'{float(value):.3f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def symbol_prefix(lib_id: str, ref: str) -> str:
    if ':' in lib_id:
        name = lib_id.split(':', 1)[1]
        if name:
            return name[0].upper()
    return ''.join(ch for ch in ref if ch.isalpha()).upper()[:1] or 'U'


def local_symbol_library(symbols: list[dict[str, Any]]) -> str:
    lib_ids = sorted({str(symbol.get('lib_id', 'AIAgent:Generic_2Pin')) for symbol in symbols})
    footprints_by_lib_id: dict[str, str] = {}
    for symbol in symbols:
        lib_id = str(symbol.get('lib_id', 'AIAgent:Generic_2Pin'))
        footprint = str(symbol.get('footprint', '')).strip()
        if footprint and lib_id not in footprints_by_lib_id:
            footprints_by_lib_id[lib_id] = footprint
    blocks = ['  (lib_symbols']
    for lib_id in lib_ids:
        blocks.append(symbol_block_with_default_footprint(symbol_block_for_lib_id(lib_id), footprints_by_lib_id.get(lib_id, '')))
    blocks.append('  )')
    return '\n'.join(blocks)


def kicad_symbol_roots() -> list[Path]:
    roots: list[Path] = [REPO_ROOT / 'resources' / 'kicad' / 'symbols']
    explicit = env('KICAD_SYMBOL_DIR')
    if explicit:
        roots.append(Path(explicit))
    extra = env('KICAD_EXTRA_SYMBOL_DIR')
    if extra:
        roots.extend(Path(item) for item in extra.split(';') if item.strip())
    # Check project-local libs directory (for custom generated symbols)
    output_root = env('KICAD_OUTPUT_DIR', '')
    if output_root:
        for candidate in [
            Path(output_root) / 'libs',
            Path(output_root).parent / 'libs',
        ]:
            if candidate.exists():
                roots.append(candidate)
    for base in (Path('D:/Program Files/KiCad'), Path('C:/Program Files/KiCad')):
        if base.exists():
            roots.extend(path / 'share' / 'kicad' / 'symbols' for path in sorted(base.glob('*'), reverse=True))
    return roots


def find_matching_paren(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return index
    return -1


def tokenize_sexpr(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in '()':
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            escaped = False
            while index < len(text):
                current = text[index]
                index += 1
                if escaped:
                    value.append(current)
                    escaped = False
                    continue
                if current == '\\':
                    escaped = True
                    continue
                if current == '"':
                    break
                value.append(current)
            tokens.append(''.join(value))
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in '()':
            index += 1
        tokens.append(text[start:index])
    return tokens


def parse_sexpr_tokens(tokens: list[str]) -> Any:
    def parse_at(index: int) -> tuple[Any, int]:
        if tokens[index] != '(':
            return tokens[index], index + 1
        index += 1
        items: list[Any] = []
        while index < len(tokens) and tokens[index] != ')':
            item, index = parse_at(index)
            items.append(item)
        return items, index + 1

    parsed, final_index = parse_at(0)
    if final_index != len(tokens):
        raise ValueError('Unexpected trailing tokens in S-expression.')
    return parsed


def parse_sexpr(text: str) -> Any:
    return parse_sexpr_tokens(tokenize_sexpr(text))


def sexpr_head(node: Any) -> str:
    if isinstance(node, list) and node:
        return str(node[0])
    return ''


def normalize_embedded_symbol_name(block: str, library: str, symbol_name: str) -> str:
    return block.replace(f'(symbol "{symbol_name}"', f'(symbol "{library}:{symbol_name}"', 1)


def load_installed_symbol(library: str, symbol_name: str) -> str:
    needle = f'(symbol "{symbol_name}"'
    for root in kicad_symbol_roots():
        symbol_file = root / f'{library}.kicad_sym'
        if not symbol_file.exists():
            continue
        text = symbol_file.read_text(encoding='utf-8')
        start = text.find(needle)
        if start < 0:
            continue
        end = find_matching_paren(text, start)
        if end < 0:
            continue
        block = text[start:end + 1]
        block = normalize_embedded_symbol_name(block, library, symbol_name)
        return '\n'.join(f'    {line}' if line.strip() else line for line in block.splitlines())
    return ''


def installed_symbol_block(library: str, symbol_name: str) -> str:
    needle = f'(symbol "{symbol_name}"'
    for root in kicad_symbol_roots():
        symbol_file = root / f'{library}.kicad_sym'
        if not symbol_file.exists():
            continue
        text = symbol_file.read_text(encoding='utf-8')
        start = text.find(needle)
        if start < 0:
            continue
        end = find_matching_paren(text, start)
        if end >= 0:
            return text[start:end + 1]
    return ''


def symbol_block_for_lib_id(lib_id: str) -> str:
    if ':' in lib_id:
        library, symbol_name = lib_id.split(':', 1)
        installed = load_installed_symbol(library, symbol_name)
        if installed:
            return installed

    fallback_prefixes = {
        'Connector_Generic:Conn_01x04': 'J',
        'Connector:Conn_Coaxial': 'J',
        'Switch:SW_Push': 'SW',
        'Device:Crystal': 'Y',
        'Device:LED': 'D',
        'Device:D': 'D',
        'Device:R': 'R',
        'Device:C': 'C',
        'Device:L': 'L',
        'power:PWR_FLAG': '#FLG',
    }
    return local_two_pin_symbol(lib_id, fallback_prefixes.get(lib_id, 'R'))


def symbol_block_with_default_footprint(block: str, footprint: str) -> str:
    if not footprint:
        return block
    lines = block.splitlines()

    # Replace existing Footprint property
    for index, line in enumerate(lines):
        if '(property "Footprint"' in line:
            lines[index] = re.sub(r'\(property "Footprint" "([^"]*)"', f'(property "Footprint" {q(footprint)}', line, count=1)
            return '\n'.join(lines)

    # No Footprint property — insert one after the Value property block
    result: list[str] = []
    depth = 0
    in_value = False
    inserted_after: int = -1
    for index, line in enumerate(lines):
        if not in_value and '(property "Value"' in line:
            in_value = True
            depth = 1
        elif in_value:
            depth += line.count('(') - line.count(')')
            if depth <= 0:
                inserted_after = index
                in_value = False
        result.append(line)
        if inserted_after == index:
            indent = line[:len(line) - len(line.lstrip())] if line.strip() else '      '
            result.append(f'{indent}(property "Footprint" {q(footprint)} (at 0 0 0)')
            result.append(f'{indent}  (hide yes)')
            result.append(f'{indent}  (effects (font (size 1.27 1.27)))')
            result.append(f'{indent})')
            inserted_after = -1

    return '\n'.join(result)


def parse_symbol_pin_map(lib_id: str) -> dict[str, dict[str, float]]:
    if lib_id in SYMBOL_PIN_CACHE:
        return SYMBOL_PIN_CACHE[lib_id]
    if ':' not in lib_id:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    library, symbol_name = lib_id.split(':', 1)
    block = installed_symbol_block(library, symbol_name) or symbol_block_for_lib_id(lib_id)
    if not block:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    try:
        tree = parse_sexpr(block)
    except Exception:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}

    pins: dict[str, dict[str, float]] = {}

    def visit(node: Any) -> None:
        if not isinstance(node, list) or not node:
            return
        if sexpr_head(node) == 'pin':
            at_data = next((child for child in node if sexpr_head(child) == 'at'), None)
            length_data = next((child for child in node if sexpr_head(child) == 'length'), None)
            number_data = next((child for child in node if sexpr_head(child) == 'number'), None)
            if isinstance(at_data, list) and len(at_data) >= 4 and isinstance(number_data, list) and len(number_data) >= 2:
                try:
                    number = str(number_data[1])
                    pins[number] = {
                        'x': float(at_data[1]),
                        'y': float(at_data[2]),
                        'rotation': float(at_data[3]),
                        'length': float(length_data[1]) if isinstance(length_data, list) and len(length_data) >= 2 else 0.0,
                    }
                except (TypeError, ValueError):
                    pass
        for child in node:
            visit(child)

    visit(tree)
    if not pins:
        extends = next((child[1] for child in tree if isinstance(child, list) and sexpr_head(child) == 'extends'), None)
        if isinstance(extends, str) and extends:
            parent_pins = parse_symbol_pin_map(f'{library}:{extends}')
            pins.update(parent_pins)
    SYMBOL_PIN_CACHE[lib_id] = pins
    return pins


def endpoint_from_pin(pin_data: dict[str, float], origin_x: float, origin_y: float, symbol_rotation: float = 0.0) -> tuple[float, float, float]:
    import math
    lx = float(pin_data.get('x', 0.0))
    ly = float(pin_data.get('y', 0.0))
    pin_rotation = float(pin_data.get('rotation', 0.0))
    theta = math.radians(symbol_rotation)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    rx = lx * cos_t - ly * sin_t
    ry = lx * sin_t + ly * cos_t
    x = origin_x + rx
    y = origin_y - ry
    direction = (pin_rotation + symbol_rotation) % 360.0
    if direction == 0.0 or direction == 360.0:
        return x, y, 180.0
    if direction == 180.0:
        return x, y, 0.0
    if direction == 90.0:
        return x, y, 90.0
    if direction == 270.0:
        return x, y, 270.0
    return x, y, 180.0


def local_two_pin_symbol(lib_id: str, reference_prefix: str) -> str:
    symbol_name = lib_id.split(':', 1)[-1]
    return f'''    (symbol {q(lib_id)}
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" {q(reference_prefix)} (at 0 3.81 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" {q(symbol_name)} (at 0 -3.81 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "{symbol_name}_0_1"
        (rectangle (start -2.54 1.27) (end 2.54 -1.27)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (pin passive line (at -5.08 0 0) (length 2.54)
          (name "1" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 5.08 0 180) (length 2.54)
          (name "2" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )'''


def pin_endpoint(symbol: dict[str, Any], pin_number: str) -> tuple[float, float, float]:
    at = symbol.get('at', {})
    x = float(at.get('x', 0.0))
    y = float(at.get('y', 0.0))
    rotation = float(at.get('rotation', 0.0))
    lib_id = str(symbol.get('lib_id', ''))
    pin = str(pin_number).strip().upper()

    pin_map = parse_symbol_pin_map(lib_id)
    pin_data = pin_map.get(pin_number) or pin_map.get(pin)
    if pin_data:
        return endpoint_from_pin(pin_data, x, y, rotation)

    if pin in {'2', 'K', 'C'}:
        return x + 5.08, y, 0.0
    return x - 5.08, y, 180.0


def label_shape(kind: str) -> str:
    if kind == 'ground':
        return 'input'
    if kind == 'power':
        return 'input'
    return 'bidirectional'


def label_token_shape(kind: str) -> str:
    if kind == 'ground':
        return 'input'
    if kind == 'power':
        return 'input'
    return 'bidirectional'


def net_kind_by_name(plan: dict[str, Any]) -> dict[str, str]:
    return {str(net.get('name', '')): str(net.get('kind', 'signal')) for net in plan.get('nets', []) if isinstance(net, dict)}


def render_symbol_instance(symbol: dict[str, Any], project_name: str) -> str:
    return render_symbol_instance_at_path(symbol, project_name, '/')


def render_symbol_instance_at_path(symbol: dict[str, Any], project_name: str, sheet_path: str) -> str:
    at = symbol.get('at', {})
    x = float(at.get('x', 0.0))
    y = float(at.get('y', 0.0))
    rotation = float(at.get('rotation', 0.0))
    ref = str(symbol.get('ref', 'U?'))
    lib_id = str(symbol.get('lib_id', 'AIAgent:Generic_2Pin'))
    value = str(symbol.get('value', ''))
    footprint = str(symbol.get('footprint', ''))
    pins = symbol.get('pins', [])
    if not isinstance(pins, list):
        pins = []

    pin_lines = []
    pin_numbers = [str(pin.get('number', '')) for pin in pins if isinstance(pin, dict) and str(pin.get('number', ''))]
    if not pin_numbers:
        pin_numbers = list(parse_symbol_pin_map(lib_id)) or ['1', '2']
    for pin_number in dict.fromkeys(pin_numbers):
        pin_lines.append(f'      (pin {q(pin_number)} (uuid {q(new_uuid())}))')

    ref_y = y - 7.62 if lib_id == 'MCU_Espressif:ESP32-C3' else y - 5.08
    value_y = y + 7.62 if lib_id == 'MCU_Espressif:ESP32-C3' else y + 5.08
    lcsc = str(symbol.get('lcsc', ''))
    mpn = str(symbol.get('mpn', ''))
    manufacturer = str(symbol.get('manufacturer', ''))
    extra_props = ""
    if lcsc:
        extra_props += f'\n      (property "LCSC" {q(lcsc)} (at 0 0 0)\n        (hide yes)\n        (effects (font (size 1.27 1.27)))\n      )'
    if mpn:
        extra_props += f'\n      (property "MPN" {q(mpn)} (at 0 0 0)\n        (hide yes)\n        (effects (font (size 1.27 1.27)))\n      )'
    if manufacturer:
        extra_props += f'\n      (property "Manufacturer" {q(manufacturer)} (at 0 0 0)\n        (hide yes)\n        (effects (font (size 1.27 1.27)))\n      )'
    return f'''  (symbol
    (lib_id {q(lib_id)})
    (at {fmt(x)} {fmt(y)} {fmt(rotation)})
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid {q(new_uuid())})
    (property "Reference" {q(ref)} (at {fmt(x)} {fmt(ref_y)} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Value" {q(value)} (at {fmt(x)} {fmt(value_y)} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Footprint" {q(footprint)} (at {fmt(x)} {fmt(y)} 0)
      (hide yes)
      (effects (font (size 1.27 1.27)))
    ){extra_props}
{chr(10).join(pin_lines)}
    (instances
      (project {q(project_name)}
        (path {q(sheet_path)}
          (reference {q(ref)})
          (unit 1)
        )
      )
    )
  )'''


def automatic_power_flags(plan: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for index, net in enumerate(plan.get('nets', []), start=1):
        if not isinstance(net, dict):
            continue
        name = str(net.get('name', '')).strip()
        kind = str(net.get('kind', '')).strip()
        if kind != 'ground' or not name:
            continue
        flags.append(
            {
                'ref': f'#FLG{index:02d}',
                'value': 'PWR_FLAG',
                'lib_id': 'power:PWR_FLAG',
                'footprint': '',
                'at': {'x': 30.48, 'y': 106.68 + index * 7.62, 'rotation': 0.0},
                'pins': [{'number': '1', 'net': name}],
            }
        )
    return flags


def symbol_by_ref(symbols: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(symbol.get('ref', '')).upper(): symbol for symbol in symbols}


def wire_segment(start: tuple[float, float], end: tuple[float, float]) -> str:
    return f'''  (wire (pts (xy {fmt(start[0])} {fmt(start[1])}) (xy {fmt(end[0])} {fmt(end[1])}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )'''


def wire_path(points: list[tuple[float, float]]) -> list[str]:
    blocks: list[str] = []
    for start, end in zip(points, points[1:]):
        if start == end:
            continue
        blocks.append(wire_segment(start, end))
    return blocks


def parse_member_ref_pin(member: str) -> tuple[str, str]:
    if '.' not in member:
        return '', ''
    ref, pin = member.split('.', 1)
    return ref.strip().upper(), pin.strip().upper()


def _route_l_shape(p1: tuple[float, float], p2: tuple[float, float]) -> list[str]:
    if p1 == p2:
        return []
    return wire_path([p1, (p2[0], p1[1]), p2])


def _route_bus(points: list[tuple[float, float]], margin: float = 7.62) -> list[str]:
    if len(points) < 2:
        return []
    if len(points) == 2:
        return _route_l_shape(points[0], points[1])
    bus_x = min(p[0] for p in points) - margin
    sorted_pts = sorted(points, key=lambda p: p[1])
    segments: list[str] = []
    segments.extend(wire_path([
        sorted_pts[0],
        (bus_x, sorted_pts[0][1]),
        (bus_x, sorted_pts[1][1]),
        sorted_pts[1],
    ]))
    for i in range(2, len(sorted_pts)):
        prev_y = sorted_pts[i - 1][1]
        curr = sorted_pts[i]
        segments.extend(wire_path([
            (bus_x, prev_y),
            (bus_x, curr[1]),
            curr,
        ]))
    return segments


def _route_intra_block(
    ref_pins: list[tuple[str, str, tuple[float, float]]],
) -> list[str]:
    if len(ref_pins) < 2:
        return []
    points = [ep for _, _, ep in ref_pins]
    return _route_bus(points)


def intra_module_wiring(
    symbols: list[dict[str, Any]],
    nets: list[dict[str, Any]],
    layout_rules: BlockLayoutRule | None = None,
) -> tuple[list[str], set[tuple[str, str]]]:
    if layout_rules is None:
        layout_rules = build_default_layout_rules().block_layout
    by_ref = symbol_by_ref(symbols)
    blocks: list[str] = []
    suppress_labels: set[tuple[str, str]] = set()

    ref_to_block: dict[str, str] = {}
    for ref, symbol in by_ref.items():
        lib_id = str(symbol.get('lib_id', ''))
        if lib_id == 'power:PWR_FLAG':
            continue
        role = str(symbol.get('role', '')).strip().lower()
        ref_to_block[ref] = _resolve_wiring_block(role, layout_rules)

    for net in nets:
        net_kind = str(net.get('kind', 'signal'))
        is_power_rail = net_kind in ('power', 'ground')
        members = net.get('members', [])
        if not isinstance(members, list):
            continue

        parsed: list[tuple[str, str, str]] = []
        for member in members:
            if not isinstance(member, str):
                continue
            ref, pin = parse_member_ref_pin(member)
            if ref in ref_to_block and pin:
                parsed.append((ref, pin, ref_to_block[ref]))

        if len(parsed) < 2:
            continue

        block_groups: dict[str, list[tuple[str, str]]] = {}
        for ref, pin, block_name in parsed:
            block_groups.setdefault(block_name, []).append((ref, pin))

        cross_module = len(block_groups) > 1
        if is_power_rail or cross_module:
            continue

        for _block_name, group in block_groups.items():
            if len(group) < 2:
                continue
            group.sort(key=lambda rp: pin_endpoint(by_ref[rp[0]], rp[1])[1])
            ref_pins: list[tuple[str, str, tuple[float, float]]] = []
            for ref, pin in group:
                x, y, _direction = pin_endpoint(by_ref[ref], pin)
                ref_pins.append((ref, pin, (x, y)))
            blocks.extend(_route_intra_block(ref_pins))
            if cross_module:
                for ref, pin in group[1:]:
                    suppress_labels.add((ref, pin))
            else:
                for ref, pin in group:
                    suppress_labels.add((ref, pin))

    return blocks, suppress_labels


def render_connectivity(
    plan: dict[str, Any],
    symbols: list[dict[str, Any]] | None = None,
    force_global_nets: set[str] | None = None,
) -> str:
    kind_map = net_kind_by_name(plan)
    blocks: list[str] = []
    if symbols is None:
        symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
    if force_global_nets is None:
        force_global_nets = set()
    nets = plan.get('nets', [])
    direct_blocks, suppress_labels = intra_module_wiring(symbols, nets)
    blocks.extend(direct_blocks)
    rendered_labels: set[tuple[str, str, float, float]] = set()
    for symbol in symbols:
        ref = str(symbol.get('ref', '')).upper()
        pins = symbol.get('pins', [])
        if not isinstance(pins, list):
            continue
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            net_name = str(pin.get('net', '')).strip()
            pin_number = str(pin.get('number', '')).strip()
            if not net_name or not pin_number:
                continue
            if (ref, pin_number) in suppress_labels and net_name not in force_global_nets:
                continue
            x, y, direction = pin_endpoint(symbol, pin_number)
            stub = 3.81
            label_x = x - stub if direction == 180.0 else x + stub if direction == 0.0 else x
            label_y = y + stub if direction == 90.0 else y - stub if direction == 270.0 else y
            label_key = (net_name, round(label_x, 3), round(label_y, 3))
            kind = kind_map.get(net_name, 'signal')
            justify = 'right' if direction == 180.0 else 'left' if direction == 0.0 else 'center'
            justify_effect = f' (justify {justify})' if justify != 'center' else ''
            blocks.append(f'''  (wire (pts (xy {fmt(x)} {fmt(y)}) (xy {fmt(label_x)} {fmt(label_y)}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )''')
            if label_key in rendered_labels:
                continue
            rendered_labels.add(label_key)
            if net_name in force_global_nets:
                blocks.append(render_hierarchical_label(net_name, kind, label_x, label_y, 0.0, justify=justify))
            elif kind in {'ground', 'power'}:
                blocks.append(f'''  (global_label {q(net_name)} (shape {label_shape(kind)}) (at {fmt(label_x)} {fmt(label_y)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
            else:
                blocks.append(f'''  (label {q(net_name)} (at {fmt(label_x)} {fmt(label_y)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
        if str(symbol.get('lib_id', '')) == 'MCU_Espressif:ESP32-C3':
            connected_pins = {str(pin.get('number', '')).strip() for pin in pins if isinstance(pin, dict)}
            for pin_number in sorted(parse_symbol_pin_map('MCU_Espressif:ESP32-C3'), key=lambda value: int(value) if value.isdigit() else value):
                if pin_number in connected_pins:
                    continue
                x, y, _direction = pin_endpoint(symbol, pin_number)
                blocks.append(f'''  (no_connect (at {fmt(x)} {fmt(y)})
    (uuid {q(new_uuid())})
  )''')
    return '\n'.join(blocks)


def sanitize_sheet_name(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', value.strip().lower())
    cleaned = cleaned.strip('._-')
    return cleaned or 'sheet'


def load_layout_profile_config() -> dict[str, Any]:
    path = Path(env('KICAD_LAYOUT_PROFILES_FILE', str(REPO_ROOT / 'config' / 'kicad-layout-profiles.json')))
    if not path.exists():
        return {}
    try:
        with path.open('r', encoding='utf-8') as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def topology_from_plan(plan: dict[str, Any]) -> str:
    target = plan.get('target', {})
    if isinstance(target, dict):
        return str(target.get('project_name', '')).strip()
    return ''


def configured_sheet_groups(topology: str) -> list[dict[str, Any]]:
    config = load_layout_profile_config()
    profiles = config.get('profiles', {})
    profile = profiles.get(topology, {}) if isinstance(profiles, dict) else {}
    groups = profile.get('sheet_groups', []) if isinstance(profile, dict) else []
    return [group for group in groups if isinstance(group, dict)]


def symbol_block(symbol: dict[str, Any]) -> str:
    role = str(symbol.get('role', '')).strip().lower()
    return _resolve_wiring_block(role, build_default_layout_rules().block_layout)


def group_symbols_by_sheet(symbols: list[dict[str, Any]], topology: str = '') -> dict[str, list[dict[str, Any]]]:
    pages: dict[str, list[dict[str, Any]]] = {}
    order = build_default_layout_rules().block_layout.block_order
    order_index = {name: index for index, name in enumerate(order)}
    block_to_sheet: dict[str, str] = {}
    sheet_order: list[str] = []
    for group in configured_sheet_groups(topology):
        name = sanitize_sheet_name(str(group.get('name', '')).strip())
        blocks = group.get('blocks', [])
        if not name or not isinstance(blocks, list):
            continue
        sheet_order.append(name)
        for block in blocks:
            if str(block):
                block_to_sheet[str(block)] = name
    for symbol in symbols:
        block = symbol_block(symbol)
        sheet = block_to_sheet.get(block, block)
        pages.setdefault(sheet, []).append(symbol)
    if sheet_order:
        for sheet in pages:
            if sheet not in sheet_order:
                sheet_order.append(sheet)
        return dict(sorted(pages.items(), key=lambda item: (sheet_order.index(item[0]) if item[0] in sheet_order else 999, item[0])))
    return dict(sorted(pages.items(), key=lambda item: (order_index.get(item[0], 999), item[0])))


def symbol_ref_to_sheet(pages: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for sheet_name, symbols in pages.items():
        for symbol in symbols:
            ref = str(symbol.get('ref', '')).strip().upper()
            if ref:
                refs[ref] = sheet_name
    return refs


def page_cross_nets(plan: dict[str, Any], ref_to_sheet: dict[str, str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for net in plan.get('nets', []):
        if not isinstance(net, dict):
            continue
        name = str(net.get('name', '')).strip()
        if not name:
            continue
        pages: set[str] = set()
        for member in net.get('members', []):
            if not isinstance(member, str):
                continue
            ref, _pin = parse_member_ref_pin(member)
            if ref in ref_to_sheet:
                pages.add(ref_to_sheet[ref])
        if len(pages) > 1:
            result[name] = pages
    return result


def shifted_symbols_for_page(symbols: list[dict[str, Any]], origin_x: float = 50.8, origin_y: float = 50.8) -> list[dict[str, Any]]:
    positioned = [symbol for symbol in symbols if isinstance(symbol.get('at', {}), dict)]
    if not positioned:
        return symbols
    min_x = min(float(symbol.get('at', {}).get('x', origin_x)) for symbol in positioned)
    min_y = min(float(symbol.get('at', {}).get('y', origin_y)) for symbol in positioned)
    dx = origin_x - min_x
    dy = origin_y - min_y
    shifted: list[dict[str, Any]] = []
    for symbol in symbols:
        copy = dict(symbol)
        at = dict(symbol.get('at', {})) if isinstance(symbol.get('at', {}), dict) else {}
        at['x'] = float(at.get('x', origin_x)) + dx
        at['y'] = float(at.get('y', origin_y)) + dy
        copy['at'] = at
        shifted.append(copy)
    return shifted


def render_sheet_instances(sheet_pages: list[dict[str, Any]]) -> str:
    lines = ['  (sheet_instances', '    (path "/" (page "1"))']
    for index, page in enumerate(sheet_pages, start=2):
        lines.append(f'    (path {q(page["path"])} (page {q(str(index))}))')
    lines.append('  )')
    return '\n'.join(lines)


def render_schematic(plan: dict[str, Any]) -> str:
    symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
    symbols.extend(automatic_power_flags(plan))
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    instances = '\n'.join(render_symbol_instance(symbol, project_name) for symbol in symbols)
    connectivity = render_connectivity(plan, symbols)
    return f'''(kicad_sch
  (version {KICAD_SCHEMATIC_FILE_VERSION})
  (generator "kicad-agent-suite")
  (generator_version "10.0")
  (uuid {q(new_uuid())})
  (paper "A4")
{local_symbol_library(symbols)}
{instances}
{connectivity}
  (sheet_instances
    (path "/" (page "1"))
  )
)'''


def render_hierarchical_label(name: str, kind: str, x: float, y: float, angle: float, justify: str = 'left') -> str:
    justify_effect = f' (justify {justify})' if justify != 'center' else ''
    return f'''  (hierarchical_label {q(name)} (shape {label_token_shape(kind)}) (at {fmt(x)} {fmt(y)} {fmt(angle)})
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )'''


def render_sheet_pin(name: str, kind: str, x: float, y: float, angle: float) -> str:
    return f'''    (pin {q(name)} {label_token_shape(kind)} (at {fmt(x)} {fmt(y)} {fmt(angle)})
      (effects (font (size 1.27 1.27)))
      (uuid {q(new_uuid())})
    )'''


def render_root_sheet(page: dict[str, Any], kind_map: dict[str, str]) -> str:
    x = float(page['x'])
    y = float(page['y'])
    w = float(page['w'])
    h = float(page['h'])
    pins = []
    root_labels = []
    for index, net_name in enumerate(page['pins']):
        pin_y = y + 7.62 + index * 7.62
        pin_x = x + w
        kind = kind_map.get(net_name, 'signal')
        pins.append(render_sheet_pin(net_name, kind, pin_x, pin_y, 0.0))
        root_labels.append(wire_segment((pin_x, pin_y), (pin_x + 5.08, pin_y)))
        root_labels.append(f'''  (global_label {q(net_name)} (shape {label_shape(kind)}) (at {fmt(pin_x + 5.08)} {fmt(pin_y)} 0)
    (effects (font (size 1.27 1.27)) (justify left))
    (uuid {q(new_uuid())})
  )''')
    return f'''  (sheet
    (at {fmt(x)} {fmt(y)})
    (size {fmt(w)} {fmt(h)})
    (stroke (width 0.1524) (type solid))
    (fill (color 0 0 0 0.0000))
    (uuid {q(page['uuid'])})
    (property "Sheetname" {q(page['name'])} (at {fmt(x)} {fmt(y - 1.27)} 0)
      (effects (font (size 1.27 1.27)) (justify left bottom))
    )
    (property "Sheetfile" {q(page['file'])} (at {fmt(x)} {fmt(y + h + 1.27)} 0)
      (effects (font (size 1.27 1.27)) (justify left top))
    )
{chr(10).join(pins)}
  )
{chr(10).join(root_labels)}'''


def render_root_schematic(plan: dict[str, Any], sheet_pages: list[dict[str, Any]]) -> str:
    kind_map = net_kind_by_name(plan)
    sheets = '\n'.join(render_root_sheet(page, kind_map) for page in sheet_pages)
    return f'''(kicad_sch
  (version {KICAD_SCHEMATIC_FILE_VERSION})
  (generator "kicad-agent-suite")
  (generator_version "10.0")
  (uuid {q(new_uuid())})
  (paper "A4")
  (lib_symbols)
{sheets}
{render_sheet_instances(sheet_pages)}
)'''


def render_child_schematic(
    plan: dict[str, Any],
    page: dict[str, Any],
    symbols: list[dict[str, Any]],
    sheet_pages: list[dict[str, Any]],
    cross_nets: set[str],
) -> str:
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    page_symbols = shifted_symbols_for_page(symbols)
    instances = '\n'.join(render_symbol_instance_at_path(symbol, project_name, page['path']) for symbol in page_symbols)
    connectivity = render_connectivity(plan, page_symbols, force_global_nets=cross_nets)
    return f'''(kicad_sch
  (version {KICAD_SCHEMATIC_FILE_VERSION})
  (generator "kicad-agent-suite")
  (generator_version "10.0")
  (uuid {q(new_uuid())})
  (paper "A4")
{local_symbol_library(page_symbols)}
{instances}
{connectivity}
{render_sheet_instances(sheet_pages)}
)'''


def write_hierarchical_project(plan: dict[str, Any], output_dir: Path, schematic_file: Path) -> dict[str, Any]:
    base_symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    pages = group_symbols_by_sheet(base_symbols, project_name)
    ref_to_sheet = symbol_ref_to_sheet(pages)
    cross_net_pages = page_cross_nets(plan, ref_to_sheet)

    # Collect power/ground nets that are entirely local to a single sheet.
    # These need sheet pins so EasyEDA can map global labels through the hierarchy.
    net_kind_lookup = {str(net.get('name', '')): str(net.get('kind', 'signal')) for net in plan.get('nets', []) if isinstance(net, dict)}
    local_power_nets: dict[str, set[str]] = {}
    for net in plan.get('nets', []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get('name', '')).strip()
        kind = str(net.get('kind', 'signal'))
        if kind not in ('power', 'ground') or net_name in cross_net_pages:
            continue
        sheet_members: set[str] = set()
        for member in net.get('members', []):
            if not isinstance(member, str):
                continue
            ref, _pin = parse_member_ref_pin(member)
            if ref in ref_to_sheet:
                sheet_members.add(ref_to_sheet[ref])
        if len(sheet_members) == 1:
            sheet_name = next(iter(sheet_members))
            local_power_nets.setdefault(sheet_name, set()).add(net_name)

    sheet_pages: list[dict[str, Any]] = []
    cursor_x = 25.4
    cursor_y = 25.4
    max_x = 210.0
    for index, (name, symbols) in enumerate(pages.items(), start=1):
        page_nets = sorted(set(net for net, net_pages in cross_net_pages.items() if name in net_pages) | local_power_nets.get(name, set()))
        height = max(20.32, 15.24 + len(page_nets) * 7.62)
        sheet_name = sanitize_sheet_name(name)
        file_name = f'{index:02d}_{sheet_name}.kicad_sch'
        if cursor_x > max_x:
            cursor_x = 25.4
            cursor_y += 45.72
        sheet_uuid = new_uuid()
        sheet_pages.append(
            {
                'name': name,
                'file': file_name,
                'path': f'/{sheet_uuid}',
                'uuid': sheet_uuid,
                'x': cursor_x,
                'y': cursor_y,
                'w': 48.26,
                'h': height,
                'pins': page_nets,
                'symbols': symbols,
            }
        )
        cursor_x += 66.04

    schematic_file.write_text(render_root_schematic(plan, sheet_pages) + '\n', encoding='utf-8')
    for page in sheet_pages:
        child_path = schematic_file.parent / page['file']
        child_path.write_text(
            render_child_schematic(
                plan=plan,
                page=page,
                symbols=page['symbols'],
                sheet_pages=sheet_pages,
                cross_nets=set(page['pins']),
            ) + '\n',
            encoding='utf-8',
        )

    return {
        'sheet_count': len(sheet_pages) + 1,
        'root_schematic_file': str(schematic_file),
        'sheet_files': [str(schematic_file.parent / page['file']) for page in sheet_pages],
    }


def render_project(output_dir: str | Path | None = None) -> str:
    project_json: dict[str, Any] = {
        'board': {
            'design_settings': {
                'defaults': {},
                'rules': {},
            }
        },
        'meta': {
            'version': 1,
        },
        'net_settings': {
            'classes': [],
            'meta': {
                'version': 3,
            },
        },
        'schematic': {
            'drawing': {},
            'legacy_lib_dir': '',
            'legacy_lib_list': [],
        },
    }

    # Add project-local JLC libraries if they exist
    if output_dir:
        output_path = Path(output_dir)
        pinned_fp: list[dict[str, str]] = []
        pinned_sym: list[dict[str, str]] = []

        jlc_fp_dir = _find_jlc_lib_dir(output_path)
        jlc_sym_file = _find_jlc_sym_file(output_path)

        if jlc_fp_dir:
            try:
                rel = Path(os.path.relpath(str(jlc_fp_dir), str(output_path.resolve())))
            except ValueError:
                rel = jlc_fp_dir
            uri = '${KIPRJMOD}/' + str(rel).replace('\\', '/')
            pinned_fp.append({
                "name": "jlc_footprints",
                "type": "KiCad",
                "uri": uri,
                "options": "",
                "description": "JLC/LCSC imported footprints",
            })

        if jlc_sym_file:
            try:
                rel = Path(os.path.relpath(str(jlc_sym_file), str(output_path.resolve())))
            except ValueError:
                rel = jlc_sym_file
            uri = '${KIPRJMOD}/' + str(rel).replace('\\', '/')
            pinned_sym.append({
                "name": "jlc_symbols",
                "type": "KiCad",
                "uri": uri,
                "options": "",
                "description": "JLC/LCSC imported symbols",
            })

        if pinned_fp or pinned_sym:
            project_json['libraries'] = {
                'pinned_footprint_libs': pinned_fp,
                'pinned_symbol_libs': pinned_sym,
            }

    return json.dumps(project_json, ensure_ascii=False, indent=2) + '\n'


def _find_jlc_lib_dir(output_dir: Path) -> Path | None:
    """Find the JLC footprint library directory relative to the project."""
    for candidate in [
        output_dir / 'libs' / 'jlc_footprints.pretty',
        output_dir.parent / 'libs' / 'jlc_footprints.pretty',
    ]:
        if candidate.exists():
            return candidate
    return None


def _find_jlc_sym_file(output_dir: Path) -> Path | None:
    """Find the JLC symbol library file relative to the project."""
    for candidate in [
        output_dir / 'libs' / 'jlc_symbols.kicad_sym',
        output_dir.parent / 'libs' / 'jlc_symbols.kicad_sym',
    ]:
        if candidate.exists():
            return candidate
    return None


def write_fp_lib_table(output_dir: Path) -> None:
    output_resolved = output_dir.resolve()
    lines = ['(fp_lib_table']

    # Repo AIAgent footprints
    repo_fp = REPO_ROOT / 'resources' / 'kicad' / 'footprints'
    if repo_fp.exists():
        for pretty_dir in sorted(repo_fp.glob('*.pretty')):
            lib_name = pretty_dir.name.rsplit('.', 1)[0]
            try:
                rel = Path(os.path.relpath(str(pretty_dir), str(output_resolved)))
            except ValueError:
                rel = pretty_dir
            uri = '${KIPRJMOD}/' + str(rel).replace('\\', '/')
            lines.append(f'  (lib (name "{lib_name}")(type "KiCad")(uri "{uri}")(options "")(descr "AIAgent custom footprints"))')

    # JLC/LCSC imported footprints
    jlc_fp = _find_jlc_lib_dir(output_dir)
    if jlc_fp:
        try:
            rel = Path(os.path.relpath(str(jlc_fp), str(output_resolved)))
        except ValueError:
            rel = jlc_fp
        uri = '${KIPRJMOD}/' + str(rel).replace('\\', '/')
        lines.append(f'  (lib (name "jlc_footprints")(type "KiCad")(uri "{uri}")(options "")(descr "JLC/LCSC imported footprints"))')

    lines.append(')\n')
    content = '\n'.join(lines)
    (output_dir / 'fp-lib-table').write_text(content, encoding='utf-8')

    # Also write sym-lib-table for JLC symbols
    jlc_sym = _find_jlc_sym_file(output_dir)
    if jlc_sym:
        try:
            rel = Path(os.path.relpath(str(jlc_sym), str(output_resolved)))
        except ValueError:
            rel = jlc_sym
        uri = '${KIPRJMOD}/' + str(rel).replace('\\', '/')
        sym_content = f'(sym_lib_table\n  (lib (name "jlc_symbols")(type "KiCad")(uri "{uri}")(options "")(descr "JLC/LCSC imported symbols"))\n)\n'
        (output_dir / 'sym-lib-table').write_text(sym_content, encoding='utf-8')


def write_project(plan: dict[str, Any]) -> dict[str, Any]:
    target = plan.get('target', {})
    if not isinstance(target, dict):
        raise ValueError('KiCad plan target must be an object.')
    output_dir = Path(str(target.get('output_dir', '.where/kicad-output/project')))
    project_file = Path(str(target.get('project_file') or output_dir / 'project.kicad_pro'))
    schematic_file = Path(str(target.get('schematic_file') or output_dir / 'project.kicad_sch'))

    output_dir.mkdir(parents=True, exist_ok=True)
    project_file.parent.mkdir(parents=True, exist_ok=True)
    schematic_file.parent.mkdir(parents=True, exist_ok=True)
    project_file.write_text(render_project(output_dir), encoding='utf-8')
    write_fp_lib_table(output_dir)
    hierarchical = env('KICAD_HIERARCHICAL_SHEETS', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    hierarchical_summary: dict[str, Any] = {}
    if hierarchical:
        hierarchical_summary = write_hierarchical_project(plan, output_dir, schematic_file)
    else:
        schematic_file.write_text(render_schematic(plan) + '\n', encoding='utf-8')

    summary = {
        'schema_version': 'kicad-project-write-result.v1',
        'request_id': str(plan.get('request_id', '')),
        'project_file': str(project_file),
        'schematic_file': str(schematic_file),
        'symbol_count': len([item for item in plan.get('symbols', []) if isinstance(item, dict)]),
        'net_count': len([item for item in plan.get('nets', []) if isinstance(item, dict)]),
        'diagnostics': plan.get('diagnostics', {}),
    }
    if hierarchical_summary:
        summary['hierarchical_sheets'] = hierarchical_summary
    summary_file = output_dir / 'kicad-write-summary.json'
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary['summary_file'] = str(summary_file)
    return summary


def run() -> None:
    plan = load_plan()
    summary = write_project(plan)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('Write KiCad project failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)
