#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .env_utils import env, to_int_env
from .schema_versions import (
    CIRCUIT_MODEL_SCHEMA_VERSION,
    KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
    NETLIST_SCHEMA_VERSION,
)
from .env_utils import repo_root

REPO_ROOT = repo_root()
LAYOUT_PROFILES_CACHE: dict[str, Any] | None = None
FOOTPRINT_EXISTS_CACHE: dict[str, bool] = {}

# Role → (KiCad_lib:symbol, footprint_lib) fallback when no symbol map match.
from .symbol_footprint_resolver import _ROLE_FALLBACK


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


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f'{path} must contain a JSON object.')
    return payload


def load_symbol_map() -> dict[str, Any]:
    """Return an empty compatibility config.

    The old shared symbol rule table has been retired. Resolution now comes
    from ``selected_part`` plus a small set of built-in role templates.
    """
    return {}


def load_layout_profiles() -> dict[str, Any]:
    global LAYOUT_PROFILES_CACHE
    if LAYOUT_PROFILES_CACHE is not None:
        return LAYOUT_PROFILES_CACHE
    path = Path(env('KICAD_LAYOUT_PROFILES_FILE', str(REPO_ROOT / 'config' / 'kicad-layout-profiles.json')))
    LAYOUT_PROFILES_CACHE = load_json_file(path) if path.exists() else {'profiles': {}}
    return LAYOUT_PROFILES_CACHE


def layout_defaults() -> dict[str, Any]:
    defaults = load_layout_profiles().get('default', {})
    return defaults if isinstance(defaults, dict) else {}


def layout_numeric_setting(name: str, fallback: float) -> float:
    settings = layout_defaults().get('layout', {})
    if not isinstance(settings, dict):
        settings = {}
    try:
        return float(settings.get(name, fallback))
    except (TypeError, ValueError):
        return fallback


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if str(value):
        return [str(value)]
    return []


def mapping_matches(match: dict[str, Any], ref: str, role: str, value: str) -> bool:
    checks: list[bool] = []
    ref_upper = ref.upper()
    role_lower = role.lower()
    value_lower = value.lower()
    if 'ref' in match:
        checks.append(ref_upper == str(match['ref']).upper())
    if 'ref_prefix' in match:
        checks.append(any(ref_upper.startswith(prefix.upper()) for prefix in _as_list(match['ref_prefix'])))
    if 'role_contains' in match:
        checks.append(any(token.lower() in role_lower for token in _as_list(match['role_contains'])))
    if 'value_contains' in match:
        checks.append(any(token.lower() in value_lower for token in _as_list(match['value_contains'])))
    return all(checks) if checks else False


def symbol_mapping_for(component: dict[str, Any]) -> tuple[str, str, list[str]]:
    role = str(component.get('role', '')).strip().lower()
    ref = str(component.get('ref', '')).strip().upper()
    value = str(component.get('value', '')).strip().lower()
    selected = component.get('selected_part', {})
    if not isinstance(selected, dict):
        selected = {}
    package = str(
        selected.get('kicad_footprint_hint')
        or selected.get('package', '')
        or selected.get('mechanical_package', '')
    ).strip()
    notes: list[str] = []

    symbol_name = _selected_part_symbol_name(selected)
    if symbol_name:
        lib_id = f'JLC-MCP:{symbol_name}'
        notes.append('Resolved from selected_part; shared symbol rule table is retired.')
        return lib_id, resolve_footprint(package, str(selected.get('kicad_footprint_hint', ''))), notes

    # Role-based fallback to KiCad built-in symbols
    role_fallback = _ROLE_FALLBACK.get(role)
    if role_fallback:
        lib_sym, fp = role_fallback
        notes.append(f'Role "{role}" resolved to KiCad built-in {lib_sym} (selected_part missing or incomplete).')
        return lib_sym, resolve_footprint(package, fp), notes

    notes.append(f'Mapped unknown role "{role}" to local AIAgent:Generic_2Pin placeholder symbol.')
    return 'AIAgent:Generic_2Pin', normalize_footprint(package), notes


