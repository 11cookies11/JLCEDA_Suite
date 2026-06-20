#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..shared.env_utils import env
from .kicad_project_resources import (
    load_project_dsl_sheets,
    write_fp_lib_table,
)
from .kicad_symbol_library import (
    installed_symbol_block,
    kicad_symbol_roots,
    load_installed_symbol,
    local_h618_minimal_symbol,
    local_symbol_library,
    normalize_connector_pin_types,
    normalize_passive_component_pin_types,
    parse_symbol_pin_map,
    symbol_block_for_lib_id,
    symbol_block_with_default_footprint,
    symbol_pin_unit,
    symbol_real_pin_numbers,
    symbol_unit_numbers,
)
from .pcb_generator import generate_pcb  # re-export for PyInstaller visibility
from ..shared.schema_versions import KICAD_EXECUTION_PLAN_SCHEMA_VERSION, KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION
from ..domain.core.schematic_layout_rules import BlockLayoutRule, build_default_layout_rules, _resolve_wiring_block

KICAD_SCHEMATIC_FILE_VERSION = '20250114'
REPO_ROOT = Path(__file__).resolve().parents[2]
SYMBOL_PIN_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
SYMBOL_UNIT_CACHE: dict[str, list[int]] = {}
PIN_LEN = 2.54  # standard KiCad pin line length, mm
_PROJECT_PATH: Path | None = None  # set by write_project before rendering

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
    "isolated_pin_label": "ignore",
    "label_dangling": "ignore",
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
    "no_connect_dangling": "ignore",
    "pin_not_connected": "ignore",
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
    "unconnected_wire_endpoint": "ignore",
    "undefined_netclass": "error",
    "unit_value_mismatch": "error",
    "unresolved_variable": "error",
    "wire_dangling": "error",
}


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
    lib_ids = sorted({str(symbol.get('lib_id', '')).strip() for symbol in symbols})
    if any(not lib_id for lib_id in lib_ids):
        raise ValueError('Every KiCad symbol instance must provide an explicit lib_id.')
    footprints_by_lib_id: dict[str, str] = {}
    for symbol in symbols:
        lib_id = str(symbol.get('lib_id', '')).strip()
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

    Priority: project-local (from _PROJECT_PATH) > repo-bundled > CWD > KiCad system.
    """
    roots: list[Path] = []

    def _add_if_exists(path: Path) -> None:
        if path.exists() and path not in roots:
            roots.append(path)

    # 1. Project-local libraries (highest priority ?? resolve-symbols output)
    if _PROJECT_PATH:
        _add_if_exists(_PROJECT_PATH / 'libraries' / 'symbols')
    # Derive project root from output dir: {project}/output ?? project root
    out_env = env('KICAD_OUTPUT_DIR', '')
    if out_env:
        _add_if_exists(Path(out_env).parent / 'libraries' / 'symbols')

    # 2. Repo-bundled symbols
    _add_if_exists(REPO_ROOT / 'resources' / 'kicad' / 'symbols')

    # 3. Output directory
    output_root = env('KICAD_OUTPUT_DIR', '')
    if output_root:
        _add_if_exists(Path(output_root) / 'libs')
        try:
            for subdir in Path(output_root).iterdir():
                if subdir.is_dir():
                    _add_if_exists(subdir / 'libraries' / 'symbols')
        except OSError:
            pass

    # 4. CWD and parents
    try:
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents)[:4]:
            _add_if_exists(parent / 'libraries' / 'symbols')
    except OSError:
        pass

    # 5. KiCad system libraries (lowest priority)
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
    safe_symbol_name = _sanitize_symbol_name(symbol_name)
    if safe_symbol_name != symbol_name:
        block = block.replace(symbol_name, safe_symbol_name)
    block = block.replace(f'(symbol "{safe_symbol_name}"', f'(symbol "{library}:{safe_symbol_name}"', 1)
    return strip_symbol_lib_id(block)


def strip_symbol_lib_id(block: str) -> str:
    """Remove accidental schematic-instance lib_id markers from library symbol blocks."""
    lines = block.splitlines()
    filtered = [line for line in lines if '(lib_id ' not in line]
    return '\n'.join(filtered)


def sanitize_lib_symbols_section(text: str) -> str:
    """Ensure the top-level lib_symbols section only contains library-symbol syntax."""
    lib_start = text.find('(lib_symbols')
    if lib_start < 0:
        return text
    lib_end = find_matching_paren(text, lib_start)
    if lib_end < 0:
        return text
    section = text[lib_start:lib_end + 1]
    cleaned = strip_symbol_lib_id(section)
    return text[:lib_start] + cleaned + text[lib_end + 1:]


def _sanitize_symbol_name(name: str) -> str:
    """Return a KiCad-safe symbol name."""
    cleaned = name.replace(' ', '_').replace(':', '_').replace('/', '_')
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', cleaned)
    return cleaned.strip('._-') or 'UNKNOWN'


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
        candidate_files = _candidate_symbol_library_files(root, library)
        for symbol_file in candidate_files:
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
        for symbol_file in _candidate_symbol_library_files(root, library):
            if not symbol_file.exists():
                continue
            text = symbol_file.read_text(encoding='utf-8')
            start = text.find(needle)
            if start < 0:
                continue
            end = find_matching_paren(text, start)
            if end >= 0:
                return strip_symbol_lib_id(text[start:end + 1])
    return ''


def _candidate_symbol_library_files(root: Path, library: str) -> list[Path]:
    """Return symbol library files to inspect for a given library name."""
    files: list[Path] = []
    exact = root / f'{library}.kicad_sym'
    if exact.exists():
        files.append(exact)
    if library == 'JLC-MCP':
        for extra in sorted(root.glob('JLC-MCP*.kicad_sym')):
            if extra not in files:
                files.append(extra)
    return files


def symbol_block_for_lib_id(lib_id: str) -> str:
    if ':' in lib_id:
        library, symbol_name = lib_id.split(':', 1)
        installed = load_installed_symbol(library, symbol_name)
        if installed and symbol_name == 'ALLWINNERH618' and '(pin ' not in installed:
            return local_h618_minimal_symbol(lib_id)
        if installed:
            normalized = normalize_connector_pin_types(installed, symbol_name)
            normalized = normalize_passive_component_pin_types(normalized, symbol_name)
            return strip_symbol_lib_id(normalized)
        system_block = installed_symbol_block(library, symbol_name)
        if system_block:
            if symbol_name == 'ALLWINNERH618' and '(pin ' not in system_block:
                return local_h618_minimal_symbol(lib_id)
            normalized = normalize_embedded_symbol_name(system_block, library, symbol_name)
            normalized = normalize_connector_pin_types(normalized, symbol_name)
            normalized = normalize_passive_component_pin_types(normalized, symbol_name)
            return '\n'.join(f'    {line}' if line.strip() else line for line in strip_symbol_lib_id(normalized).splitlines())

    raise ValueError(f'KiCad symbol not found: {lib_id}')


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

    # No Footprint property ?? insert one after the Value property block
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
                gpio_match = re.fullmatch(r'IO(\d+)', normalized)
                if gpio_match:
                    aliases.add(f'GPIO{gpio_match.group(1)}')
                gpio_match = re.fullmatch(r'GPIO(\d+)', normalized)
                if gpio_match:
                    aliases.add(f'IO{gpio_match.group(1)}')
                if normalized == 'RXD0':
                    aliases.add('U0RXD')
                elif normalized == 'TXD0':
                    aliases.add('U0TXD')
                elif normalized == 'U0RXD':
                    aliases.add('RXD0')
                elif normalized == 'U0TXD':
                    aliases.add('TXD0')
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


def pin_endpoint(symbol: dict[str, Any], pin_number: str) -> tuple[float, float, float] | None:
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

    # Pin not found in symbol ?? return None to avoid fake default positions
    # that would collide with other pins (ERC multiple_net_names).
    return None


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
    lib_id = str(symbol.get('lib_id', '')).strip()
    if not lib_id:
        raise ValueError(f'Symbol instance {ref} has no explicit lib_id.')
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
    driven_power_nets = power_output_net_names(plan.get('symbols', []))
    # Board-local regulator rails are driven by their regulator output symbols.
    # Some imported JLC symbols are not always parseable early enough for
    # power_output_net_names(), so keep this conservative board-local fallback.
    driven_power_nets.update({name for name in net_names if name.upper() in {'+3V3_MAIN'}})
    return automatic_power_flags_for_net_names(net_names - driven_power_nets, kind_map)


def symbol_by_ref(symbols: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(symbol.get('ref', '')).upper(): symbol for symbol in symbols}


def parse_member_ref_pin(member: str) -> tuple[str, str]:
    if '.' not in member:
        return '', ''
    ref, pin = member.split('.', 1)
    return ref.strip().upper(), pin.strip().upper()


def render_connectivity(
    plan: dict[str, Any],
    symbols: list[dict[str, Any]] | None = None,
    force_global_nets: set[str] | None = None,
    force_hierarchical_nets: set[str] | None = None,
) -> str:
    kind_map = net_kind_by_name(plan)
    blocks: list[str] = []
    if symbols is None:
        symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
    if force_global_nets is None:
        force_global_nets = set()
    if force_hierarchical_nets is None:
        force_hierarchical_nets = set()
    rendered_labels: set[tuple[str, str, float, float]] = set()
    rendered_hierarchical_nets: set[str] = set()
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
            endpoint = pin_endpoint(symbol, pin_number)
            if endpoint is None:
                continue  # pin not in symbol, skip
            x, y, direction = endpoint
            stub = 3.81
            label_x = x - stub if direction == 180.0 else x + stub if direction == 0.0 else x
            label_y = y + stub if direction == 90.0 else y - stub if direction == 270.0 else y
            # Avoid label position collisions across different nets: offset
            # vertically when two nets would share the same (x, y) coordinate
            # (prevents ERC multiple_net_names / unconnected_wire_endpoint).
            pos_key = (round(label_x, 3), round(label_y, 3))
            offset = 0.0
            while pos_key in rendered_labels:
                offset += 2.54
                if direction in {0.0, 180.0}:
                    shifted_x = label_x + offset if direction == 0.0 else label_x - offset
                    pos_key = (round(shifted_x, 3), round(label_y, 3))
                else:
                    shifted_y = label_y + offset if direction == 90.0 else label_y - offset
                    pos_key = (round(label_x, 3), round(shifted_y, 3))
            rendered_labels.add(pos_key)
            lx = pos_key[0]
            ly = pos_key[1]
            blocks.append(f'''  (wire (pts (xy {fmt(x)} {fmt(y)}) (xy {fmt(lx)} {fmt(ly)}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )''')
            kind = effective_net_kind(net_name, kind_map.get(net_name, 'signal'))
            justify = 'right' if direction == 180.0 else 'left' if direction == 0.0 else 'center'
            justify_effect = f' (justify {justify})' if justify != 'center' else ''
            if net_name in force_hierarchical_nets and net_name not in rendered_hierarchical_nets:
                blocks.append(f'''  (hierarchical_label {q(net_name)} (shape {label_shape(kind)}) (at {fmt(lx)} {fmt(ly)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
                rendered_hierarchical_nets.add(net_name)
            elif net_name in force_hierarchical_nets:
                # The first attached hierarchical label joins the child sheet
                # to its parent pin.  Other occurrences stay local so the
                # page does not become a field of duplicate port diamonds.
                blocks.append(f'''  (label {q(net_name)} (at {fmt(lx)} {fmt(ly)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
            elif net_name in force_global_nets or kind in {'ground', 'power'}:
                blocks.append(f'''  (global_label {q(net_name)} (shape {label_shape(kind)}) (at {fmt(lx)} {fmt(ly)} 0)
    (effects (font (size 1.27 1.27)){justify_effect})
    (uuid {q(new_uuid())})
  )''')
            else:
                blocks.append(f'''  (label {q(net_name)} (at {fmt(lx)} {fmt(ly)} 0)
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
                ep = pin_endpoint(symbol, connected_pin)
                if ep is None:
                    continue
                cx, cy, _ = ep
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
                    ep = pin_endpoint(symbol, pin_number)
                    if ep is None:
                        continue
                    x, y, _direction = ep
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


def _sheet_file_stem(index: int, sheet_name: str) -> str:
    """Build a stable child schematic stem without duplicating numeric prefixes."""
    cleaned = sanitize_sheet_name(sheet_name)
    while True:
        stripped = re.sub(r'^\d+[_-]+', '', cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = cleaned.strip('._-') or 'sheet'
    return f'{index:02d}_{cleaned}'


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


def _default_sheet_groups() -> list[dict[str, Any]]:
    """Return a sensible built-in sheet grouping when no profile is available."""
    return [
        {"name": "01_power", "blocks": ["input", "power_reg", "power_decouple", "power"]},
        {"name": "02_mcu", "blocks": ["mcu", "crystal", "reset", "boot", "memory", "rf"]},
        {"name": "03_io", "blocks": ["debug", "indicator", "io", "output", "feedback"]},
        {"name": "04_other", "blocks": ["power_stage", "strap"]},
    ]


def group_symbols_by_sheet(
    symbols: list[dict[str, Any]], topology: str = '',
    dsl_sheets: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Group symbols into sheets.

    Priority: DSL ``sheets`` field > profile ``sheet_groups`` > built-in defaults.
    """
    pages: dict[str, list[dict[str, Any]]] = {}
    ref_to_symbol = {str(s.get('ref', '')): s for s in symbols}

    # -- 1. DSL sheets (from circuit-model.json) --------------------------
    if dsl_sheets:
        for sheet in dsl_sheets:
            name = sanitize_sheet_name(str(sheet.get('name', '')).strip())
            comp_refs = sheet.get('components', [])
            if not name or not isinstance(comp_refs, list):
                continue
            for ref in comp_refs:
                sym = ref_to_symbol.get(str(ref))
                if sym:
                    pages.setdefault(name, []).append(sym)
        if pages:
            return pages

    # -- 2. Profile / built-in block grouping ------------------------------
    order = build_default_layout_rules().block_layout.block_order
    order_index = {name: index for index, name in enumerate(order)}
    block_to_sheet: dict[str, str] = {}
    sheet_order: list[str] = []
    groups = configured_sheet_groups(topology) or _default_sheet_groups()
    for group in groups:
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



