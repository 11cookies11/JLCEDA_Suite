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
from .schema_versions import KICAD_EXECUTION_PLAN_SCHEMA_VERSION, KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION
from .schematic_layout_rules import BlockLayoutRule, build_default_layout_rules, _resolve_wiring_block

KICAD_SCHEMATIC_FILE_VERSION = '20250114'
REPO_ROOT = Path(__file__).resolve().parents[2]
SYMBOL_PIN_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
SYMBOL_UNIT_CACHE: dict[str, list[int]] = {}
PIN_LEN = 2.54  # standard KiCad pin line length, mm

DEFAULT_ERC_PIN_MAP: list[list[int]] = [
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 2],
    [0, 2, 0, 1, 0, 0, 1, 0, 2, 2, 2, 2],
    [0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 2],
    [0, 1, 0, 0, 0, 0, 1, 1, 2, 1, 1, 2],
    [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 2],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2],
    [1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 2],
    [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 2],
    [0, 2, 1, 2, 0, 0, 1, 0, 2, 2, 2, 2],
    [0, 2, 0, 1, 0, 0, 1, 0, 2, 0, 0, 2],
    [0, 2, 1, 1, 0, 0, 1, 0, 2, 0, 0, 2],
    [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
]

DEFAULT_ERC_RULE_SEVERITIES: dict[str, str] = {
    "bus_definition_conflict": "error",
    "bus_entry_needed": "error",
    "bus_to_bus_conflict": "error",
    "bus_to_net_conflict": "error",
    "different_unit_footprint": "error",
    "different_unit_net": "error",
    "duplicate_reference": "error",
    "duplicate_sheet_names": "error",
    "endpoint_off_grid": "warning",
    "extra_units": "error",
    "field_name_whitespace": "warning",
    "footprint_filter": "ignore",
    "footprint_link_issues": "warning",
    "four_way_junction": "ignore",
    "ground_pin_not_ground": "warning",
    "hier_label_mismatch": "error",
    "isolated_pin_label": "warning",
    "label_dangling": "error",
    "label_multiple_wires": "warning",
    "lib_symbol_issues": "warning",
    "lib_symbol_mismatch": "ignore",
    "missing_bidi_pin": "warning",
    "missing_input_pin": "warning",
    "missing_power_pin": "error",
    "missing_unit": "warning",
    "multiple_net_names": "warning",
    "net_not_bus_member": "warning",
    "no_connect_connected": "warning",
    "no_connect_dangling": "warning",
    "pin_not_connected": "error",
    "pin_not_driven": "error",
    "pin_to_pin": "warning",
    "power_pin_not_driven": "error",
    "same_local_global_label": "warning",
    "similar_label_and_power": "warning",
    "similar_labels": "warning",
    "similar_power": "warning",
    "simulation_model_issue": "ignore",
    "single_global_label": "ignore",
    "stacked_pin_name": "warning",
    "unannotated": "error",
    "unconnected_wire_endpoint": "warning",
    "undefined_netclass": "error",
    "unit_value_mismatch": "error",
    "unresolved_variable": "error",
    "wire_dangling": "error",
}