def _selected_part_symbol_name(selected: dict[str, Any]) -> str:
    """Derive a stable EasyEDA/JLC symbol name from selected_part."""
    for key in ('symbol_ref', 'symbol_name', 'kicad_symbol'):
        value = str(selected.get(key, '')).strip()
        if value:
            return _sanitize_symbol_name(value)
    for key in ('display_name', 'part_id', 'lcsc_id', 'mpn'):
        value = str(selected.get(key, '')).strip()
        if value:
            cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', value)
            return _sanitize_symbol_name(cleaned)
    return ''


def _sanitize_symbol_name(name: str) -> str:
    """Return a KiCad-safe symbol name."""
    cleaned = name.replace(' ', '_').replace(':', '_').replace('/', '_')
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', cleaned)
    return cleaned.strip('._-') or 'UNKNOWN'


def normalize_footprint(footprint: str) -> str:
    """Add JLC-MCP prefix if no library prefix is present."""
    if not footprint:
        return footprint
    if footprint.startswith('JLC-MCP:'):
        return footprint
    return f'JLC-MCP:{footprint}'


def _remap_jlc_footprint(fp: str) -> str:
    """Map a JLC-MCP footprint name to the closest KiCad system-library footprint."""
    name = fp.split(':', 1)[1] if ':' in fp else fp

    # Package patterns: match footprint geometry to KiCad library
    if name.startswith('R0') or name.startswith('R1'):
        # Resistor: e.g. R0603, R0402, R0805, R1206, R2512
        size = name[1:]  # e.g. "0603" from "R0603"
        return f'Resistor_SMD:R_{size}_{"1005" if size == "0402" else "1608" if size == "0603" else "2012" if size == "0805" else "3216" if size == "1206" else "6332"}Metric'
    if name.startswith('C0') or name.startswith('C1'):
        size = name[1:]
        return f'Capacitor_SMD:C_{size}_{"1005" if size == "0402" else "1608" if size == "0603" else "2012" if size == "0805" else "3216" if size == "1206" else "6332"}Metric'
    if name.startswith('LED0') or name.startswith('LED1'):
        size = name[3:7] if name.startswith('LED') else name[1:5]
        return f'LED_SMD:LED_{size}_{"1005" if size == "0402" else "1608" if size == "0603" else "2012" if size == "0805" else "3216"}Metric'
    if name.startswith('L0') or name.startswith('L1'):
        size = name[1:]
        return f'Inductor_SMD:L_{size}_{"1005" if size == "0402" else "1608" if size == "0603" else "2012" if size == "0805" else "3216"}Metric'

    # IC package patterns
    if 'QFN-32' in name or 'QFN32' in name:
        return 'Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm'
    if 'QFN-56' in name or 'LQFN-56' in name or 'QFN56' in name:
        return 'Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm'
    if 'QFN-20' in name or 'QFN20' in name:
        return 'Package_DFN_QFN:QFN-20-1EP_3x5mm_P0.5mm_EP1.45x2.9mm'
    if 'LQFP-48' in name or 'QFP-48' in name:
        return 'JLC-MCP:LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL'
    if 'LQFP-64' in name or 'QFP-64' in name:
        return 'Package_QFP:LQFP-64_10x10mm_P0.5mm'
    if 'LQFP-100' in name or 'QFP-100' in name:
        return 'Package_QFP:LQFP-100_14x14mm_P0.5mm'

    if 'SOT-23-6' in name or 'SOT23-6' in name:
        return 'Package_TO_SOT_SMD:SOT-23-6'
    if 'SOT-23-5' in name or 'TSOT-23-5' in name or 'SOT23-5' in name:
        return 'Package_TO_SOT_SMD:SOT-23-5'
    if 'SOT-23-3' in name or 'SOT-23_L' in name or 'SOT23-3' in name:
        return 'Package_TO_SOT_SMD:SOT-23'
    if 'SOT-223' in name:
        return 'Package_TO_SOT_SMD:SOT-223-3_TabPin2'

    if 'SOIC-16' in name and 'W' in name:
        return 'Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm'
    if 'SOIC-16' in name:
        return 'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm'
    if 'SOIC-8' in name or 'SOP-8' in name:
        return 'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm'
    if 'SOIC-14' in name or 'SOP-14' in name:
        return 'Package_SO:SOIC-14_3.9x8.7mm_P1.27mm'

    if 'SMB_' in name or 'SMB_L' in name:
        return 'Diode_SMD:D_SMB'

    if 'TO-252' in name:
        return 'Package_TO_SOT_SMD:TO-252-2'

    if 'USB-C' in name or 'TYPE-C' in name:
        return 'Connector_USB:USB_C_Receptacle_Amphenol_12401548E4-2A'

    if 'PWRM-TH' in name or 'SIP' in name and 'TH' in name:
        return 'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical'

    if 'CRYSTAL' in name:
        return 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm'

    # Fallback: return original — caller should still report it via diagnostics
    return fp