def render_schematic_decorations(plan: dict[str, Any]) -> str:
    """Render optional flat-sheet frames and section titles."""
    blocks: list[str] = []
    for item in plan.get('decorations', []):
        if not isinstance(item, dict):
            continue
        kind = str(item.get('type', ''))
        if kind == 'frame':
            x1, y1 = float(item['x1']), float(item['y1'])
            x2, y2 = float(item['x2']), float(item['y2'])
            blocks.append(f'''  (polyline
    (pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)}) (xy {fmt(x1)} {fmt(y2)}) (xy {fmt(x1)} {fmt(y1)}))
    (stroke (width 0.5) (type dash) (color 80 80 80 0))
    (fill (type none))
    (uuid {q(new_uuid())})
  )''')
        elif kind == 'title':
            blocks.append(f'''  (text {q(str(item.get('text', '')))}
    (exclude_from_sim no)
    (at {fmt(float(item['x']))} {fmt(float(item['y']))} 0)
    (effects (font (size 2 2) (bold yes)) (justify left bottom))
    (uuid {q(new_uuid())})
  )''')
    return '\n'.join(blocks)

def render_schematic(plan: dict[str, Any], include_power_flags: bool = True) -> str:
    symbols = add_missing_unit_placeholders([symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)])
    if include_power_flags:
        symbols.extend(automatic_power_flags(plan))
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    instances = '\n'.join(render_symbol_instance(symbol, project_name) for symbol in symbols)
    connectivity = render_connectivity(plan, symbols)
    decorations = render_schematic_decorations(plan)
    return f'''(kicad_sch
  (version {KICAD_SCHEMATIC_FILE_VERSION})
  (generator "kicad-agent-suite")
  (generator_version "10.0")
  (uuid {q(new_uuid())})
  (paper {q(str(plan.get('paper', 'A4')))} )
{local_symbol_library(symbols)}
{instances}
{connectivity}
{decorations}
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


def render_sheet_pins(page: dict[str, Any], kind_map: dict[str, str]) -> str:
    pins = [str(name).strip() for name in page.get('ports', []) if str(name).strip()]
    if not pins:
        return ''
    x = float(page['x'])
    y = float(page['y'])
    w = float(page['w'])
    h = float(page['h'])
    left_count = (len(pins) + 1) // 2
    right_count = len(pins) // 2
    step = 7.62
    start_offset = 7.62
    lines: list[str] = []
    left_index = 0
    right_index = 0
    for index, pin_name in enumerate(pins):
        kind = effective_net_kind(pin_name, kind_map.get(pin_name, 'signal'))
        if index % 2 == 0 or right_count == 0:
            left_index += 1
            pin_x = x
            pin_y = y + start_offset + step * (left_index - 1)
            angle = 180.0
        else:
            right_index += 1
            pin_x = x + w
            pin_y = y + start_offset + step * (right_index - 1)
            angle = 0.0
        lines.append(render_sheet_pin(pin_name, kind, pin_x, pin_y, angle))
    return '\n'.join(lines)


def render_child_sheet_port_labels(page: dict[str, Any], kind_map: dict[str, str]) -> str:
    """Render unmatched child ports as a compact rail at the left page edge."""
    pins = [str(name).strip() for name in page.get('ports', []) if str(name).strip()]
    if not pins:
        return ''
    x = 5.08
    y0 = 20.32
    step = 5.08
    lines: list[str] = []
    for index, pin_name in enumerate(sorted(set(pins))):
        kind = effective_net_kind(pin_name, kind_map.get(pin_name, 'signal'))
        lines.append(render_hierarchical_label(pin_name, kind, x, y0 + index * step, 0.0, justify='left'))
    return '\n'.join(lines)


def render_root_sheet(page: dict[str, Any], kind_map: dict[str, str]) -> str:
    x = float(page['x'])
    y = float(page['y'])
    w = float(page['w'])
    h = float(page['h'])
    pins = render_sheet_pins(page, kind_map)
    pins_block = f'\n{pins}' if pins else ''
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
{pins_block}
  )'''


