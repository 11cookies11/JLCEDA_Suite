#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from env_utils import env
from schematic_layout_rules import BlockLayoutRule, build_default_layout_rules, _resolve_wiring_block


KICAD_PLAN_SCHEMA_VERSION = 'kicad-execution-plan.v1'
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
    blocks = ['  (lib_symbols']
    for lib_id in lib_ids:
        if lib_id == 'AIAgent:Buck_Regulator':
            blocks.append(local_buck_regulator_symbol())
        elif lib_id == 'MCU_Espressif:ESP32-C3':
            blocks.append(load_installed_symbol('MCU_Espressif', 'ESP32-C3') or local_esp32_c3_bare_symbol())
        elif lib_id == 'AIAgent:ESP32_C3_Bare_QFN32':
            blocks.append(local_esp32_c3_bare_symbol())
        elif lib_id == 'AIAgent:ESP32_C3_Module':
            blocks.append(local_esp32_c3_symbol())
        elif lib_id == 'AIAgent:Conn_01x04':
            blocks.append(local_connector_01x04_symbol())
        elif lib_id == 'Connector_Generic:Conn_01x04':
            blocks.append(load_installed_symbol('Connector_Generic', 'Conn_01x04') or local_connector_01x04_symbol())
        elif lib_id == 'Connector:Conn_Coaxial':
            blocks.append(load_installed_symbol('Connector', 'Conn_Coaxial') or local_two_pin_symbol(lib_id, 'J'))
        elif lib_id == 'AIAgent:Generic_2Pin':
            blocks.append(local_two_pin_symbol(lib_id, 'X'))
        elif lib_id == 'Switch:SW_Push':
            blocks.append(load_installed_symbol('Switch', 'SW_Push') or local_two_pin_symbol(lib_id, 'SW'))
        elif lib_id == 'Device:Crystal':
            blocks.append(load_installed_symbol('Device', 'Crystal') or local_two_pin_symbol(lib_id, 'Y'))
        elif lib_id == 'Device:LED':
            blocks.append(load_installed_symbol('Device', 'LED') or local_two_pin_symbol(lib_id, 'D'))
        elif lib_id == 'Device:D':
            blocks.append(load_installed_symbol('Device', 'D') or local_two_pin_symbol(lib_id, 'D'))
        elif lib_id == 'Device:R':
            blocks.append(load_installed_symbol('Device', 'R') or local_two_pin_symbol(lib_id, 'R'))
        elif lib_id == 'Device:C':
            blocks.append(load_installed_symbol('Device', 'C') or local_two_pin_symbol(lib_id, 'C'))
        elif lib_id == 'Device:L':
            blocks.append(load_installed_symbol('Device', 'L') or local_two_pin_symbol(lib_id, 'L'))
        elif lib_id == 'power:PWR_FLAG':
            blocks.append(load_installed_symbol('power', 'PWR_FLAG') or local_two_pin_symbol('power:PWR_FLAG', '#FLG'))
        else:
            blocks.append(local_two_pin_symbol(lib_id, 'R'))
    blocks.append('  )')
    return '\n'.join(blocks)


def kicad_symbol_roots() -> list[Path]:
    roots: list[Path] = []
    explicit = env('KICAD_SYMBOL_DIR')
    if explicit:
        roots.append(Path(explicit))
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


def parse_symbol_pin_map(lib_id: str) -> dict[str, dict[str, float]]:
    if lib_id in SYMBOL_PIN_CACHE:
        return SYMBOL_PIN_CACHE[lib_id]
    if ':' not in lib_id:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    library, symbol_name = lib_id.split(':', 1)
    block = installed_symbol_block(library, symbol_name)
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


def local_buck_regulator_symbol() -> str:
    return '''    (symbol "AIAgent:Buck_Regulator"
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "U" (at 0 8.89 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" "Buck_Regulator" (at 0 -8.89 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "AIAgent_Buck_Regulator_0_1"
        (rectangle (start -5.08 6.35) (end 5.08 -6.35)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (pin power_in line (at -10.16 3.81 0) (length 5.08)
          (name "VIN" (effects (font (size 1.27 1.27))))
          (number "VIN" (effects (font (size 1.27 1.27))))
        )
        (pin power_out line (at 10.16 3.81 180) (length 5.08)
          (name "SW" (effects (font (size 1.27 1.27))))
          (number "SW" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at -10.16 -3.81 0) (length 5.08)
          (name "FB" (effects (font (size 1.27 1.27))))
          (number "FB" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at 0 -11.43 90) (length 5.08)
          (name "GND" (effects (font (size 1.27 1.27))))
          (number "GND" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )'''