H618_MINIMAL_PINS: tuple[str, ...] = (
    "GND",
    "VDD1",
    "VDD2",
    "VDDQ",
    "PMIC_SCL",
    "PMIC_SDA",
    "PMIC_INT_N",
    "XIN",
    "XOUT",
    "RTC_XIN",
    "RTC_XOUT",
    "PH0",
    "PH1",
    "RESET_N",
    "BOOT0",
    "SD_CLK",
    "SD_CMD",
    "SD_D0",
    "SD_D1",
    "SD_D2",
    "SD_D3",
    "SPI0_CLK",
    "SPI0_MOSI",
    "SPI0_MISO",
    "SPI0_CS0",
    "RGMII_MDC",
    "RGMII_MDIO",
    "RGMII_TXD0",
    "RGMII_TXD1",
    "RGMII_TXD2",
    "RGMII_TXD3",
    "RGMII_RXD0",
    "RGMII_RXD1",
    "RGMII_RXD2",
    "RGMII_RXD3",
    "RGMII_TXC",
    "RGMII_RXC",
    "RGMII_TXCTL",
    "RGMII_RXCTL",
    "RGMII_RESET_N",
    "USB0_DM",
    "USB0_DP",
    "USB_HUB_RESET_N",
    "HDMI_TX0_P",
    "HDMI_TX0_N",
    "HDMI_TX1_P",
    "HDMI_TX1_N",
    "HDMI_TX2_P",
    "HDMI_TX2_N",
    "HDMI_CLK_P",
    "HDMI_CLK_N",
    "PH5",
    "PH4",
    "PC9",
    "PH2",
    "PH3",
    "PC6",
    "PC11",
    "PC5",
    "PC8",
    "PC15",
    "PC14",
    "PH7",
    "PH8",
    "PH6",
    "PH9",
    "PC7",
    "PC10",
    "DQ0",
    "DQ1",
    "DQ2",
    "DQ3",
    "DQ4",
    "DQ5",
    "DQ6",
    "DQ7",
    "DQS0_P",
    "DQS0_N",
    "CKE",
)


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
    if str(payload.get('schema_version', '')) != KICAD_EXECUTION_PLAN_SCHEMA_VERSION:
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
    """Return ordered list of directories searched for .kicad_sym library files.

    Priority: workspace > explicit env vars > output dir > CWD > KiCad system.
    """
    roots: list[Path] = []

    def _add_if_exists(path: Path) -> None:
        if path.exists() and path not in roots:
            roots.append(path)

    # 1. Workspace libraries (highest priority — single source of truth)
    workspace = env('KICAD_WORKSPACE', '')
    if workspace:
        _add_if_exists(Path(workspace) / 'libraries' / 'symbols')
        _add_if_exists(Path(workspace) / 'libs')

    # 2. Repo-bundled symbols
    _add_if_exists(REPO_ROOT / 'resources' / 'kicad' / 'symbols')

    # 3. Explicit env var overrides
    explicit = env('KICAD_SYMBOL_DIR')
    if explicit:
        _add_if_exists(Path(explicit))
    extra = env('KICAD_EXTRA_SYMBOL_DIR')
    if extra:
        for item in extra.split(';'):
            if item.strip():
                _add_if_exists(Path(item.strip()))

    # 4. Source project libraries
    source_project = env('KICAD_SOURCE_PROJECT_DIR', '')
    if source_project:
        _add_if_exists(Path(source_project) / 'libraries' / 'symbols')

    # 5. Output directory (for in-project libs generated by tooling)
    output_root = env('KICAD_OUTPUT_DIR', '')
    project_name = env('KICAD_PROJECT_NAME', '')
    if output_root:
        _add_if_exists(Path(output_root) / project_name / 'libraries' / 'symbols')
        _add_if_exists(Path(output_root) / 'libraries' / 'symbols')
        _add_if_exists(Path(output_root) / 'libs')
        try:
            for subdir in Path(output_root).iterdir():
                if subdir.is_dir():
                    _add_if_exists(subdir / 'libraries' / 'symbols')
                    _add_if_exists(subdir / 'libs')
        except OSError:
            pass

    # 6. CWD and parents (fallback)
    try:
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents)[:4]:
            _add_if_exists(parent / 'libraries' / 'symbols')
            _add_if_exists(parent / 'libs')
    except OSError:
        pass

    # 7. KiCad system libraries (lowest priority)
    for base in (Path('D:/Program Files/KiCad'), Path('C:/Program Files/KiCad')):
        if base.exists():
            for path in sorted(base.glob('*'), reverse=True):
                _add_if_exists(path / 'share' / 'kicad' / 'symbols')

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


def sanitize_symbol_block(text: str) -> str:
    """Drop invalid graphic primitives emitted by third-party symbol converters."""
    cleaned = text
    for bad_token in ('NaN', 'nan', 'INF', 'Inf'):
        while bad_token in cleaned:
            bad_index = cleaned.find(bad_token)
            start = max(
                cleaned.rfind(f'({head}', 0, bad_index)
                for head in ('arc', 'circle', 'polyline', 'rectangle', 'bezier')
            )
            if start < 0:
                cleaned = cleaned.replace(bad_token, '0', 1)
                continue
            end = find_matching_paren(cleaned, start)
            if end < 0:
                cleaned = cleaned[:bad_index] + '0' + cleaned[bad_index + len(bad_token):]
                continue
            while start > 0 and cleaned[start - 1] in ' \t':
                start -= 1
            if start > 0 and cleaned[start - 1] == '\n':
                start -= 1
            cleaned = cleaned[:start] + cleaned[end + 1:]
    return cleaned


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
        block = sanitize_symbol_block(text[start:end + 1])
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
        if installed and symbol_name == 'ALLWINNERH618' and '(pin ' not in installed:
            return local_h618_minimal_symbol(lib_id)
        if installed:
            return normalize_connector_pin_types(installed, symbol_name)
        system_block = installed_symbol_block(library, symbol_name)
        if system_block:
            if symbol_name == 'ALLWINNERH618' and '(pin ' not in system_block:
                return local_h618_minimal_symbol(lib_id)
            normalized = normalize_embedded_symbol_name(system_block, library, symbol_name)
            normalized = normalize_connector_pin_types(normalized, symbol_name)
            return '\n'.join(f'    {line}' if line.strip() else line for line in normalized.splitlines())

    connector = local_connector_symbol(lib_id)
    if connector:
        return connector

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