def render_root_schematic(plan: dict[str, Any], sheet_pages: list[dict[str, Any]]) -> str:
    kind_map = net_kind_by_name(plan)
    sheets = '\n'.join(render_root_sheet(page, kind_map) for page in sheet_pages)
    return sanitize_lib_symbols_section(f'''(kicad_sch
  (version {KICAD_SCHEMATIC_FILE_VERSION})
  (generator "kicad-agent-suite")
  (generator_version "10.0")
  (uuid {q(new_uuid())})
  (paper "A4")
  (lib_symbols)
{sheets}
{render_sheet_instances(sheet_pages)}
)''')


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
    driven_power_nets = power_output_net_names(plan.get('symbols', []))
    driven_power_nets.update({name for name in page_net_names if name.upper() in {'+3V3_MAIN'}})
    power_flag_nets = set(power_flag_nets) - driven_power_nets
    page_symbols.extend(automatic_power_flags_for_net_names(power_flag_nets, net_kind_by_name(plan), start_index=page_index * 100))
    instances = '\n'.join(render_symbol_instance_at_path(symbol, project_name, page['path']) for symbol in page_symbols)
    connectivity = render_connectivity(
        plan,
        page_symbols,
        force_global_nets=set(),
        force_hierarchical_nets=cross_nets,
    )
    sheet_port_labels = render_child_sheet_port_labels(page, net_kind_by_name(plan))
    return sanitize_lib_symbols_section(f'''(kicad_sch
  (version {KICAD_SCHEMATIC_FILE_VERSION})
  (generator "kicad-agent-suite")
  (generator_version "10.0")
  (uuid {q(new_uuid())})
  (paper "A4")
{local_symbol_library(page_symbols)}
{instances}
{connectivity}
{sheet_port_labels}
{render_sheet_instances(sheet_pages)}
)''')