def local_esp32_c3_symbol() -> str:
    return '''    (symbol "AIAgent:ESP32_C3_Module"
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "U" (at 0 16.51 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" "ESP32-C3" (at 0 -16.51 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "ESP32_C3_Module_0_1"
        (rectangle (start -10.16 13.97) (end 10.16 -13.97)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (pin power_in line (at -15.24 10.16 0) (length 5.08)
          (name "3V3" (effects (font (size 1.27 1.27))))
          (number "3V3" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at -15.24 5.08 0) (length 5.08)
          (name "EN" (effects (font (size 1.27 1.27))))
          (number "EN" (effects (font (size 1.27 1.27))))
        )
        (pin bidirectional line (at -15.24 0 0) (length 5.08)
          (name "GPIO9/BOOT" (effects (font (size 1.27 1.27))))
          (number "GPIO9" (effects (font (size 1.27 1.27))))
        )
        (pin output line (at 15.24 5.08 180) (length 5.08)
          (name "TXD" (effects (font (size 1.27 1.27))))
          (number "TXD" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at 15.24 0 180) (length 5.08)
          (name "RXD" (effects (font (size 1.27 1.27))))
          (number "RXD" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at 0 -19.05 90) (length 5.08)
          (name "GND" (effects (font (size 1.27 1.27))))
          (number "GND" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )'''


def local_esp32_c3_bare_symbol() -> str:
    return '''    (symbol "AIAgent:ESP32_C3_Bare_QFN32"
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "U" (at 0 24.13 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" "ESP32-C3FH4/FH8X" (at 0 -24.13 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "ESP32_C3_Bare_QFN32_0_1"
        (rectangle (start -15.24 21.59) (end 15.24 -21.59)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (pin power_in line (at -20.32 17.78 0) (length 5.08)
          (name "VDD3P3" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at -20.32 15.24 0) (length 5.08)
          (name "VDD3P3" (effects (font (size 1.27 1.27))))
          (number "3" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at -20.32 12.7 0) (length 5.08)
          (name "VDD3P3_RTC" (effects (font (size 1.27 1.27))))
          (number "11" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at -20.32 10.16 0) (length 5.08)
          (name "VDD3P3_CPU" (effects (font (size 1.27 1.27))))
          (number "17" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at -20.32 7.62 0) (length 5.08)
          (name "VDD_SPI" (effects (font (size 1.27 1.27))))
          (number "18" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at -20.32 5.08 0) (length 5.08)
          (name "VDDA" (effects (font (size 1.27 1.27))))
          (number "31" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at -20.32 2.54 0) (length 5.08)
          (name "VDDA" (effects (font (size 1.27 1.27))))
          (number "32" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at -20.32 -2.54 0) (length 5.08)
          (name "CHIP_EN" (effects (font (size 1.27 1.27))))
          (number "7" (effects (font (size 1.27 1.27))))
        )
        (pin bidirectional line (at -20.32 -7.62 0) (length 5.08)
          (name "GPIO9/BOOT" (effects (font (size 1.27 1.27))))
          (number "15" (effects (font (size 1.27 1.27))))
        )
        (pin bidirectional line (at -20.32 -10.16 0) (length 5.08)
          (name "GPIO8" (effects (font (size 1.27 1.27))))
          (number "14" (effects (font (size 1.27 1.27))))
        )
        (pin output line (at 20.32 12.7 180) (length 5.08)
          (name "U0TXD" (effects (font (size 1.27 1.27))))
          (number "28" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at 20.32 10.16 180) (length 5.08)
          (name "U0RXD" (effects (font (size 1.27 1.27))))
          (number "27" (effects (font (size 1.27 1.27))))
        )
        (pin bidirectional line (at 20.32 5.08 180) (length 5.08)
          (name "GPIO2" (effects (font (size 1.27 1.27))))
          (number "6" (effects (font (size 1.27 1.27))))
        )
        (pin bidirectional line (at 20.32 2.54 180) (length 5.08)
          (name "GPIO18" (effects (font (size 1.27 1.27))))
          (number "25" (effects (font (size 1.27 1.27))))
        )
        (pin bidirectional line (at 20.32 0 180) (length 5.08)
          (name "GPIO19" (effects (font (size 1.27 1.27))))
          (number "26" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at -5.08 -26.67 90) (length 5.08)
          (name "XTAL_P" (effects (font (size 1.27 1.27))))
          (number "30" (effects (font (size 1.27 1.27))))
        )
        (pin output line (at 5.08 -26.67 90) (length 5.08)
          (name "XTAL_N" (effects (font (size 1.27 1.27))))
          (number "29" (effects (font (size 1.27 1.27))))
        )
        (pin input line (at 20.32 -10.16 180) (length 5.08)
          (name "LNA_IN" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin power_in line (at 0 -26.67 90) (length 5.08)
          (name "GND" (effects (font (size 1.27 1.27))))
          (number "33" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )'''