def normalize_connector_pin_types(block: str, symbol_name: str) -> str:
    upper_name = symbol_name.upper()
    if upper_name in {
        'USB2514B-AEZC-TR',
        'AXP313A_C5365290',
        'GD25Q16ETIGR',
        'RTL8211F-CG',
        '322524M12PF10PPM',
        'H9HCNNNBKUMLXR-NEE',
    }:
        return re.sub(r'\(pin\s+unspecified\s+line', '(pin passive line', block)
    connector_tokens = (
        'HEADER',
        'HDR-',
        'CONN_',
        'PINHEADER',
        'XKTF',
        'TF-',
        'MICROSD',
        'SDCARD',
        'USB-',
        'USB_',
        'TYPE-C',
        'RJ45',
        'HDMI',
        '467650301',
        'DS1021',
    )
    if not any(token in upper_name for token in connector_tokens):
        return block
    return re.sub(r'\(pin\s+(input|output|bidirectional|tri_state|passive|power_in|power_out|open_collector|open_emitter|unspecified)\s+line', '(pin passive line', block)


def local_h618_minimal_symbol(lib_id: str) -> str:
    """Minimal schematic symbol for the EasyEDA H618 entry when it has no pins."""
    symbol_name = lib_id.split(':', 1)[-1]
    half_count = (len(H618_MINIMAL_PINS) + 1) // 2
    half_height = max(10.16, half_count * 1.27 + 2.54)
    pins: list[str] = []
    for index, pin_name in enumerate(H618_MINIMAL_PINS):
        left = index < half_count
        row = index if left else index - half_count
        y = (half_count - 1) * 1.27 - row * 2.54
        x = -22.86 if left else 22.86
        rotation = 0 if left else 180
        pins.append(f'''        (pin passive line (at {fmt(x)} {fmt(y)} {rotation}) (length 2.54)
          (name {q(pin_name)} (effects (font (size 1.27 1.27))))
          (number {q(pin_name)} (effects (font (size 1.27 1.27))))
        )''')
    return f'''    (symbol {q(lib_id)}
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "U" (at 0 {fmt(half_height + 2.54)} 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" {q(symbol_name)} (at 0 {fmt(-half_height - 2.54)} 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "{symbol_name}_0_1"
        (rectangle (start -17.78 {fmt(half_height)}) (end 17.78 {fmt(-half_height)})
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
{chr(10).join(pins)}
      )
      (embedded_fonts no)
    )'''


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


def parse_symbol_pin_map(lib_id: str) -> dict[str, dict[str, Any]]:
    if lib_id in SYMBOL_PIN_CACHE:
        return SYMBOL_PIN_CACHE[lib_id]
    if ':' not in lib_id:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    library, symbol_name = lib_id.split(':', 1)
    # Use the same symbol resolution path as schematic generation.  Some
    # imported EasyEDA symbols (notably ALLWINNERH618) can be present but empty,
    # so resolving installed symbols first would collapse all generated labels
    # onto the same fallback coordinate.
    block = symbol_block_for_lib_id(lib_id) or installed_symbol_block(library, symbol_name)
    if not block:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    try:
        tree = parse_sexpr(block)
    except Exception:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}

    pins: dict[str, dict[str, Any]] = {}

    def pin_aliases(number: str, name: str) -> set[str]:
        aliases = {number, number.upper()}
        clean_name = name.strip()
        if clean_name:
            name_upper = clean_name.upper()
            aliases.add(clean_name)
            aliases.add(name_upper)
            normalized = re.sub(r'[^A-Z0-9]+', '_', name_upper).strip('_')
            if normalized:
                aliases.add(normalized)
                aliases.add(normalized.replace('_T', '_P').replace('_C', '_N'))
                match = re.fullmatch(r'(.+?)[AB]', normalized)
                if match:
                    aliases.add(match.group(1))
                match = re.fullmatch(r'(CKE\d+)[AB]', normalized)
                if match:
                    aliases.add(match.group(1))
                    aliases.add(match.group(1).replace('0', '', 1))
                match = re.fullmatch(r'(DQ\d+)[AB]', normalized)
                if match:
                    aliases.add(match.group(1))
                match = re.fullmatch(r'(DQS\d+)_[TC][AB]', normalized)
                if match:
                    aliases.add(match.group(1))
        return {alias for alias in aliases if alias}

    def visit(node: Any, current_unit: int = 1) -> None:
        if not isinstance(node, list) or not node:
            return
        node_unit = current_unit
        if sexpr_head(node) == 'symbol' and len(node) >= 2 and isinstance(node[1], str):
            unit_match = re.fullmatch(rf'{re.escape(symbol_name)}_(\d+)_\d+', node[1])
            if unit_match:
                parsed_unit = int(unit_match.group(1))
                if parsed_unit > 0:
                    node_unit = parsed_unit
        if sexpr_head(node) == 'pin':
            at_data = next((child for child in node if sexpr_head(child) == 'at'), None)
            length_data = next((child for child in node if sexpr_head(child) == 'length'), None)
            number_data = next((child for child in node if sexpr_head(child) == 'number'), None)
            name_data = next((child for child in node if sexpr_head(child) == 'name'), None)
            if isinstance(at_data, list) and len(at_data) >= 4 and isinstance(number_data, list) and len(number_data) >= 2:
                try:
                    number = str(number_data[1])
                    name = str(name_data[1]) if isinstance(name_data, list) and len(name_data) >= 2 else ''
                    pin_info = {
                        'x': float(at_data[1]),
                        'y': float(at_data[2]),
                        'rotation': float(at_data[3]),
                        'length': float(length_data[1]) if isinstance(length_data, list) and len(length_data) >= 2 else 0.0,
                        'electrical_type': str(node[1]) if len(node) >= 2 else '',
                        'name': name,
                        'number': number,
                        'unit': node_unit,
                    }
                    for alias in pin_aliases(number, name):
                        pins.setdefault(alias, pin_info)
                except (TypeError, ValueError):
                    pass
        for child in node:
            visit(child, node_unit)

    visit(tree)
    if not pins:
        extends = next((child[1] for child in tree if isinstance(child, list) and sexpr_head(child) == 'extends'), None)
        if isinstance(extends, str) and extends:
            parent_pins = parse_symbol_pin_map(f'{library}:{extends}')
            pins.update(parent_pins)
    SYMBOL_PIN_CACHE[lib_id] = pins
    return pins