def _has_library_prefix(footprint: str) -> bool:
    """Check if a footprint string has the full 'Library:Name' format."""
    return ':' in footprint.strip()


def resolve_footprint(component_package: str, mapping_footprint: str) -> str:
    """Resolve footprint: prefer mapping footprint (JLC-MCP) over component package.

    KiCad requires the full 'Library:FootprintName' format. Short names like '0603'
    cause warnings and failures in KiCad.
    """
    if mapping_footprint and _has_library_prefix(mapping_footprint):
        return mapping_footprint
    if component_package and _has_library_prefix(component_package):
        return component_package
    if mapping_footprint:
        return normalize_footprint(mapping_footprint)
    if component_package:
        return normalize_footprint(component_package)
    return ''


def kicad_footprint_roots() -> list[Path]:
    roots: list[Path] = []
    explicit = env('KICAD_FOOTPRINT_DIR')
    if explicit:
        roots.append(Path(explicit))
    extra = env('KICAD_EXTRA_FOOTPRINT_DIR')
    if extra:
        roots.extend(Path(item) for item in extra.split(';') if item.strip())
    repo_fp = REPO_ROOT / 'resources' / 'kicad' / 'footprints'
    if repo_fp.exists():
        roots.append(repo_fp)
    source_project = env('KICAD_SOURCE_PROJECT_DIR', '')
    if source_project:
        source_fp = Path(source_project) / 'libraries' / 'footprints'
        if source_fp.exists():
            roots.append(source_fp)
    # Check project-local libs directory (for EasyEDA imported footprints)
    output_root = env('KICAD_OUTPUT_DIR', '')
    if output_root:
        project_libs = Path(output_root) / 'libs'
        if project_libs.exists():
            roots.append(project_libs)
        try:
            for project_dir in Path(output_root).iterdir():
                candidate = project_dir / 'libraries' / 'footprints'
                if candidate.exists():
                    roots.append(candidate)
        except OSError:
            pass
    output_project = env('KICAD_OUTPUT_PROJECT_DIR', '')
    if output_project:
        parent_libs = Path(output_project).parent / 'libs'
        if parent_libs.exists():
            roots.append(parent_libs)
        project_fp = Path(output_project) / 'libraries' / 'footprints'
        if project_fp.exists():
            roots.append(project_fp)
    for base in (Path('D:/Program Files/KiCad'), Path('C:/Program Files/KiCad')):
        if base.exists():
            roots.extend(path / 'share' / 'kicad' / 'footprints' for path in sorted(base.glob('*'), reverse=True))
    return roots