def write_hierarchical_project(
    plan: dict[str, Any], output_dir: Path, schematic_file: Path,
    dsl_sheets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base_symbols = [symbol for symbol in plan.get('symbols', []) if isinstance(symbol, dict)]
    target = plan.get('target', {})
    project_name = str(target.get('project_name', 'kicad_agent_project')) if isinstance(target, dict) else 'kicad_agent_project'
    # The plan may not carry topology; prefer env var, else derive from project name
    topology = env('KICAD_TOPOLOGY', '') or project_name
    if dsl_sheets is None:
        plan_sheets = plan.get('sheets', [])
        if isinstance(plan_sheets, list) and plan_sheets:
            dsl_sheets = plan_sheets
    pages = group_symbols_by_sheet(base_symbols, topology, dsl_sheets=dsl_sheets)
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
        page_ports = sorted(net for net, net_pages in cross_net_pages.items() if name in net_pages)
        page_nets = sorted(set(page_ports) | local_power_nets.get(name, set()))
        height = max(20.32, 15.24 + len(page_nets) * 7.62)
        file_name = f'{_sheet_file_stem(index, name)}.kicad_sch'
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
                'ports': page_ports,
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

    _remove_stale_child_schematics(schematic_file.parent, [schematic_file.name, *(page['file'] for page in sheet_pages)])
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
                cross_nets=set(page['ports']),
                power_flag_nets=page_power_flags,
            ) + '\n',
            encoding='utf-8',
        )

    return {
        'sheet_count': len(sheet_pages) + 1,
        'root_schematic_file': str(schematic_file),
        'sheet_files': [str(schematic_file.parent / page['file']) for page in sheet_pages],
    }