def symbol_unit_numbers(lib_id: str) -> list[int]:
    if lib_id in SYMBOL_UNIT_CACHE:
        return SYMBOL_UNIT_CACHE[lib_id]
    if ':' not in lib_id:
        SYMBOL_UNIT_CACHE[lib_id] = [1]
        return [1]
    symbol_name = lib_id.split(':', 1)[1]
    block = symbol_block_for_lib_id(lib_id)
    units = sorted({int(match.group(1)) for match in re.finditer(rf'\(symbol "{re.escape(symbol_name)}_(\d+)_', block)})
    if not units:
        units = [1]
    SYMBOL_UNIT_CACHE[lib_id] = units
    return units


def symbol_real_pin_numbers(lib_id: str, unit: int | None = None) -> list[str]:
    real_pins: dict[str, dict[str, Any]] = {}
    for alias, pin_info in parse_symbol_pin_map(lib_id).items():
        number = str(pin_info.get('number', alias)).strip()
        if not number:
            continue
        if unit is not None and int(pin_info.get('unit', 1) or 1) != unit:
            continue
        real_pins.setdefault(number, pin_info)
    return sorted(real_pins, key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value)))


def symbol_pin_unit(lib_id: str, pin_number: str) -> int:
    raw = str(pin_number).strip()
    pin_map = parse_symbol_pin_map(lib_id)
    pin_info = pin_map.get(raw) or pin_map.get(raw.upper())
    if isinstance(pin_info, dict):
        try:
            return int(pin_info.get('unit', 1) or 1)
        except (TypeError, ValueError):
            return 1
    return 1


def effective_net_kind(name: str, declared_kind: str = 'signal') -> str:
    normalized = name.strip().upper()
    if normalized == 'GND' or normalized.startswith('GND_') or normalized.endswith('_GND') or '_GND_' in normalized:
        return 'ground'
    voltage_pattern = r'(^|\+|_)(\d+V\d*|VCC|VDD|VBUS|VIN|VOUT)(_|$)'
    if normalized.startswith('+') or re.search(voltage_pattern, normalized):
        return 'power'
    if normalized.endswith('_EN') or normalized.endswith('_CTRL'):
        return 'signal'
    if declared_kind in {'power', 'ground'}:
        return declared_kind
    return 'signal'


def power_flag_net_names(net_names: set[str], kind_map: dict[str, str]) -> set[str]:
    return {
        name
        for name in net_names
        if effective_net_kind(name, kind_map.get(name, 'signal')) in {'power', 'ground'}
    }


def power_output_net_names(symbols: list[dict[str, Any]]) -> set[str]:
    driven: set[str] = set()
    for symbol in symbols:
        lib_id = str(symbol.get('lib_id', '')).strip()
        if not lib_id:
            continue
        try:
            pin_map = parse_symbol_pin_map(lib_id)
        except Exception:
            pin_map = {}
        for pin in symbol.get('pins', []):
            if not isinstance(pin, dict):
                continue
            pin_number = str(pin.get('number', '')).strip()
            net_name = str(pin.get('net', '')).strip()
            pin_data = pin_map.get(pin_number) or pin_map.get(pin_number.upper())
            electrical_type = str(pin_data.get('electrical_type', '') if isinstance(pin_data, dict) else '')
            if net_name and electrical_type == 'power_out':
                driven.add(net_name)
    return driven