def footprint_exists(footprint: str) -> bool | None:
    footprint = footprint.strip()
    if not footprint:
        return False
    if footprint in FOOTPRINT_EXISTS_CACHE:
        return FOOTPRINT_EXISTS_CACHE[footprint]
    if ':' not in footprint:
        FOOTPRINT_EXISTS_CACHE[footprint] = False
        return False
    library, footprint_name = footprint.split(':', 1)
    roots = kicad_footprint_roots()
    if not roots:
        return None
    for root in roots:
        if (root / f'{library}.pretty' / f'{footprint_name}.kicad_mod').exists():
            FOOTPRINT_EXISTS_CACHE[footprint] = True
            return True
    FOOTPRINT_EXISTS_CACHE[footprint] = False
    return False


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
    from .schematic_layout_rules import build_default_layout_rules, _resolve_wiring_block
    topology = env('KICAD_TOPOLOGY', '')
    return _resolve_wiring_block(role, build_default_layout_rules(topology).block_layout)


def _legacy_estimate_symbol_size(lib_id: str) -> tuple[float, float]:
    """Estimate symbol size in mm including label stubs on each side.

    Returns (width, height) where width covers pin tips + labels on left/right,
    and height covers pin tips + labels on top/bottom.
    """
    from .kicad_project_writer import parse_symbol_pin_map
    pins = parse_symbol_pin_map(lib_id)
    if not pins:
        return 12.7, 10.16
    xs = [p['x'] for p in pins.values()]
    ys = [p['y'] for p in pins.values()]
    if not xs:
        return 12.7, 10.16

    # Label extends from pin tip outward by pin_len + stub ≈ 6.35mm,
    # plus ~5mm for typical label text.  Total ~12mm per side with labels.
    _LABEL_EXTENSION = 12.0  # mm beyond pin tip for label + stub
    _BODY_PAD = 3.81  # mm padding for symbol body edge

    # Determine which sides have labels (based on pin exit direction)
    has_left_labels = any(p['rotation'] == 0 for p in pins.values())
    has_right_labels = any(p['rotation'] == 180 for p in pins.values())
    has_top_labels = any(p['rotation'] == 270 for p in pins.values())
    has_bottom_labels = any(p['rotation'] == 90 for p in pins.values())

    left_margin = _LABEL_EXTENSION if has_left_labels else _BODY_PAD
    right_margin = _LABEL_EXTENSION if has_right_labels else _BODY_PAD
    top_margin = _LABEL_EXTENSION if has_top_labels else _BODY_PAD
    bottom_margin = _LABEL_EXTENSION if has_bottom_labels else _BODY_PAD

    w = (max(xs) - min(xs)) + left_margin + right_margin
    h = (max(ys) - min(ys)) + top_margin + bottom_margin
    return max(w, 10.0), max(h, 8.0)


def _estimate_symbol_size_from_pins(lib_id: str) -> tuple[float, float] | None:
    from .kicad_project_writer import parse_symbol_pin_map
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


def configured_block_order() -> list[str]:
    topology = env('KICAD_TOPOLOGY', '')
    if topology:
        from .schematic_layout_rules import build_default_layout_rules
        order = build_default_layout_rules(topology).block_layout.block_order
        if order:
            return [str(item) for item in order if str(item)]
    order = layout_defaults().get('block_order', [])
    if isinstance(order, list):
        return [str(item) for item in order if str(item)]
    return ['input', 'power', 'reset', 'mcu', 'memory', 'crystal', 'boot', 'io', 'indicator']


def configured_role_rotation(role: str) -> float:
    rotations = layout_defaults().get('role_rotations', {})
    if not isinstance(rotations, dict):
        return 0.0
    try:
        return float(rotations.get(role, 0.0))
    except (TypeError, ValueError):
        return 0.0

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
    from .kicad_project_writer import installed_symbol_block, kicad_symbol_roots

    checked: set[str] = set()
    missing_libs: dict[str, list[str]] = {}  # library → [refs]

    for ref, _role, lib_id, _footprint, _notes in preflight:
        if lib_id in checked:
            continue
        if ':' not in lib_id:
            continue
        library, symbol_name = lib_id.split(':', 1)
        # Only check JLC-MCP libraries — KiCad built-in libs use 'extends'
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