def _remove_stale_child_schematics(directory: Path, keep_names: list[str]) -> None:
    """Remove old child schematic files before rewriting a hierarchical project."""
    if not directory.exists():
        return
    keep = {name for name in keep_names if name}
    for file_path in directory.glob('*.kicad_sch'):
        if file_path.name in keep:
            continue
        try:
            file_path.unlink()
        except OSError:
            pass


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


def write_single_page_project(
    plan: dict[str, Any],
    output_dir: Path,
    schematic_file: Path,
    dsl_sheets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write the standard single-page KiCad schematic.

    Source sheets remain a useful way to group design intent, but the exported
    project is deliberately a single KiCad sheet.  Each source group is packed
    into a separate framed area so sheet-local coordinates cannot overlap.
    """
    ref_to_sheet: dict[str, str] = {}
    for sheet in dsl_sheets or []:
        if not isinstance(sheet, dict):
            continue
        sheet_name = str(sheet.get('name', 'ungrouped'))
        for ref in sheet.get('components', []):
            ref_to_sheet[str(ref)] = sheet_name

    by_sheet: dict[str, list[dict[str, Any]]] = {}
    for symbol in plan.get('symbols', []):
        if not isinstance(symbol, dict):
            continue
        copied = dict(symbol)
        copied['assigned_sheet'] = ref_to_sheet.get(str(copied.get('ref', '')), 'ungrouped')
        by_sheet.setdefault(copied['assigned_sheet'], []).append(copied)

    from ..domain.core.compile_kicad_execution_plan import _estimate_symbol_size

    group_layouts: list[dict[str, Any]] = []
    for sheet_name in sorted(by_sheet):
        source_group = by_sheet[sheet_name]
        measured: list[tuple[dict[str, Any], float, float]] = []
        for item in source_group:
            width, height = _estimate_symbol_size(str(item.get('lib_id', '')))
            measured.append((item, width + 22.86, height + 20.32))
        measured.sort(key=lambda entry: (entry[1] * entry[2], str(entry[0].get('ref', ''))), reverse=True)
        widest = max((entry[1] for entry in measured), default=0.0)
        columns = 2 if widest >= 55.0 else 3
        rows = (len(measured) + columns - 1) // columns
        column_widths = [0.0] * columns
        row_heights = [0.0] * rows
        for index, (_item, width, height) in enumerate(measured):
            column_widths[index % columns] = max(column_widths[index % columns], width)
            row_heights[index // columns] = max(row_heights[index // columns], height)
        column_gap = 12.7
        row_gap = 12.7
        local_width = sum(column_widths) + max(0, columns - 1) * column_gap
        local_height = sum(row_heights) + max(0, rows - 1) * row_gap
        x_offsets: list[float] = []
        cursor_x = 0.0
        for width in column_widths:
            x_offsets.append(cursor_x)
            cursor_x += width + column_gap
        y_offsets: list[float] = []
        cursor_y = 15.24
        for height in row_heights:
            y_offsets.append(cursor_y)
            cursor_y += height + row_gap
        placed: list[dict[str, Any]] = []
        for index, (item, width, height) in enumerate(measured):
            copied = dict(item)
            at = dict(item.get('at', {}))
            column, row = index % columns, index // columns
            at['x'] = round((x_offsets[column] + width / 2.0) / 2.54) * 2.54
            at['y'] = round((y_offsets[row] + height / 2.0) / 2.54) * 2.54
            copied['at'] = at
            placed.append(copied)
        group_layouts.append({
            'name': sheet_name,
            'symbols': placed,
            'width': local_width + 20.32,
            'height': local_height + 35.56,
        })

    flat_symbols: list[dict[str, Any]] = []
    decorations: list[dict[str, Any]] = []
    page_x, page_y = 25.4, 38.1
    group_gap_x, group_gap_y = 15.24, 20.32
    for row_start in range(0, len(group_layouts), 3):
        row_groups = group_layouts[row_start:row_start + 3]
        row_height = max(float(group['height']) for group in row_groups)
        cursor_x = page_x
        for group in row_groups:
            group_width = float(group['width'])
            group_height = float(group['height'])
            x1, y1 = cursor_x, page_y
            for symbol in group['symbols']:
                at = dict(symbol.get('at', {}))
                at['x'] = round((float(at.get('x', 0.0)) + x1 + 10.16) / 2.54) * 2.54
                at['y'] = round((float(at.get('y', 0.0)) + y1 + 17.78) / 2.54) * 2.54
                symbol['at'] = at
                flat_symbols.append(symbol)
            decorations.append({'type': 'frame', 'x1': x1, 'y1': y1, 'x2': x1 + group_width, 'y2': y1 + group_height})
            decorations.append({'type': 'title', 'text': str(group['name']).replace('_', ' ').upper(), 'x': x1 + 5.08, 'y': y1 + 7.62})
            cursor_x += group_width + group_gap_x
        page_y += row_height + group_gap_y

    single_page_plan = dict(plan)
    single_page_plan['symbols'] = flat_symbols
    single_page_plan['paper'] = 'A0'
    single_page_plan['decorations'] = decorations
    _remove_stale_child_schematics(output_dir, [schematic_file.name])
    schematic_file.write_text(render_schematic(single_page_plan) + '\n', encoding='utf-8')
    return {'single_page': True, 'section_count': len(group_layouts)}


def write_project(plan: dict[str, Any], project_path: str | Path | None = None) -> dict[str, Any]:
    global _PROJECT_PATH
    if project_path:
        _PROJECT_PATH = Path(project_path)
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

    # Read DSL sheet assignments if present
    dsl_sheets = None
    plan_sheets = plan.get('sheets', [])
    if isinstance(plan_sheets, list) and plan_sheets:
        dsl_sheets = plan_sheets
    elif _PROJECT_PATH:
        dsl_sheets = load_project_dsl_sheets(_PROJECT_PATH)

    single_page_summary = write_single_page_project(plan, output_dir, schematic_file, dsl_sheets=dsl_sheets)

    summary = {
        'schema_version': KICAD_PROJECT_WRITE_RESULT_SCHEMA_VERSION,
        'request_id': str(plan.get('request_id', '')),
        'project_file': str(project_file),
        'schematic_file': str(schematic_file),
        'symbol_count': len([item for item in plan.get('symbols', []) if isinstance(item, dict)]),
        'net_count': len([item for item in plan.get('nets', []) if isinstance(item, dict)]),
        'diagnostics': plan.get('diagnostics', {}),
    }
    summary.update(single_page_summary)
    summary_file = output_dir / 'kicad-write-summary.json'
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary['summary_file'] = str(summary_file)

    # Log build result ?? always logged regardless of how write_project is called
    _log_build(_PROJECT_PATH, summary, plan.get("diagnostics", {}))

    return summary


def _log_build(project_path: Path | None, summary: dict[str, Any], diagnostics: Any) -> None:
    """Append a build entry to the project's operations.jsonl."""
    if not project_path:
        return
    log_dir = project_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "operations.jsonl"
    diags = diagnostics if isinstance(diagnostics, dict) else {}
    unsupported = diags.get("unsupported", []) if isinstance(diags, dict) else []
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "op": "build",
        "ok": True,
        "symbols": summary.get("symbol_count", 0),
        "nets": summary.get("net_count", 0),
        "sheets": summary.get("hierarchical_sheets", {}).get("sheet_count", 0) if isinstance(summary.get("hierarchical_sheets"), dict) else 0,
        "build_warnings": len(unsupported),
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