def endpoint_from_pin(pin_data: dict[str, float], origin_x: float, origin_y: float, symbol_rotation: float = 0.0) -> tuple[float, float, float]:
    """Return (tip_x, tip_y, direction).

    (tip_x, tip_y) = pin tip absolute position (the electrical connection point).
    direction = 0/90/180/270, the direction the wire exits the pin.
    """
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


def _pin_length(symbol: dict[str, Any], pin_number: str) -> float:
    """Return the pin line length (mm) for a symbol's pin, default PIN_LEN."""
    lib_id = str(symbol.get('lib_id', ''))
    if not lib_id:
        return PIN_LEN
    pin = str(pin_number).strip().upper()
    pin_map = parse_symbol_pin_map(lib_id)
    pin_data = pin_map.get(pin_number) or pin_map.get(pin)
    if not pin_data:
        return PIN_LEN
    try:
        length = float(pin_data.get('length', PIN_LEN))
    except (TypeError, ValueError):
        return PIN_LEN
    return length if length > 0 else PIN_LEN


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


def local_connector_symbol(lib_id: str) -> str:
    match = re.fullmatch(r'Connector_Generic:Conn_(\d{2})x(\d{2})', lib_id)
    if not match:
        return ''
    columns = int(match.group(1))
    rows = int(match.group(2))
    if columns not in {1, 2} or rows < 1:
        return ''
    symbol_name = lib_id.split(':', 1)[-1]
    half_height = max(1.27, (rows - 1) * 2.54 / 2 + 1.27)
    pins: list[str] = []
    if columns == 1:
        for row in range(rows):
            number = str(row + 1)
            y = (rows - 1) * 1.27 - row * 2.54
            pins.append(f'''        (pin passive line (at -5.08 {fmt(y)} 0) (length 2.54)
          (name {q(number)} (effects (font (size 1.27 1.27))))
          (number {q(number)} (effects (font (size 1.27 1.27))))
        )''')
    else:
        for row in range(rows):
            y = (rows - 1) * 1.27 - row * 2.54
            left_number = str(row * 2 + 1)
            right_number = str(row * 2 + 2)
            pins.append(f'''        (pin passive line (at -5.08 {fmt(y)} 0) (length 2.54)
          (name {q(left_number)} (effects (font (size 1.27 1.27))))
          (number {q(left_number)} (effects (font (size 1.27 1.27))))
        )''')
            pins.append(f'''        (pin passive line (at 5.08 {fmt(y)} 180) (length 2.54)
          (name {q(right_number)} (effects (font (size 1.27 1.27))))
          (number {q(right_number)} (effects (font (size 1.27 1.27))))
        )''')
    return f'''    (symbol {q(lib_id)}
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "J" (at 0 {fmt(half_height + 2.54)} 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" {q(symbol_name)} (at 0 {fmt(-half_height - 2.54)} 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "{symbol_name}_0_1"
        (rectangle (start -2.54 {fmt(half_height)}) (end 2.54 {fmt(-half_height)})
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
{chr(10).join(pins)}
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


def resolve_symbol_pin_number(lib_id: str, pin_number: str) -> str:
    """Return the real symbol pin number when a semantic alias is used."""
    raw = str(pin_number).strip()
    if not raw:
        return ''
    pin_map = parse_symbol_pin_map(lib_id)
    pin_data = pin_map.get(raw) or pin_map.get(raw.upper())
    if isinstance(pin_data, dict):
        resolved = str(pin_data.get('number', '')).strip()
        if resolved:
            return resolved
    return raw


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
    unit = int(symbol.get('unit', 1) or 1)
    ref = str(symbol.get('ref', 'U?'))
    lib_id = str(symbol.get('lib_id', 'AIAgent:Generic_2Pin'))
    value = str(symbol.get('value', ''))
    footprint = str(symbol.get('footprint', ''))
    pins = symbol.get('pins', [])
    if not isinstance(pins, list):
        pins = []

    pin_lines = []
    pin_numbers = [
        resolve_symbol_pin_number(lib_id, str(pin.get('number', '')))
        for pin in pins
        if isinstance(pin, dict) and str(pin.get('number', ''))
    ]
    if not symbol.get('unit_placeholder'):
        for real_pin in symbol_real_pin_numbers(lib_id, unit=unit):
            pin_numbers.append(real_pin)
    if not pin_numbers and not symbol.get('unit_placeholder'):
        pin_numbers = ['1', '2']
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
    (unit {unit})
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
          (unit {unit})
        )
      )
    )
  )'''