def local_connector_01x04_symbol() -> str:
    return '''    (symbol "AIAgent:Conn_01x04"
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "J" (at 0 8.89 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" "Conn_01x04" (at 0 -8.89 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "Conn_01x04_0_1"
        (rectangle (start -2.54 6.35) (end 2.54 -6.35)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (pin passive line (at -7.62 3.81 0) (length 5.08)
          (name "1" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at -7.62 1.27 0) (length 5.08)
          (name "2" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at -7.62 -1.27 0) (length 5.08)
          (name "3" (effects (font (size 1.27 1.27))))
          (number "3" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at -7.62 -3.81 0) (length 5.08)
          (name "4" (effects (font (size 1.27 1.27))))
          (number "4" (effects (font (size 1.27 1.27))))
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

    if lib_id == 'AIAgent:Buck_Regulator':
        if pin == 'VIN':
            return x - 10.16, y + 3.81, 180.0
        if pin == 'SW':
            return x + 10.16, y + 3.81, 0.0
        if pin == 'FB':
            return x - 10.16, y - 3.81, 180.0
        if pin == 'GND':
            return x, y - 11.43, 90.0
    if lib_id == 'AIAgent:ESP32_C3_Module':
        if pin in {'3V3'}:
            return x - 15.24, y + 10.16, 180.0
        if pin == 'EN':
            return x - 15.24, y + 5.08, 180.0
        if pin == 'GPIO9':
            return x - 15.24, y, 180.0
        if pin == 'TXD':
            return x + 15.24, y + 5.08, 0.0
        if pin == 'RXD':
            return x + 15.24, y, 0.0
        if pin == 'GND':
            return x, y - 19.05, 90.0
    if lib_id == 'AIAgent:ESP32_C3_Bare_QFN32':
        return bare_esp32_pin_endpoint(pin, x, y)

    if lib_id == 'MCU_Espressif:ESP32-C3':
        return official_esp32_c3_pin_endpoint(pin, x, y)

    if lib_id == 'AIAgent:ESP32_C3_Bare_QFN32':
        return bare_esp32_pin_endpoint(pin, x, y)
    if lib_id == 'AIAgent:Conn_01x04':
        pin_y = {'1': 3.81, '2': 1.27, '3': -1.27, '4': -3.81}.get(pin, 0.0)
        return x - 7.62, y + pin_y, 180.0
    if lib_id == 'Connector_Generic:Conn_01x04':
        pin_y = {'1': 2.54, '2': 0.0, '3': -2.54, '4': -5.08}.get(pin, 0.0)
        return x - 5.08, y + pin_y, 180.0
    if lib_id == 'Connector:Conn_Coaxial':
        if pin == '2':
            return x, y - 5.08, 90.0
        return x - 5.08, y, 180.0
    if lib_id in {'Device:R', 'Device:C', 'Device:L'}:
        if pin == '2':
            return x, y - 3.81, 90.0
        return x, y + 3.81, 270.0
    if lib_id == 'Device:Crystal':
        if pin == '2':
            return x + 3.81, y, 0.0
        return x - 3.81, y, 180.0
    if lib_id == 'Switch:SW_Push':
        if pin == '2':
            return x + 5.08, y, 0.0
        return x - 5.08, y, 180.0

    if pin in {'2', 'K', 'C'}:
        return x + 5.08, y, 0.0
    return x - 5.08, y, 180.0


def bare_esp32_pin_endpoint(pin: str, x: float, y: float) -> tuple[float, float, float]:
        bare_pin_offsets: dict[str, tuple[float, float, float]] = {
            '2': (-20.32, 17.78, 180.0),
            '3': (-20.32, 15.24, 180.0),
            '11': (-20.32, 12.7, 180.0),
            '17': (-20.32, 10.16, 180.0),
            '18': (-20.32, 7.62, 180.0),
            '31': (-20.32, 5.08, 180.0),
            '32': (-20.32, 2.54, 180.0),
            '7': (-20.32, -2.54, 180.0),
            '15': (-20.32, -7.62, 180.0),
            '14': (-20.32, -10.16, 180.0),
            '28': (20.32, 12.7, 0.0),
            '27': (20.32, 10.16, 0.0),
            '6': (20.32, 5.08, 0.0),
            '25': (20.32, 2.54, 0.0),
            '26': (20.32, 0.0, 0.0),
            '30': (-5.08, -26.67, 90.0),
            '29': (5.08, -26.67, 90.0),
            '1': (20.32, -10.16, 0.0),
            '33': (0.0, -26.67, 90.0),
        }
        aliases = {
            'VDD3P3': '2',
            'VDD3P3_A': '2',
            'VDD3P3_B': '3',
            'VDD3P3_RTC': '11',
            'VDD3P3_CPU': '17',
            'VDD_SPI': '18',
            'VDDA1': '31',
            'VDDA2': '32',
            'VDDA': '31',
            'CHIP_EN': '7',
            'EN': '7',
            'GPIO9': '15',
            'BOOT': '15',
            'GPIO8': '14',
            'U0TXD': '28',
            'TXD': '28',
            'U0RXD': '27',
            'RXD': '27',
            'GPIO2': '6',
            'GPIO18': '25',
            'GPIO19': '26',
            'XTAL_P': '30',
            'XTAL_N': '29',
            'LNA_IN': '1',
            'GND': '33',
        }
        offset = bare_pin_offsets.get(aliases.get(pin, pin))
        if offset:
            dx, dy, direction = offset
            return x + dx, y + dy, direction
        return x, y, 0.0


def official_esp32_c3_pin_endpoint(pin: str, x: float, y: float) -> tuple[float, float, float]:
    offsets: dict[str, tuple[float, float, float]] = {
        '1': (22.86, 20.32, 0.0),
        '2': (-10.16, 25.4, 90.0),
        '3': (-10.16, 25.4, 90.0),
        '4': (-22.86, -7.62, 180.0),
        '5': (-22.86, -10.16, 180.0),
        '6': (22.86, -20.32, 0.0),
        '7': (-22.86, 2.54, 180.0),
        '8': (-22.86, -12.7, 180.0),
        '9': (-22.86, -15.24, 180.0),
        '10': (-22.86, -17.78, 180.0),
        '11': (-7.62, 25.4, 90.0),
        '12': (-22.86, -20.32, 180.0),
        '13': (-22.86, -22.86, 180.0),
        '14': (22.86, 17.78, 0.0),
        '15': (22.86, 15.24, 0.0),
        '16': (22.86, 12.7, 0.0),
        '17': (-5.08, 25.4, 90.0),
        '18': (-2.54, 25.4, 90.0),
        '19': (22.86, -17.78, 0.0),
        '20': (22.86, -15.24, 0.0),
        '21': (22.86, -12.7, 0.0),
        '22': (22.86, -10.16, 0.0),
        '23': (22.86, -7.62, 0.0),
        '24': (22.86, -5.08, 0.0),
        '25': (22.86, -2.54, 0.0),
        '26': (22.86, 0.0, 0.0),
        '27': (22.86, 2.54, 0.0),
        '28': (22.86, 5.08, 0.0),
        '29': (-22.86, 15.24, 180.0),
        '30': (-22.86, 17.78, 180.0),
        '31': (-22.86, 20.32, 180.0),
        '32': (-7.62, 25.4, 90.0),
        '33': (0.0, -25.4, 270.0),
    }
    aliases = {
        'VDD3P3': '2',
        'VDD3P3_A': '2',
        'VDD3P3_B': '3',
        'VDD3P3_RTC': '11',
        'VDD3P3_CPU': '17',
        'VDD_SPI': '18',
        'VDDA1': '31',
        'VDDA2': '32',
        'VDDA': '31',
        'CHIP_EN': '7',
        'EN': '7',
        'GPIO9': '15',
        'BOOT': '15',
        'GPIO8': '14',
        'U0TXD': '28',
        'TXD': '28',
        'U0RXD': '27',
        'RXD': '27',
        'GPIO2': '6',
        'GPIO18': '25',
        'GPIO19': '26',
        'XTAL_P': '30',
        'XTAL_N': '29',
        'LNA_IN': '1',
        'GND': '33',
    }
    offset = offsets.get(aliases.get(pin, pin))
    if offset:
        dx, dy, direction = offset
        return x + dx, y + dy, direction
    return x, y, 0.0


def label_shape(kind: str) -> str:
    if kind == 'ground':
        return 'input'
    if kind == 'power':
        return 'input'
    return 'bidirectional'


def net_kind_by_name(plan: dict[str, Any]) -> dict[str, str]:
    return {str(net.get('name', '')): str(net.get('kind', 'signal')) for net in plan.get('nets', []) if isinstance(net, dict)}


def render_symbol_instance(symbol: dict[str, Any], project_name: str) -> str:
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
        pin_numbers = ['1', '2'] if lib_id != 'AIAgent:Buck_Regulator' else ['VIN', 'SW', 'FB', 'GND']
    for pin_number in dict.fromkeys(pin_numbers):
        pin_lines.append(f'      (pin {q(pin_number)} (uuid {q(new_uuid())}))')

    ref_y = y - 7.62 if lib_id == 'MCU_Espressif:ESP32-C3' else y - 5.08
    value_y = y + 7.62 if lib_id == 'MCU_Espressif:ESP32-C3' else y + 5.08
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
    )
{chr(10).join(pin_lines)}
    (instances
      (project {q(project_name)}
        (path "/"
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

        for _block_name, group in block_groups.items():
            if len(group) < 2:
                continue
            group.sort(key=lambda rp: pin_endpoint(by_ref[rp[0]], rp[1])[1])
            ref_pins: list[tuple[str, str, tuple[float, float]]] = []
            for ref, pin in group:
                x, y, _direction = pin_endpoint(by_ref[ref], pin)
                ref_pins.append((ref, pin, (x, y)))
            blocks.extend(_route_intra_block(ref_pins))
            if is_power_rail:
                continue
            if cross_module:
                for ref, pin in group[1:]:
                    suppress_labels.add((ref, pin))
            else:
                for ref, pin in group:
                    suppress_labels.add((ref, pin))

    return blocks, suppress_labels


def render_connectivity(plan: dict[str, Any], symbols: list[dict[str, Any]] | None = None) -> str:
    kind_map = net_kind_by_name(plan)
    blocks: list[str] = []
    if symbols is None:
        symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
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
            if (ref, pin_number) in suppress_labels:
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
            if kind in {'ground', 'power'}:
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


def render_schematic(plan: dict[str, Any]) -> str:
    symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
    symbols.extend(automatic_power_flags(plan))
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    instances = '\n'.join(render_symbol_instance(symbol, project_name) for symbol in symbols)
    connectivity = render_connectivity(plan, symbols)
    return f'''(kicad_sch
  (version 20250610)
  (generator "kicad-suite-agent")
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


def render_project() -> str:
    return json.dumps(
        {
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
        },
        ensure_ascii=False,
        indent=2,
    ) + '\n'


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
    project_file.write_text(render_project(), encoding='utf-8')
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