def automatic_power_flags_for_net_names(
    net_names: set[str],
    kind_map: dict[str, str],
    start_index: int = 1,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for position_index, name in enumerate(sorted(net_names), start=1):
        kind = effective_net_kind(name, kind_map.get(name, '').strip())
        if kind not in {'power', 'ground'} or not name:
            continue
        ref_index = start_index + position_index - 1
        flags.append(
            {
                'ref': f'#FLG{ref_index:03d}',
                'value': 'PWR_FLAG',
                'lib_id': 'power:PWR_FLAG',
                'footprint': '',
                'at': {'x': 30.48, 'y': 106.68 + position_index * 7.62, 'rotation': 0.0},
                'pins': [{'number': '1', 'net': name}],
            }
        )
    return flags


def automatic_power_flags(plan: dict[str, Any]) -> list[dict[str, Any]]:
    kind_map = net_kind_by_name(plan)
    net_names = {str(net.get('name', '')).strip() for net in plan.get('nets', []) if isinstance(net, dict)}
    return automatic_power_flags_for_net_names(net_names, kind_map)


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


def direct_intra_module_wiring_enabled() -> bool:
    value = env('KICAD_DIRECT_INTRA_MODULE_WIRING', '').strip().lower()
    return value in {'1', 'true', 'yes', 'on'}


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
    suppress_labels: set[tuple[str, str]] = set()
    if direct_intra_module_wiring_enabled():
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
            x, y, direction = pin_endpoint(symbol, pin_number)
            if (ref, pin_number) in suppress_labels and net_name not in force_global_nets:
                continue
            stub = 3.81
            label_x = x - stub if direction == 180.0 else x + stub if direction == 0.0 else x
            label_y = y + stub if direction == 90.0 else y - stub if direction == 270.0 else y
            blocks.append(f'''  (wire (pts (xy {fmt(x)} {fmt(y)}) (xy {fmt(label_x)} {fmt(label_y)}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )''')
            label_key = (net_name, round(label_x, 3), round(label_y, 3))
            kind = effective_net_kind(net_name, kind_map.get(net_name, 'signal'))
            justify = 'right' if direction == 180.0 else 'left' if direction == 0.0 else 'center'
            justify_effect = f' (justify {justify})' if justify != 'center' else ''
            if label_key in rendered_labels:
                continue
            rendered_labels.add(label_key)
            if net_name in force_global_nets or kind in {'ground', 'power'}:
                blocks.append(f'''  (global_label {q(net_name)} (shape {label_shape(kind)}) (at {fmt(label_x)} {fmt(label_y)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
            else:
                blocks.append(f'''  (label {q(net_name)} (at {fmt(label_x)} {fmt(label_y)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
        lib_id_str = str(symbol.get('lib_id', ''))
        if lib_id_str:
            if symbol.get('unit_placeholder') and symbol.get('suppress_no_connect'):
                continue
            connected_pins = {str(pin.get('number', '')).strip() for pin in pins if isinstance(pin, dict)}
            connected_pin_coords: set[tuple[float, float]] = set()
            for connected_pin in connected_pins:
                if not connected_pin:
                    continue
                cx, cy, _ = pin_endpoint(symbol, connected_pin)
                connected_pin_coords.add((round(cx, 3), round(cy, 3)))
            connected_pin_aliases: set[str] = set()
            for connected_pin in connected_pins:
                if not connected_pin:
                    continue
                connected_pin_aliases.add(connected_pin)
                connected_pin_aliases.add(connected_pin.upper())
                resolved_pin = resolve_symbol_pin_number(lib_id_str, connected_pin)
                if resolved_pin:
                    connected_pin_aliases.add(resolved_pin)
                    connected_pin_aliases.add(resolved_pin.upper())
                normalized_pin = re.sub(r'[^A-Z0-9]+', '_', connected_pin.upper()).strip('_')
                if normalized_pin:
                    connected_pin_aliases.add(normalized_pin)
            try:
                pin_map = parse_symbol_pin_map(lib_id_str)
            except Exception:
                pin_map = {}
            if len(pin_map) > 2:
                real_pins: dict[str, dict[str, Any]] = {}
                connected_real_pins: set[str] = set()
                for alias, pin_info in pin_map.items():
                    real_pin_number = str(pin_info.get('number', alias)).strip()
                    if not real_pin_number:
                        continue
                    real_pins.setdefault(real_pin_number, pin_info)
                    if alias in connected_pin_aliases or real_pin_number in connected_pin_aliases or real_pin_number.upper() in connected_pin_aliases:
                        connected_real_pins.add(real_pin_number)
                for pin_number in sorted(real_pins, key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value))):
                    if pin_number in connected_real_pins:
                        continue
                    x, y, _direction = pin_endpoint(symbol, pin_number)
                    if (round(x, 3), round(y, 3)) in connected_pin_coords:
                        continue
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
    single_sheet_name = sheet_order[0] if len(sheet_order) == 1 else ''
    for symbol in symbols:
        block = symbol_block(symbol)
        sheet = block_to_sheet.get(block, single_sheet_name or block)
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


def add_missing_unit_placeholders(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    placed_units = {
        (str(symbol.get('ref', '')), int(symbol.get('unit', 1) or 1))
        for symbol in symbols
        if isinstance(symbol, dict) and str(symbol.get('ref', '')).strip()
    }
    for symbol in symbols:
        if not isinstance(symbol, dict):
            continue
        ref = str(symbol.get('ref', '')).strip()
        lib_id = str(symbol.get('lib_id', '')).strip()
        if not ref or not lib_id:
            expanded.append(symbol)
            continue
        units = symbol_unit_numbers(lib_id)
        if len(units) <= 1:
            expanded.append(symbol)
            continue
        base_unit = int(symbol.get('unit', 1) or 1)
        original_pins = [pin for pin in symbol.get('pins', []) if isinstance(pin, dict)]
        base_symbol = dict(symbol)
        base_symbol['pins'] = [
            pin for pin in original_pins
            if symbol_pin_unit(lib_id, str(pin.get('number', ''))) == base_unit
        ]
        expanded.append(base_symbol)
        at = dict(symbol.get('at', {})) if isinstance(symbol.get('at', {}), dict) else {}
        base_x = float(at.get('x', 50.8))
        base_y = float(at.get('y', 50.8))
        for unit in units:
            if unit <= 1 or (ref, unit) in placed_units:
                continue
            placeholder = dict(symbol)
            placeholder['unit'] = unit
            placeholder['unit_placeholder'] = True
            placeholder['pins'] = [
                pin for pin in original_pins
                if symbol_pin_unit(lib_id, str(pin.get('number', ''))) == unit
            ]
            placeholder_at = dict(at)
            placeholder_at['x'] = base_x + 35.56 * (unit - 1)
            placeholder_at['y'] = base_y
            placeholder['at'] = placeholder_at
            expanded.append(placeholder)
            placed_units.add((ref, unit))
    return expanded


def render_sheet_instances(sheet_pages: list[dict[str, Any]]) -> str:
    lines = ['  (sheet_instances', '    (path "/" (page "1"))']
    for index, page in enumerate(sheet_pages, start=2):
        lines.append(f'    (path {q(page["path"])} (page {q(str(index))}))')
    lines.append('  )')
    return '\n'.join(lines)


def render_schematic(plan: dict[str, Any]) -> str:
    symbols = add_missing_unit_placeholders([symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)])
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
  )'''


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
    power_flag_nets: set[str] | None = None,
) -> str:
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    page_symbols = add_missing_unit_placeholders(shifted_symbols_for_page(symbols))
    page_net_names = {
        str(pin.get('net', '')).strip()
        for symbol in page_symbols
        for pin in symbol.get('pins', [])
        if isinstance(pin, dict) and str(pin.get('net', '')).strip()
    }
    try:
        page_index = int(str(page.get('file', '0')).split('_', 1)[0])
    except ValueError:
        page_index = 1
    if power_flag_nets is None:
        power_flag_nets = power_flag_net_names(page_net_names, net_kind_by_name(plan))
    page_symbols.extend(automatic_power_flags_for_net_names(power_flag_nets, net_kind_by_name(plan), start_index=page_index * 100))
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
    # They should still use global power labels inside that sheet.
    net_kind_lookup = {str(net.get('name', '')): str(net.get('kind', 'signal')) for net in plan.get('nets', []) if isinstance(net, dict)}
    local_power_nets: dict[str, set[str]] = {}
    for net in plan.get('nets', []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get('name', '')).strip()
        kind = effective_net_kind(net_name, str(net.get('kind', 'signal')))
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

    flag_page_by_net: dict[str, str] = {}
    for page in sheet_pages:
        page_net_names = {
            str(pin.get('net', '')).strip()
            for symbol in page.get('symbols', [])
            if isinstance(symbol, dict)
            for pin in symbol.get('pins', [])
            if isinstance(pin, dict) and str(pin.get('net', '')).strip()
        }
        for net_name in power_flag_net_names(page_net_names, net_kind_lookup):
            flag_page_by_net.setdefault(net_name, str(page['name']))

    schematic_file.write_text(render_root_schematic(plan, sheet_pages) + '\n', encoding='utf-8')
    for page in sheet_pages:
        child_path = schematic_file.parent / page['file']
        page_power_flags = {
            net_name
            for net_name, page_name in flag_page_by_net.items()
            if page_name == str(page['name'])
        }
        child_path.write_text(
            render_child_schematic(
                plan=plan,
                page=page,
                symbols=page['symbols'],
                sheet_pages=sheet_pages,
                cross_nets=set(page['pins']),
                power_flag_nets=page_power_flags,
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
        'erc': {
            'erc_exclusions': [],
            'meta': {
                'version': 0,
            },
            'pin_map': DEFAULT_ERC_PIN_MAP,
            'rule_severities': DEFAULT_ERC_RULE_SEVERITIES,
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

    # Pin the project-local JLC libraries KiCad will need after postprocess.
    # The library sync step runs after the project file is first written, so
    # these expected paths must not depend on files already existing.
    if output_dir:
        output_path = Path(output_dir)
        pinned_sym: list[dict[str, str]] = []
        pinned_fp: list[dict[str, str]] = [{
            "name": "JLC-MCP",
            "type": "KiCad",
            "uri": "libraries/footprints/JLC-MCP.pretty",
            "options": "",
            "description": "JLC-MCP footprints",
        }]

        symbols_dir = output_path / 'libraries' / 'symbols'
        symbol_files = sorted(symbols_dir.glob('*.kicad_sym')) if symbols_dir.exists() else []
        for symbol_file in symbol_files:
            pinned_sym.append({
                "name": symbol_file.stem,
                "type": "KiCad",
                "uri": f"libraries/symbols/{symbol_file.name}",
                "options": "",
                "description": f"JLC-MCP {symbol_file.stem}",
            })

        project_json['libraries'] = {
            'pinned_footprint_libs': pinned_fp,
            'pinned_symbol_libs': pinned_sym,
        }

    return json.dumps(project_json, ensure_ascii=False, indent=2) + '\n'


def _find_jlc_lib_dir(output_dir: Path) -> Path | None:
    """Find the JLC footprint library directory relative to the project."""
    for candidate in [
        output_dir / 'libraries' / 'footprints' / 'JLC-MCP.pretty',
        output_dir / 'libs' / 'JLC-MCP.pretty',
        output_dir.parent / 'libs' / 'JLC-MCP.pretty',
        Path(env('KICAD_SOURCE_PROJECT_DIR', '')) / 'libraries' / 'footprints' / 'JLC-MCP.pretty',
    ]:
        if candidate.exists():
            return candidate
    return None


def _find_jlc_sym_file(output_dir: Path) -> Path | None:
    """Find the JLC symbol library file relative to the project."""
    for candidate in [
        output_dir / 'libraries' / 'symbols' / 'EasyEDA-local.kicad_sym',
        output_dir / 'libs' / 'jlc_symbols.kicad_sym',
        output_dir.parent / 'libs' / 'jlc_symbols.kicad_sym',
        Path(env('KICAD_SOURCE_PROJECT_DIR', '')) / 'libraries' / 'symbols' / 'EasyEDA-local.kicad_sym',
    ]:
        if candidate.exists():
            return candidate
    return None


def write_fp_lib_table(output_dir: Path) -> None:
    """Write fp-lib-table and sym-lib-table with project-relative paths.

    Uses bare relative paths (no ${KIPRJMOD}) so the project is portable
    across machines. KiCad resolves bare relative URIs against the
    directory containing the .kicad_pro file.
    """
    lines = ['(fp_lib_table', '  (version 7)']

    # Repo-managed footprints (AIAgent, JLC-MCP, etc.).  Use project-local
    # paths like "libraries/footprints/<name>.pretty" — postprocess is
    # responsible for copying the .kicad_mod files into the output directory
    # before KiCad opens the project.  This avoids fragile repo-relative
    # "../../.." paths that break when the output tree depth changes.
    repo_fp = REPO_ROOT / 'resources' / 'kicad' / 'footprints'
    if repo_fp.exists():
        for pretty_dir in sorted(repo_fp.glob('*.pretty')):
            lib_name = pretty_dir.name.rsplit('.', 1)[0]
            uri = f'libraries/footprints/{pretty_dir.name}'
            lines.append(f'  (lib (name "{lib_name}")(type "KiCad")(uri "{uri}")(options "")(descr "AIAgent custom footprints"))')

    # JLC/LCSC imported footprints. Register the expected project-local path
    # even before postprocess copies the library into the output directory.
    lines.append('  (lib (name "JLC-MCP")(type "KiCad")(uri "libraries/footprints/JLC-MCP.pretty")(options "")(descr "JLC-MCP footprints"))')

    lines.append(')\n')
    content = '\n'.join(lines)
    (output_dir / 'fp-lib-table').write_text(content, encoding='utf-8')

    # Also write sym-lib-table for JLC symbols
    output_resolved = output_dir.resolve()
    jlc_sym = _find_jlc_sym_file(output_dir)
    if jlc_sym:
        try:
            rel = Path(os.path.relpath(str(jlc_sym.resolve()), str(output_resolved)))
        except ValueError:
            rel = jlc_sym
        uri = str(rel).replace('\\', '/')
        sym_content = f'(sym_lib_table\n  (version 7)\n  (lib (name "jlc_symbols")(type "KiCad")(uri "{uri}")(options "")(descr "JLC/LCSC imported symbols"))\n)\n'
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
    hierarchical = env('KICAD_HIERARCHICAL_SHEETS', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
    hierarchical_summary: dict[str, Any] = {}
    if hierarchical:
        hierarchical_summary = write_hierarchical_project(plan, output_dir, schematic_file)
    else:
        schematic_file.write_text(render_schematic(plan) + '\n', encoding='utf-8')

    summary = {
        'schema_version': KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION,
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
