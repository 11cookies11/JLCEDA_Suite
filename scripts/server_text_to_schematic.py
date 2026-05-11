#!/usr/bin/env python3
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schematic_layout_rules import compile_layout_context
from env_utils import env, parse_json_env, is_truthy_env, to_int_env, normalize_text, to_float, normalize_number, normalize_bool, get_schematic_layout_config

REQ_SCHEMA_VERSION = 'requirement-spec.v1'
MODEL_SCHEMA_VERSION = 'circuit-model.v1'
NETLIST_SCHEMA_VERSION = 'netlist.v1'
SPICE_NETLIST_SCHEMA_VERSION = 'spice-netlist.v1'
NGSPICE_EXECUTION_SCHEMA_VERSION = 'ngspice-execution.v1'
NGSPICE_FEEDBACK_SCHEMA_VERSION = 'ngspice-feedback.v1'
PLAN_SCHEMA_VERSION = 'execution-plan.v1'
SCD_SCHEMA_VERSION = 'schematic-construction-description.v1'

ERROR_PART_UNAVAILABLE = 'PART_UNAVAILABLE'
ERROR_PIN_MISSING = 'PIN_MISSING'
ERROR_WIRE_FAILED = 'WIRE_FAILED'
ERROR_EXECUTION_FAILED = 'EXECUTION_FAILED'

TWO_PIN_VIRTUAL_PIN_ROLES = {
    'current_limit_resistor',
    'feedback_resistor_top',
    'feedback_resistor_bottom',
    'input_capacitor',
    'output_capacitor',
    'inductor',
    'indicator',
}

TWO_PIN_VIRTUAL_PIN_ALIASES = {
    'indicator': ('A', 'K'),
}

TWO_PIN_VIRTUAL_PIN_SIDES = {
    'current_limit_resistor': ('right', 'left'),
    'indicator': ('left', 'right'),
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Path, fallback: Any) -> Any:
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def save_json_file(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except Exception:
        pass


def parse_source_record(line: str) -> dict[str, dict[str, Any]] | None:
    index = line.find('||')
    if index < 0:
        return None
    header_text = line[:index]
    body_text = line[index + 2:]
    if body_text.endswith('|'):
        body_text = body_text[:-1]
    try:
        return {
            'header': json.loads(header_text),
            'body': json.loads(body_text),
        }
    except Exception:
        return None


def transform_point(point: dict[str, float], placement: dict[str, Any]) -> dict[str, float]:
    mirrored = {'x': -point['x'], 'y': point['y']} if normalize_bool(placement.get('mirror')) else point
    rotation = int(placement.get('rotation', 0)) % 360
    if rotation == 90:
        return {'x': float(placement['x']) - mirrored['y'], 'y': float(placement['y']) + mirrored['x']}
    if rotation == 180:
        return {'x': float(placement['x']) - mirrored['x'], 'y': float(placement['y']) - mirrored['y']}
    if rotation == 270:
        return {'x': float(placement['x']) + mirrored['y'], 'y': float(placement['y']) - mirrored['x']}
    return {'x': float(placement['x']) + mirrored['x'], 'y': float(placement['y']) + mirrored['y']}


def parse_symbol_pins_from_base64(base64_payload: str) -> list[dict[str, Any]]:
    if not base64_payload:
        return []
    try:
        raw = base64.b64decode(base64_payload)
    except Exception:
        return []
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw), 'r')
    except Exception:
        return []

    best_text: str | None = None
    best_pin_count = -1
    for info in archive.infolist():
        if info.is_dir():
            continue
        try:
            text = archive.read(info).decode('utf-8', errors='replace')
        except Exception:
            continue
        pin_count = 0
        for line in text.splitlines():
            record = parse_source_record(line.strip())
            if not record:
                continue
            header_type = str(record['header'].get('type', ''))
            body = record['body']
            if header_type == 'PIN':
                pin_count += 1
                continue
            if body.get('pinNumber') is not None or body.get('pinNo') is not None or body.get('number') is not None:
                pin_count += 1
        if pin_count > best_pin_count or (pin_count == best_pin_count and 'DOCHEAD' in text):
            best_pin_count = pin_count
            best_text = text

    if not best_text:
        return []

    return parse_symbol_pins_from_source_text(best_text)


def parse_symbol_pins_from_source_text(source_text: str) -> list[dict[str, Any]]:
    pins: list[dict[str, Any]] = []
    for line in source_text.splitlines():
        record = parse_source_record(line.strip())
        if not record:
            continue
        header_type = str(record['header'].get('type', ''))
        body = record['body']
        pin_number = body.get('pinNumber') if isinstance(body.get('pinNumber'), str) else body.get('pinNo') if isinstance(body.get('pinNo'), str) else body.get('number') if isinstance(body.get('number'), str) else None
        pin_name = body.get('pinName') if isinstance(body.get('pinName'), str) else body.get('name') if isinstance(body.get('name'), str) else None
        if header_type != 'PIN' and pin_number is None and pin_name is None:
            continue
        x = normalize_number(body.get('x')) or normalize_number(body.get('centerX')) or 0.0
        y = normalize_number(body.get('y')) or normalize_number(body.get('centerY')) or 0.0
        pins.append(
            {
                'pinNumber': pin_number or str(len(pins) + 1),
                'pinName': pin_name or '',
                'x': x,
                'y': y,
                'rotation': normalize_number(body.get('rotation')) or 0.0,
                'pinLength': normalize_number(body.get('pinLength')) or normalize_number(body.get('length')) or 0.0,
            }
        )
    return pins


def parse_device_symbol_uuid_from_base64(base64_payload: str) -> str:
    if not base64_payload:
        return ''
    try:
        raw = base64.b64decode(base64_payload)
        archive = zipfile.ZipFile(io.BytesIO(raw), 'r')
    except Exception:
        return ''

    def find_symbol_uuid(value: Any) -> str:
        if isinstance(value, dict):
            direct = value.get('Symbol') or value.get('symbol') or value.get('symbolUuid') or value.get('symbol_uuid')
            if isinstance(direct, str) and direct.strip():
                return direct.strip()
            for nested in value.values():
                found = find_symbol_uuid(nested)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = find_symbol_uuid(nested)
                if found:
                    return found
        return ''

    for info in archive.infolist():
        if info.is_dir():
            continue
        try:
            text = archive.read(info).decode('utf-8', errors='replace')
            payload = json.loads(text)
        except Exception:
            continue
        found = find_symbol_uuid(payload)
        if found:
            return found
    return ''


def resolve_pin_endpoint_local(pin: dict[str, Any]) -> dict[str, float]:
    x = float(pin.get('x', 0.0))
    y = float(pin.get('y', 0.0))
    length = float(pin.get('pinLength', 0.0) or 0.0)
    rotation = int(float(pin.get('rotation', 0.0)) or 0.0) % 360
    endpoint_mode = normalize_text(env('BRIDGE_PIN_ENDPOINT_MODE', 'origin')) or 'origin'
    if endpoint_mode == 'origin' or length <= 0:
        return {'x': x, 'y': y}
    if rotation == 90:
        return {'x': x, 'y': y + length}
    if rotation == 180:
        return {'x': x - length, 'y': y}
    if rotation == 270:
        return {'x': x, 'y': y - length}
    return {'x': x + length, 'y': y}


def _points_equal(a: dict[str, float], b: dict[str, float]) -> bool:
    return abs(float(a['x']) - float(b['x'])) < 0.01 and abs(float(a['y']) - float(b['y'])) < 0.01


def build_wire_points_with_pin_stubs(source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, float]]:
    src_origin = source.get('origin')
    tgt_origin = target.get('origin')
    src_attach = {'x': float(source['x']), 'y': float(source['y'])}
    tgt_attach = {'x': float(target['x']), 'y': float(target['y'])}
    points: list[dict[str, float]] = []
    if isinstance(src_origin, dict) and not _points_equal(src_origin, src_attach):
        points.append({'x': float(src_origin['x']), 'y': float(src_origin['y'])})
    points.append(src_attach)
    manhattan = build_manhattan_wire_points(src_attach, tgt_attach)
    if points and manhattan and _points_equal(points[-1], manhattan[0]):
        points.extend(manhattan[1:])
    else:
        points.extend(manhattan)
    if isinstance(tgt_origin, dict) and not _points_equal(tgt_origin, tgt_attach):
        points.append({'x': float(tgt_origin['x']), 'y': float(tgt_origin['y'])})
    # collapse duplicates
    deduped: list[dict[str, float]] = []
    for point in points:
        if not deduped or not _points_equal(deduped[-1], point):
            deduped.append(point)
    return deduped


def is_two_pin_virtual_role(role: str) -> bool:
    normalized_role = normalize_text(role)
    return normalized_role in TWO_PIN_VIRTUAL_PIN_ROLES or any(
        token in normalized_role
        for token in ('resistor', 'capacitor', 'inductor', 'led', 'diode')
    )


def build_virtual_two_pin_geometry(role: str, placement: dict[str, Any]) -> list[dict[str, Any]]:
    """Return conservative absolute pin anchors for simple two-terminal parts.

    This fallback is intentionally limited to passives/indicators. Complex ICs
    still require verified symbol pin geometry so the planner does not invent
    unsafe pin mappings.
    """
    normalized_role = normalize_text(role)
    if not is_two_pin_virtual_role(normalized_role):
        return []

    half_span = to_float(env('BRIDGE_TWO_PIN_VIRTUAL_HALF_SPAN', '60'), 60.0)
    center_x = float(placement.get('x', 0.0))
    center_y = float(placement.get('y', 0.0))
    pin_names = TWO_PIN_VIRTUAL_PIN_ALIASES.get(normalized_role, ('1', '2'))
    sides = TWO_PIN_VIRTUAL_PIN_SIDES.get(normalized_role, ('left', 'right'))

    def x_for_side(side: str) -> float:
        return center_x - half_span if side == 'left' else center_x + half_span

    first_x = x_for_side(sides[0])
    second_x = x_for_side(sides[1])
    return [
        {
            'pinNumber': '1',
            'pinName': pin_names[0],
            'x': first_x,
            'y': center_y,
            'origin': {'x': first_x, 'y': center_y},
            'virtual': True,
        },
        {
            'pinNumber': '2',
            'pinName': pin_names[1],
            'x': second_x,
            'y': center_y,
            'origin': {'x': second_x, 'y': center_y},
            'virtual': True,
        },
    ]


def adjust_schematic_wire_command_point(point: dict[str, Any]) -> dict[str, float]:
    return {
        'x': float(point.get('x', 0.0)) + to_float(env('BRIDGE_SCHEMATIC_WIRE_PIN_OFFSET_X', '-2'), -2.0),
        'y': float(point.get('y', 0.0)) + to_float(env('BRIDGE_SCHEMATIC_WIRE_PIN_OFFSET_Y', '-2'), -2.0),
    }


def enrich_candidate_pin_geometry(
    client: 'BridgeControlClient',
    client_id: str,
    candidate: PartCandidate,
    cache: dict[str, int],
    request_id_prefix: str,
    stats: dict[str, int] | None = None,
) -> PartCandidate:
    if not candidate.library_uuid or not candidate.symbol_uuid:
        return candidate
    cache_key = f'{candidate.library_uuid}:{candidate.symbol_uuid}'
    if cache_key in cache:
        cached_value = cache.get(cache_key)
        if isinstance(cached_value, dict):
            candidate.pin_count = int(cached_value.get('pinCount', 0) or 0)
            candidate.named_pin_count = int(cached_value.get('namedPinCount', 0) or 0)
            cached_symbol_uuid = cached_value.get('symbolUuid')
            if isinstance(cached_symbol_uuid, str) and cached_symbol_uuid:
                candidate.symbol_uuid = cached_symbol_uuid
        else:
            try:
                candidate.pin_count = int(cached_value or 0)
            except (TypeError, ValueError):
                candidate.pin_count = 0
        return candidate
    resolved_symbol_uuid = candidate.symbol_uuid
    try:
        base64_payload = fetch_symbol_file_base64(
            client=client,
            client_id=client_id,
            symbol_uuid=candidate.symbol_uuid,
            library_uuid=candidate.library_uuid,
            request_id=f'{request_id_prefix}-{candidate.symbol_uuid[:8]}',
        )
        pins = parse_symbol_pins_from_base64(base64_payload)
        if stats is not None:
            stats['symbolFileAttempt'] = stats.get('symbolFileAttempt', 0) + 1
            if pins:
                stats['symbolFileSuccess'] = stats.get('symbolFileSuccess', 0) + 1
        if not pins:
            device_uuid = candidate.place_uuid or candidate.part_id
            device_base64 = fetch_device_file_base64(
                client=client,
                client_id=client_id,
                device_uuid=device_uuid,
                request_id=f'{request_id_prefix}-device-{device_uuid[:8]}',
            )
            symbol_uuid = parse_device_symbol_uuid_from_base64(device_base64)
            if symbol_uuid and symbol_uuid != candidate.symbol_uuid:
                resolved_symbol_uuid = symbol_uuid
                base64_payload = fetch_symbol_file_base64(
                    client=client,
                    client_id=client_id,
                    symbol_uuid=symbol_uuid,
                    library_uuid=candidate.library_uuid,
                    request_id=f'{request_id_prefix}-symbol-{symbol_uuid[:8]}',
                )
                pins = parse_symbol_pins_from_base64(base64_payload)
                if stats is not None:
                    stats['deviceSymbolResolveSuccess'] = stats.get('deviceSymbolResolveSuccess', 0) + 1
                    if pins:
                        stats['deviceSymbolPinSuccess'] = stats.get('deviceSymbolPinSuccess', 0) + 1
    except Exception:  # noqa: BLE001
        pins = []
        if stats is not None:
            stats['symbolFileError'] = stats.get('symbolFileError', 0) + 1

    max_open_doc_attempts = to_int_env('BRIDGE_OPEN_DOC_MAX_ATTEMPTS', 8)
    current_open_doc_attempts = 0 if stats is None else stats.get('openDocAttempt', 0)
    allow_open_doc = current_open_doc_attempts < max_open_doc_attempts

    if not pins and allow_open_doc and is_truthy_env('BRIDGE_PIN_SOURCE_FALLBACK_OPEN_DOC', 'true'):
        try:
            source_text = fetch_symbol_source_by_open_document(
                client=client,
                client_id=client_id,
                symbol_uuid=resolved_symbol_uuid,
                library_uuid=candidate.library_uuid,
                request_id=f'{request_id_prefix}-src-{resolved_symbol_uuid[:8]}',
            )
            pins = parse_symbol_pins_from_source_text(source_text)
            if stats is not None:
                stats['openDocAttempt'] = stats.get('openDocAttempt', 0) + 1
                if pins:
                    stats['openDocSuccess'] = stats.get('openDocSuccess', 0) + 1
        except Exception:  # noqa: BLE001
            if stats is not None:
                stats['openDocError'] = stats.get('openDocError', 0) + 1

    pin_count = len(pins)
    named_pin_count = sum(1 for pin in pins if str(pin.get('pinName', '') or '').strip())
    bbox: dict[str, float] = {}
    if pins:
        xs = [float(p.get('x', 0) or 0) for p in pins]
        ys = [float(p.get('y', 0) or 0) for p in pins]
        if xs and ys:
            padding = 10.0  # small margin around pin cluster
            min_x = min(xs) - padding
            max_x = max(xs) + padding
            min_y = min(ys) - padding
            max_y = max(ys) + padding
            bbox = {
                'minX': min_x,
                'maxX': max_x,
                'minY': min_y,
                'maxY': max_y,
                'width': max(20.0, max_x - min_x),
                'height': max(20.0, max_y - min_y),
            }
    if pins:
        candidate.symbol_uuid = resolved_symbol_uuid
    cache[cache_key] = {'pinCount': pin_count, 'namedPinCount': named_pin_count, 'symbolUuid': candidate.symbol_uuid, **bbox}
    candidate.pin_count = pin_count
    candidate.named_pin_count = named_pin_count
    return candidate


def build_symbol_dimensions_from_components(
    components: list[CircuitComponent],
    cache_dir: str | None = None,
) -> dict[str, dict[str, float]]:
    """Return {ref: {width, height}} for each component using cached symbol pin data.

    Reads the auto-search pin cache (populated by enrich_candidate_pin_geometry).
    Falls back to pin_count heuristic stored on the component when the cache
    entry doesn't include bounding-box coordinates.
    """
    cache_root = Path(cache_dir or env('BRIDGE_CACHE_DIR', '.where/cache'))
    cache_path = cache_root / 'auto-search-cache-v2.json'
    cache_payload = load_json_file(cache_path, {})
    if not isinstance(cache_payload, dict):
        cache_payload = {}

    dimensions: dict[str, dict[str, float]] = {}
    for component in components:
        ref = component.ref
        selected = component.selected_part
        cache_key = f'{selected.library_uuid}:{selected.symbol_uuid}'
        cached_entry = cache_payload.get(cache_key)
        if isinstance(cached_entry, dict):
            w = float(cached_entry.get('width', 0) or 0)
            h = float(cached_entry.get('height', 0) or 0)
            if w > 0 and h > 0:
                dimensions[ref] = {'width': w, 'height': h}
    return dimensions


@dataclass
class ElectricalTargets:
    vin_min_v: float
    vin_max_v: float
    vout_target_v: float
    iout_max_a: float
    ripple_limit_mv: float = 50.0
    efficiency_target_percent: float = 85.0
    switching_frequency_hz: float = 500000.0


@dataclass
class RequirementSpec:
    schema_version: str
    request_id: str
    project_id: str
    goal: str
    electrical_targets: ElectricalTargets
    constraints: dict[str, Any] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


@dataclass
class PartCandidate:
    part_id: str
    display_name: str
    lcsc_id: str = ''
    manufacturer: str = ''
    mpn: str = ''
    package: str = ''
    library_uuid: str = ''
    place_uuid: str = ''
    symbol_uuid: str = ''
    pin_count: int = 0
    named_pin_count: int = 0
    availability_status: str = 'unknown'


@dataclass
class CircuitComponent:
    ref: str
    role: str
    value: str
    selected_part: PartCandidate
    candidate_parts: list[PartCandidate]
    availability_status: str
    notes: list[str] = field(default_factory=list)


@dataclass
class CircuitNet:
    name: str
    members: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class CircuitCalculation:
    name: str
    formula: str
    inputs: dict[str, float]
    result: float
    unit: str


@dataclass
class DesignDecision:
    title: str
    rationale: str
    impact: str = ''


@dataclass
class CircuitModel:
    schema_version: str
    request_id: str
    project_id: str
    topology: str
    components: list[CircuitComponent]
    nets: list[CircuitNet]
    calculations: list[CircuitCalculation]
    design_decisions: list[DesignDecision]
    risks: list[str]


@dataclass
class NetlistPart:
    part_id: str
    display_name: str
    library_uuid: str = ''
    symbol_uuid: str = ''
    pin_count: int = 0
    named_pin_count: int = 0


@dataclass
class NetlistPin:
    pin: str
    net: str
    pin_name: str = ''


@dataclass
class NetlistComponent:
    ref: str
    role: str
    value: str
    part: NetlistPart
    pins: list[NetlistPin]
    availability_status: str = 'unknown'


@dataclass
class NetlistNet:
    name: str
    kind: str
    members: list[str]


@dataclass
class NetlistSourceModel:
    schema_version: str
    request_id: str


@dataclass
class NetlistModel:
    schema_version: str
    request_id: str
    project_id: str
    source_model: NetlistSourceModel
    components: list[NetlistComponent]
    nets: list[NetlistNet]


@dataclass
class SpiceNetlistLine:
    ref: str
    kind: str
    line: str
    supported: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class SpiceNetlistModel:
    schema_version: str
    request_id: str
    source_netlist: str
    lines: list[SpiceNetlistLine]
    node_map: dict[str, str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class NgspiceExecutionModel:
    schema_version: str
    request_id: str
    enabled: bool
    attempted: bool
    executable: str
    command: list[str]
    netlist_path: str
    log_path: str
    returncode: int | None = None
    success: bool = False
    stdout: str = ''
    stderr: str = ''
    log_text: str = ''
    parsed: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ''


@dataclass
class NgspiceFeedbackModel:
    schema_version: str
    request_id: str
    ok: bool
    summary: str
    risk_updates: list[str] = field(default_factory=list)
    requirement_unknowns: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionOperation:
    id: str
    kind: str
    payload: dict[str, Any]
    on_error: str = 'stop'
    notes: list[str] = field(default_factory=list)


@dataclass
class FallbackRule:
    trigger_code: str
    strategy: str
    detail: str = ''


@dataclass
class ExecutionPlan:
    schema_version: str
    request_id: str
    target: dict[str, Any]
    operations: list[ExecutionOperation]
    fallback_rules: list[FallbackRule]


@dataclass
class SCDBlock:
    name: str
    role: str
    scope: str
    statements: list[str]
    notes: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


@dataclass
class SCDDocument:
    schema_version: str
    title: str
    version: str
    purpose: str
    blocks: list[SCDBlock]
    markdown: str


class SCDParseError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        line_no: int | None = None,
        line_text: str = '',
        hint: str = '',
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line_no = line_no
        self.line_text = line_text
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'message': self.message,
            'line_no': self.line_no,
            'line_text': self.line_text,
            'hint': self.hint,
        }


def _scd_error(code: str, message: str, line_no: int | None = None, line_text: str = '', hint: str = '') -> SCDParseError:
    return SCDParseError(code=code, message=message, line_no=line_no, line_text=line_text, hint=hint)


SCD_HEADER_RE = re.compile(r'^# (Title|Version|Purpose):\s*(.+)$')
SCD_BLOCK_RE = re.compile(r'^\[Block: (.+)\]$')
SCD_SECTION_RE = re.compile(r'^\[(Notes|Checks)\]$')
SCD_BULLET_RE = re.compile(r'^-\s+(.+)$')
SCD_STATEMENT_PATTERNS = (
    re.compile(r'^(?P<net>[^\s]+)\s*->\s*(?P<device_pin>[^\s.]+\.[^\s.]+)$'),
    re.compile(r'^(?P<device_pin>[^\s.]+\.[^\s.]+)\s*->\s*(?P<net>[^\s]+)$'),
    re.compile(r'^(?P<net>[^\s]+)\s*->\s*(?P<component>[^\s]+(?:\s+[^\s].*?)?)\s*->\s*GND$'),
    re.compile(r'^(?P<net_a>[^\s]+)\s*->\s*(?P<component>[^\s]+(?:\s+[^\s].*?)?)\s*->\s*(?P<net_b>[^\s]+)$'),
    re.compile(r'^(?P<net>[^\s]+)\s*->\s*(?P<device_pin>[^\s.]+\.[^\s.]+)\s*->\s*(?P<net_out>[^\s]+)$'),
)


def _normalize_scd_statement(text: str) -> str:
    return re.sub(r'\s*->\s*', ' -> ', ' '.join(text.split()))


def _is_scd_statement(text: str) -> bool:
    return any(pattern.match(text) for pattern in SCD_STATEMENT_PATTERNS)


def render_scd_document(document: SCDDocument) -> str:
    lines = [
        f'# Title: {document.title}',
        f'# Version: {document.version}',
        f'# Purpose: {document.purpose}',
        '',
    ]
    for block in document.blocks:
        lines.extend([
            f'[Block: {block.name}]',
            f'- Role: {block.role}',
            f'- Scope: {block.scope}',
            '',
        ])
        lines.extend(block.statements)
        if block.notes:
            lines.append('')
            lines.append('[Notes]')
            lines.extend([f'- {note}' for note in block.notes])
        if block.checks:
            lines.append('')
            lines.append('[Checks]')
            lines.extend([f'- {check}' for check in block.checks])
        lines.append('')
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines) + '\n'


def parse_scd_document(markdown: str) -> dict[str, Any]:
    lines = markdown.splitlines()
    index = 0

    def advance(start: int) -> int:
        current = start
        while current < len(lines) and not lines[current].strip():
            current += 1
        return current

    def fail(code: str, message: str, line_no: int | None = None, hint: str = '') -> SCDParseError:
        line_text = lines[line_no - 1] if line_no and 1 <= line_no <= len(lines) else ''
        return _scd_error(code, message, line_no, line_text, hint)

    index = advance(index)
    header: dict[str, str] = {}
    for expected_key in ('Title', 'Version', 'Purpose'):
        if index >= len(lines):
            raise fail('SCD_HEADER_MISSING', f'Missing header field: {expected_key}', len(lines) or None, 'Add the three-line header at the top of the document.')
        match = SCD_HEADER_RE.match(lines[index].strip())
        if not match or match.group(1) != expected_key:
            raise fail('SCD_HEADER_INVALID', f'Expected header field {expected_key}.', index + 1, 'Use the exact order: Title, Version, Purpose.')
        header[expected_key.lower()] = match.group(2).strip()
        index += 1
        index = advance(index)

    blocks: list[dict[str, Any]] = []
    while index < len(lines):
        current = lines[index].strip()
        if not current:
            index += 1
            continue
        block_match = SCD_BLOCK_RE.match(current)
        if not block_match:
            raise fail('SCD_BLOCK_INVALID', 'Expected a block header.', index + 1, 'Start each block with [Block: <name>].')
        block_name = block_match.group(1).strip()
        index += 1
        index = advance(index)

        if index >= len(lines):
            raise fail('SCD_BLOCK_INCOMPLETE', f'Block {block_name} is incomplete.', len(lines) or None, 'Add Role and Scope lines.')
        role_match = re.match(r'^- Role:\s*(.+)$', lines[index].strip())
        if not role_match:
            raise fail('SCD_ROLE_INVALID', f'Block {block_name} is missing Role.', index + 1, 'Add "- Role: ..." immediately after the block header.')
        role = role_match.group(1).strip()
        index += 1
        index = advance(index)

        if index >= len(lines):
            raise fail('SCD_BLOCK_INCOMPLETE', f'Block {block_name} is incomplete.', len(lines) or None, 'Add a Scope line.')
        scope_match = re.match(r'^- Scope:\s*(.+)$', lines[index].strip())
        if not scope_match:
            raise fail('SCD_SCOPE_INVALID', f'Block {block_name} is missing Scope.', index + 1, 'Add "- Scope: ..." immediately after Role.')
        scope = scope_match.group(1).strip()
        index += 1
        index = advance(index)

        statements: list[str] = []
        notes: list[str] = []
        checks: list[str] = []
        active_section = 'statements'
        seen_notes = False
        seen_checks = False

        while index < len(lines):
            current = lines[index].strip()
            if not current:
                index += 1
                continue
            if SCD_BLOCK_RE.match(current):
                break
            section_match = SCD_SECTION_RE.match(current)
            if section_match:
                active_section = section_match.group(1).lower()
                if active_section == 'notes':
                    if seen_notes:
                        raise fail('SCD_SECTION_DUPLICATE', f'Block {block_name} has duplicate Notes sections.', index + 1, 'Keep only one [Notes] section per block.')
                    seen_notes = True
                else:
                    if seen_checks:
                        raise fail('SCD_SECTION_DUPLICATE', f'Block {block_name} has duplicate Checks sections.', index + 1, 'Keep only one [Checks] section per block.')
                    seen_checks = True
                index += 1
                continue
            bullet_match = SCD_BULLET_RE.match(current)
            if bullet_match:
                if active_section == 'notes':
                    notes.append(bullet_match.group(1).strip())
                elif active_section == 'checks':
                    checks.append(bullet_match.group(1).strip())
                else:
                    raise fail('SCD_BULLET_OUTSIDE_SECTION', 'Bullet items are only allowed in Notes or Checks sections.', index + 1, 'Move bullet lines under [Notes] or [Checks].')
                index += 1
                continue
            normalized = _normalize_scd_statement(current)
            if _is_scd_statement(normalized):
                if active_section != 'statements':
                    raise fail('SCD_STATEMENT_IN_SECTION', 'Connection statements are not allowed inside Notes or Checks.', index + 1, 'Move connection statements above the optional sections.')
                statements.append(normalized)
                index += 1
                continue
            raise fail('SCD_LINE_INVALID', 'Unrecognized line in SCD document.', index + 1, 'Use only block headers, role/scope lines, connection statements, and bullet sections.')

        if not statements:
            raise fail('SCD_BLOCK_EMPTY', f'Block {block_name} does not contain any statements.', index + 1 if index < len(lines) else len(lines) or None, 'Add at least one connection statement.')

        blocks.append(
            {
                'name': block_name,
                'role': role,
                'scope': scope,
                'statements': statements,
                'notes': notes,
                'checks': checks,
            }
        )

    return {
        'schema_version': SCD_SCHEMA_VERSION,
        'title': header['title'],
        'version': header['version'],
        'purpose': header['purpose'],
        'blocks': blocks,
    }


def summarize_scd_document(document: SCDDocument) -> dict[str, Any]:
    return {
        'schema_version': document.schema_version,
        'title': document.title,
        'version': document.version,
        'purpose': document.purpose,
        'blockCount': len(document.blocks),
        'statementCount': sum(len(block.statements) for block in document.blocks),
        'noteCount': sum(len(block.notes) for block in document.blocks),
        'checkCount': sum(len(block.checks) for block in document.blocks),
    }


def ensure_requirement(spec: RequirementSpec) -> None:
    t = spec.electrical_targets
    if spec.schema_version != REQ_SCHEMA_VERSION:
        raise ValueError(f'Unsupported requirement schema_version: {spec.schema_version}')
    if t.vin_min_v <= 0 or t.vin_max_v <= 0 or t.vout_target_v <= 0 or t.iout_max_a <= 0:
        raise ValueError('Electrical targets must be positive values.')
    if t.vin_min_v > t.vin_max_v:
        raise ValueError('vin_min_v must be <= vin_max_v.')
    if t.vout_target_v > t.vin_max_v:
        raise ValueError('vout_target_v should be <= vin_max_v for buck topology.')


def load_part_catalog() -> dict[str, list[PartCandidate]]:
    raw = parse_json_env('BRIDGE_COMPONENT_CATALOG_JSON', {})
    if not isinstance(raw, dict):
        return {}
    catalog: dict[str, list[PartCandidate]] = {}
    for role, entries in raw.items():
        if not isinstance(entries, list):
            continue
        converted: list[PartCandidate] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            converted.append(
                PartCandidate(
                    part_id=str(entry.get('part_id', '') or entry.get('partId', '') or f'{role}-{len(converted)+1}'),
                    display_name=str(entry.get('display_name', '') or entry.get('displayName', '') or role),
                    lcsc_id=str(entry.get('lcsc_id', '') or entry.get('lcscId', '')),
                    manufacturer=str(entry.get('manufacturer', '')),
                    mpn=str(entry.get('mpn', '')),
                    package=str(entry.get('package', '')),
                    library_uuid=str(entry.get('library_uuid', '') or entry.get('libraryUuid', '')),
                    place_uuid=str(entry.get('place_uuid', '') or entry.get('placeUuid', '') or entry.get('uuid', '')),
                    symbol_uuid=str(entry.get('symbol_uuid', '') or entry.get('symbolUuid', '')),
                    pin_count=int(entry.get('pin_count', 0) or entry.get('pinCount', 0) or 0),
                    named_pin_count=int(entry.get('named_pin_count', 0) or entry.get('namedPinCount', 0) or 0),
                    availability_status=str(entry.get('availability_status', '') or entry.get('availabilityStatus', '') or 'unknown'),
                )
            )
        if converted:
            catalog[str(role)] = converted
    return catalog


def build_default_requirement() -> RequirementSpec:
    return RequirementSpec(
        schema_version=REQ_SCHEMA_VERSION,
        request_id=str(uuid.uuid4()),
        project_id='',
        goal='Design a buck power stage from 5V to 3.3V at 2A',
        electrical_targets=ElectricalTargets(
            vin_min_v=5.0,
            vin_max_v=5.5,
            vout_target_v=3.3,
            iout_max_a=2.0,
        ),
        constraints={},
        preferences={'topology': 'buck'},
        acceptance_criteria=[
            'Output voltage in nominal condition is 3.3V ±3%',
            'Current capability reaches 2A',
        ],
        unknowns=[],
    )


def requirement_from_env() -> RequirementSpec:
    payload = parse_json_env('BRIDGE_REQUIREMENT_SPEC_JSON', {})
    if not isinstance(payload, dict) or not payload:
        spec = build_default_requirement()
        return spec

    targets = payload.get('electrical_targets', {})
    if not isinstance(targets, dict):
        targets = {}

    spec = RequirementSpec(
        schema_version=str(payload.get('schema_version', REQ_SCHEMA_VERSION)),
        request_id=str(payload.get('request_id', payload.get('requestId', str(uuid.uuid4())))),
        project_id=str(payload.get('project_id', payload.get('projectId', ''))),
        goal=str(payload.get('goal', '')),
        electrical_targets=ElectricalTargets(
            vin_min_v=to_float(targets.get('vin_min_v', targets.get('vinMinV', 5.0)), 5.0),
            vin_max_v=to_float(targets.get('vin_max_v', targets.get('vinMaxV', 5.5)), 5.5),
            vout_target_v=to_float(targets.get('vout_target_v', targets.get('voutTargetV', 3.3)), 3.3),
            iout_max_a=to_float(targets.get('iout_max_a', targets.get('ioutMaxA', 2.0)), 2.0),
            ripple_limit_mv=to_float(targets.get('ripple_limit_mv', targets.get('rippleLimitMv', 50.0)), 50.0),
            efficiency_target_percent=to_float(targets.get('efficiency_target_percent', targets.get('efficiencyTargetPercent', 85.0)), 85.0),
            switching_frequency_hz=to_float(targets.get('switching_frequency_hz', targets.get('switchingFrequencyHz', 500000.0)), 500000.0),
        ),
        constraints=payload.get('constraints', {}) if isinstance(payload.get('constraints'), dict) else {},
        preferences=payload.get('preferences', {}) if isinstance(payload.get('preferences'), dict) else {},
        acceptance_criteria=[str(item) for item in payload.get('acceptance_criteria', payload.get('acceptanceCriteria', [])) if isinstance(item, str)],
        unknowns=[str(item) for item in payload.get('unknowns', []) if isinstance(item, str)],
    )
    ensure_requirement(spec)
    return spec


def pick_part(role: str, catalog: dict[str, list[PartCandidate]], fallback_name: str) -> tuple[PartCandidate, list[PartCandidate], str]:
    candidates = catalog.get(role, [])
    if not candidates:
        selected = PartCandidate(
            part_id=f'{role}-placeholder',
            display_name=fallback_name,
            availability_status='unknown',
        )
        return selected, [selected], 'unknown'

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            0 if c.availability_status == 'available' else 1,
            0 if c.library_uuid and (c.place_uuid or c.symbol_uuid) else 1,
            0 if c.pin_count > 0 else 1,
        ),
    )
    selected = sorted_candidates[0]
    availability = selected.availability_status if selected.availability_status in ('available', 'unavailable') else 'unknown'
    return selected, sorted_candidates, availability


def synthesize_circuit_model(spec: RequirementSpec, catalog: dict[str, list[PartCandidate]]) -> CircuitModel:
    requested_topology = normalize_text(str(spec.preferences.get('topology', '') or spec.goal))
    if any(token in requested_topology for token in ('led', 'indicator', '指示灯', '发光二极管')):
        return synthesize_led_indicator_model(spec, catalog)

    t = spec.electrical_targets
    delta_i = max(0.3 * t.iout_max_a, 0.4)
    freq = max(t.switching_frequency_hz, 100000.0)
    inductance_h = (t.vout_target_v * (1 - (t.vout_target_v / max(t.vin_max_v, 0.1)))) / (delta_i * freq)
    inductance_uh = max(inductance_h * 1_000_000.0, 1.0)
    rtop = 200000.0
    vref = 0.6
    rbot = rtop / (max(t.vout_target_v, 0.1) / vref - 1)

    u1, u1_candidates, u1_status = pick_part('buck_regulator', catalog, 'Buck Regulator Placeholder')
    l1, l1_candidates, l1_status = pick_part('inductor', catalog, 'Power Inductor Placeholder')
    cin, cin_candidates, cin_status = pick_part('input_capacitor', catalog, 'Input Capacitor Placeholder')
    cout, cout_candidates, cout_status = pick_part('output_capacitor', catalog, 'Output Capacitor Placeholder')
    rfb1, rfb1_candidates, rfb1_status = pick_part('feedback_resistor_top', catalog, 'Feedback Resistor Top Placeholder')
    rfb2, rfb2_candidates, rfb2_status = pick_part('feedback_resistor_bottom', catalog, 'Feedback Resistor Bottom Placeholder')

    components = [
        CircuitComponent('U1', 'buck_regulator', '5V->3.3V buck', u1, u1_candidates, u1_status),
        CircuitComponent('L1', 'inductor', f'{inductance_uh:.2f}uH', l1, l1_candidates, l1_status),
        CircuitComponent('CIN1', 'input_capacitor', '22uF', cin, cin_candidates, cin_status),
        CircuitComponent('COUT1', 'output_capacitor', '22uF', cout, cout_candidates, cout_status),
        CircuitComponent('RFB1', 'feedback_resistor_top', f'{int(rtop)}R', rfb1, rfb1_candidates, rfb1_status),
        CircuitComponent('RFB2', 'feedback_resistor_bottom', f'{int(rbot)}R', rfb2, rfb2_candidates, rfb2_status),
    ]

    nets = [
        CircuitNet('VIN_5V', ['U1.VIN', 'CIN1.1']),
        CircuitNet('GND', ['U1.GND', 'CIN1.2', 'COUT1.2', 'RFB2.2']),
        CircuitNet('SW', ['U1.SW', 'L1.1']),
        CircuitNet('+3V3', ['L1.2', 'COUT1.1', 'RFB1.1']),
        CircuitNet('FB', ['U1.FB', 'RFB1.2', 'RFB2.1']),
    ]

    calculations = [
        CircuitCalculation(
            name='inductance_estimate',
            formula='L = Vout * (1 - Vout/Vin) / (ΔIL * fsw)',
            inputs={'vout_v': t.vout_target_v, 'vin_v': t.vin_max_v, 'delta_il_a': delta_i, 'fsw_hz': freq},
            result=inductance_uh,
            unit='uH',
        ),
        CircuitCalculation(
            name='feedback_ratio_bottom_resistor',
            formula='Rbot = Rtop / (Vout/Vref - 1)',
            inputs={'rtop_ohm': rtop, 'vout_v': t.vout_target_v, 'vref_v': vref},
            result=rbot,
            unit='ohm',
        ),
    ]

    risks: list[str] = []
    for component in components:
        selected = component.selected_part
        place_uuid = selected.place_uuid or selected.symbol_uuid
        if not selected.library_uuid or not place_uuid:
            risks.append(f'{component.ref} lacks library/symbol mapping and cannot be auto-placed yet.')
        if selected.pin_count <= 0:
            risks.append(f'{component.ref} pin geometry is not confirmed.')
        if component.role == 'buck_regulator' and selected.named_pin_count <= 0:
            risks.append(f'{component.ref} pins are unnamed; auto-wiring may be unreliable.')
        if component.availability_status == 'unavailable':
            risks.append(f'{component.ref} selected part is currently marked unavailable.')

    decisions = [
        DesignDecision(
            title='Use buck topology for 5V to 3.3V at 2A',
            rationale='Target load current is high enough that linear regulation would waste excessive power.',
            impact='Improves efficiency and thermal margin.',
        ),
        DesignDecision(
            title='Use explicit fallback candidates per role',
            rationale='Library and availability uncertainty must not block iteration.',
            impact='Supports automatic retry when selected part fails.',
        ),
    ]

    return CircuitModel(
        schema_version=MODEL_SCHEMA_VERSION,
        request_id=spec.request_id,
        project_id=spec.project_id,
        topology=str(spec.preferences.get('topology', 'buck')),
        components=components,
        nets=nets,
        calculations=calculations,
        design_decisions=decisions,
        risks=risks,
    )


def synthesize_led_indicator_model(spec: RequirementSpec, catalog: dict[str, list[PartCandidate]]) -> CircuitModel:
    supply_v = spec.electrical_targets.vin_min_v or 5.0
    led_forward_v = to_float(spec.constraints.get('led_forward_v', spec.constraints.get('ledForwardV', 2.0)), 2.0)
    led_current_ma = to_float(spec.constraints.get('led_current_ma', spec.constraints.get('ledCurrentMa', 3.0)), 3.0)
    resistor_ohm = max((supply_v - led_forward_v) / max(led_current_ma / 1000.0, 0.001), 100.0)
    preferred_resistor = int(round(resistor_ohm / 100.0) * 100)

    resistor, resistor_candidates, resistor_status = pick_part(
        'current_limit_resistor',
        catalog,
        'Current Limit Resistor Placeholder',
    )
    led, led_candidates, led_status = pick_part('indicator', catalog, 'LED Indicator Placeholder')

    components = [
        CircuitComponent('R1', 'current_limit_resistor', f'{preferred_resistor}R', resistor, resistor_candidates, resistor_status),
        CircuitComponent('LED1', 'indicator', 'red LED', led, led_candidates, led_status),
    ]

    nets = [
        CircuitNet('VCC_5V', ['R1.2'], ['Power entry for the indicator chain.']),
        CircuitNet('LED_A', ['R1.1', 'LED1.1'], ['Series connection between current limit resistor and LED anode.']),
        CircuitNet('GND', ['LED1.2'], ['LED cathode return.']),
    ]

    calculations = [
        CircuitCalculation(
            name='led_current_limit_resistor',
            formula='R = (Vin - Vf) / If',
            inputs={'vin_v': supply_v, 'vf_v': led_forward_v, 'if_a': led_current_ma / 1000.0},
            result=float(preferred_resistor),
            unit='ohm',
        ),
    ]

    risks: list[str] = []
    for component in components:
        selected = component.selected_part
        place_uuid = selected.place_uuid or selected.symbol_uuid
        if not selected.library_uuid or not place_uuid:
            risks.append(f'{component.ref} lacks library/symbol mapping and cannot be auto-placed yet.')
        if selected.pin_count <= 0 and not is_two_pin_virtual_role(component.role):
            risks.append(f'{component.ref} pin geometry is not confirmed.')
        if component.availability_status == 'unavailable':
            risks.append(f'{component.ref} selected part is currently marked unavailable.')

    return CircuitModel(
        schema_version=MODEL_SCHEMA_VERSION,
        request_id=spec.request_id,
        project_id=spec.project_id,
        topology='led_indicator',
        components=components,
        nets=nets,
        calculations=calculations,
        design_decisions=[
            DesignDecision(
                title='Use a series resistor LED indicator',
                rationale='A resistor-limited LED is the smallest complete visual power indicator circuit.',
                impact='Creates a directly buildable two-component schematic block.',
            ),
            DesignDecision(
                title='Allow verified two-terminal fallback geometry',
                rationale='Simple passives and LEDs have two terminals, so the planner can generate conservative endpoints when the library omits pin metadata.',
                impact='Avoids blocking small circuits while still requiring real pin data for complex ICs.',
            ),
        ],
        risks=risks,
    )


def ensure_circuit_model(model: CircuitModel) -> None:
    if model.schema_version != MODEL_SCHEMA_VERSION:
        raise ValueError(f'Unsupported circuit schema_version: {model.schema_version}')
    if not model.components:
        raise ValueError('Circuit model must include at least one component.')
    if not model.nets:
        raise ValueError('Circuit model must include nets.')


def _normalize_net_kind(name: str) -> str:
    net_name = name.strip().upper()
    if net_name in {'GND', 'AGND', 'DGND', 'PGND', 'SGND'}:
        return 'ground'
    if net_name.startswith('+') or any(keyword in net_name for keyword in ('VCC', 'VDD', 'VIN', 'VOUT', 'VREF', 'VBAT', 'VDDA', 'VSUP', 'PWR', 'POWER')):
        return 'power'
    return 'signal'


def _sanitize_spice_node_name(name: str) -> str:
    raw = name.strip()
    if not raw:
        return 'N_UNNAMED'
    if raw.upper() in {'GND', 'AGND', 'DGND', 'PGND', 'SGND'}:
        return '0'
    sanitized = re.sub(r'[^A-Za-z0-9_]', '_', raw.replace('+', 'P_'))
    if not re.match(r'^[A-Za-z_]', sanitized):
        sanitized = f'N_{sanitized}'
    return sanitized


def _netlist_component_kind(component: NetlistComponent) -> str:
    role = component.role.strip().lower()
    value = component.value.strip().lower()
    display_name = component.part.display_name.strip().lower()
    if any(token in role for token in ('capacitor', 'decoupling', 'bypass', 'filter_cap')) or value.endswith('f') or 'cap' in display_name:
        return 'capacitor'
    if any(token in role for token in ('inductor', 'choke', 'coil')) or value.endswith('h') or 'inductor' in display_name:
        return 'inductor'
    if any(token in role for token in ('resistor', 'divider', 'pullup', 'pulldown', 'feedback')) or value.endswith('ohm') or 'resistor' in display_name or 'res' in display_name:
        return 'resistor'
    if any(token in role for token in ('voltage_source', 'source', 'input_source', 'reference')):
        return 'voltage_source'
    return 'unsupported'


def build_spice_netlist_from_netlist(netlist: NetlistModel) -> SpiceNetlistModel:
    node_map: dict[str, str] = {}
    lines: list[SpiceNetlistLine] = []
    warnings: list[str] = []
    source_label = f'{netlist.source_model.schema_version}:{netlist.source_model.request_id}'

    for net in netlist.nets:
        node_map[net.name] = _sanitize_spice_node_name(net.name)

    for component in netlist.components:
        nodes = [node_map.get(pin.net, _sanitize_spice_node_name(pin.net)) for pin in component.pins]
        kind = _netlist_component_kind(component)
        supported = True
        spice_line = ''
        notes: list[str] = []

        if kind in {'resistor', 'capacitor', 'inductor'}:
            if len(nodes) != 2:
                supported = False
                notes.append(f'Expected 2 pins but found {len(nodes)}.')
            else:
                element_prefix = {'resistor': 'R', 'capacitor': 'C', 'inductor': 'L'}[kind]
                value = component.value.strip() or '1'
                spice_line = f'{element_prefix}{component.ref} {nodes[0]} {nodes[1]} {value}'
        elif kind == 'voltage_source':
            if len(nodes) < 2:
                supported = False
                notes.append(f'Expected at least 2 pins but found {len(nodes)}.')
            else:
                value = component.value.strip() or 'DC 0'
                spice_line = f'V{component.ref} {nodes[0]} {nodes[1]} {value}'
        else:
            supported = False
            notes.append(f'Unsupported component role "{component.role}" for SPICE export.')
            notes.append(f'Pins: {", ".join(nodes) or "none"}.')
            if component.value.strip():
                notes.append(f'Value: {component.value.strip()}.')

        if not supported:
            warnings.append(f'{component.ref} was not exported as an active SPICE element.')
            if not spice_line:
                spice_line = f'* {component.ref} unsupported: role={component.role} pins={", ".join(nodes) or "none"} value={component.value.strip() or "n/a"}'

        lines.append(
            SpiceNetlistLine(
                ref=component.ref,
                kind=kind,
                line=spice_line,
                supported=supported,
                notes=notes,
            )
        )

    return SpiceNetlistModel(
        schema_version=SPICE_NETLIST_SCHEMA_VERSION,
        request_id=netlist.request_id,
        source_netlist=source_label,
        lines=lines,
        node_map=node_map,
        warnings=warnings,
    )


def render_spice_netlist(spice_netlist: SpiceNetlistModel) -> str:
    lines = [
        f'* JLCEDA Suite generated SPICE netlist ({spice_netlist.request_id})',
        f'* Source: {spice_netlist.source_netlist}',
        '',
    ]
    for original_name, node_name in sorted(spice_netlist.node_map.items()):
        if original_name != node_name:
            lines.append(f'* node-map: {original_name} -> {node_name}')
    if spice_netlist.node_map:
        lines.append('')
    for line in spice_netlist.lines:
        if line.line:
            lines.append(line.line)
        else:
            lines.append(f'* {line.ref} exported as comment only')
        for note in line.notes:
            lines.append(f'*   note: {note}')
    if spice_netlist.warnings:
        lines.append('')
        for warning in spice_netlist.warnings:
            lines.append(f'* warning: {warning}')
    lines.extend(['', '.op', '.end'])
    return '\n'.join(lines) + '\n'


def parse_ngspice_log(log_text: str) -> dict[str, Any]:
    analysis_kinds: list[str] = []
    warning_lines: list[str] = []
    error_lines: list[str] = []
    measurement_lines: list[str] = []
    scalar_values: dict[str, str] = {}

    analysis_patterns = [
        (re.compile(r'\boperating point\b', re.IGNORECASE), 'op'),
        (re.compile(r'\btransient\b', re.IGNORECASE), 'tran'),
        (re.compile(r'\bac analysis\b', re.IGNORECASE), 'ac'),
        (re.compile(r'\bdc analysis\b', re.IGNORECASE), 'dc'),
        (re.compile(r'\bnoise analysis\b', re.IGNORECASE), 'noise'),
    ]
    scalar_pattern = re.compile(r'^([A-Za-z0-9_.$()+/\-\[\]<>:]+)\s*=\s*(.+?)\s*$')

    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    for line in lines:
        lower = line.lower()
        for pattern, kind in analysis_patterns:
            if pattern.search(line) and kind not in analysis_kinds:
                analysis_kinds.append(kind)
        if lower.startswith('warning'):
            warning_lines.append(line)
        if lower.startswith('error'):
            error_lines.append(line)
        if 'measure' in lower or lower.startswith('measurement'):
            measurement_lines.append(line)
        match = scalar_pattern.match(line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            if len(key) <= 64 and len(value) <= 256:
                scalar_values[key] = value

    return {
        'analysisKinds': analysis_kinds,
        'warnings': warning_lines,
        'errors': error_lines,
        'measurements': measurement_lines,
        'scalarValues': scalar_values,
        'lineCount': len(lines),
    }


def build_ngspice_feedback(
    spec: RequirementSpec,
    model: CircuitModel,
    spice_netlist: SpiceNetlistModel,
    execution: NgspiceExecutionModel,
) -> NgspiceFeedbackModel:
    parsed = execution.parsed if isinstance(execution.parsed, dict) else {}
    analysis_kinds = [str(item) for item in parsed.get('analysisKinds', []) if isinstance(item, str)]
    parsed_warnings = [str(item) for item in parsed.get('warnings', []) if isinstance(item, str)]
    parsed_errors = [str(item) for item in parsed.get('errors', []) if isinstance(item, str)]
    measurement_lines = [str(item) for item in parsed.get('measurements', []) if isinstance(item, str)]
    scalar_values = parsed.get('scalarValues', {}) if isinstance(parsed.get('scalarValues', {}), dict) else {}

    risk_updates: list[str] = []
    recommendations: list[str] = []
    requirement_unknowns: list[str] = []

    if not execution.enabled:
        summary = 'ngspice execution was disabled, so no simulation feedback was produced.'
        recommendations.append('Set BRIDGE_RUN_NGSPICE=true to enable execution feedback.')
    elif not execution.attempted:
        summary = 'ngspice execution was enabled but not attempted.'
        recommendations.append('Verify ngspice is installed or BRIDGE_NGSPICE_BIN is set.')
    elif execution.success:
        summary = 'ngspice execution completed successfully.'
        if analysis_kinds:
            recommendations.append(f'Observed analyses: {", ".join(analysis_kinds)}.')
        if measurement_lines or scalar_values:
            recommendations.append('Capture measurement lines into a regression fixture for later comparison.')
    else:
        summary = 'ngspice execution failed and should be treated as a blocking validation issue.'
        risk_updates.append('ngspice execution failed and must be resolved before accepting the circuit.')
        if execution.error:
            risk_updates.append(f'ngspice execution error: {execution.error}')
        if execution.returncode not in (None, 0):
            risk_updates.append(f'ngspice returned exit code {execution.returncode}.')
        if parsed_errors:
            risk_updates.extend(parsed_errors)
            recommendations.append('Review ngspice errors before regenerating the circuit.')
        if parsed_warnings:
            recommendations.append('Review ngspice warnings before regenerating the circuit.')

    if spice_netlist.warnings:
        risk_updates.extend([f'spice export warning: {warning}' for warning in spice_netlist.warnings])
        recommendations.append('Resolve unsupported SPICE exports or provide richer component models.')

    for component in model.components:
        if component.availability_status != 'available':
            requirement_unknowns.append(f'{component.ref} availability remains {component.availability_status}.')

    if not analysis_kinds:
        recommendations.append('Add a simple .op or .tran regression case to confirm the exporter and executor are wired correctly.')

    if scalar_values:
        recommendations.append(f'Captured {len(scalar_values)} scalar value(s) from ngspice log.')

    evidence = {
        'analysisKinds': analysis_kinds,
        'warnings': parsed_warnings,
        'errors': parsed_errors,
        'measurements': measurement_lines,
        'scalarValues': scalar_values,
        'requestGoal': spec.goal,
    }

    if not requirement_unknowns:
        requirement_unknowns = list(spec.unknowns)

    return NgspiceFeedbackModel(
        schema_version=NGSPICE_FEEDBACK_SCHEMA_VERSION,
        request_id=spec.request_id,
        ok=execution.success,
        summary=summary,
        risk_updates=risk_updates,
        requirement_unknowns=requirement_unknowns,
        recommendations=recommendations,
        evidence=evidence,
    )


def resolve_ngspice_executable() -> str | None:
    explicit = env('BRIDGE_NGSPICE_BIN')
    if explicit:
        return explicit
    located = shutil.which('ngspice')
    if located:
        return located
    if os.name == 'nt':
        located = shutil.which('ngspice.exe')
        if located:
            return located
    return None


def execute_ngspice_netlist(spice_netlist: SpiceNetlistModel) -> NgspiceExecutionModel:
    enabled = is_truthy_env('BRIDGE_RUN_NGSPICE', 'false')
    command: list[str] = []
    executable = resolve_ngspice_executable() or ''
    warnings: list[str] = []
    if not enabled:
        return NgspiceExecutionModel(
            schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
            request_id=spice_netlist.request_id,
            enabled=False,
            attempted=False,
            executable=executable,
            command=command,
            netlist_path='',
            log_path='',
            parsed=parse_ngspice_log(''),
            warnings=['ngspice execution disabled by BRIDGE_RUN_NGSPICE.'],
        )

    if not executable:
        return NgspiceExecutionModel(
            schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
            request_id=spice_netlist.request_id,
            enabled=True,
            attempted=True,
            executable='',
            command=[],
            netlist_path='',
            log_path='',
            parsed=parse_ngspice_log(''),
            warnings=['ngspice executable was not found. Set BRIDGE_NGSPICE_BIN or install ngspice.'],
            error='NGSPICE_NOT_FOUND',
        )

    temp_dir = Path(tempfile.mkdtemp(prefix='jlceda-ngspice-'))
    netlist_path = temp_dir / 'netlist.cir'
    log_path = temp_dir / 'ngspice.log'
    netlist_text = render_spice_netlist(spice_netlist)
    netlist_path.write_text(netlist_text, encoding='utf-8')
    command = [executable, '-b', '-o', str(log_path), str(netlist_path)]
    try:
        try:
            process = subprocess.run(
                command,
                cwd=str(temp_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=to_int_env('BRIDGE_NGSPICE_TIMEOUT_SEC', 60),
                check=False,
            )
            log_text = ''
            if log_path.exists():
                log_text = log_path.read_text(encoding='utf-8', errors='replace')
            elif process.stdout:
                log_text = process.stdout
            parsed = parse_ngspice_log(log_text)
            success = process.returncode == 0
            if not success:
                warnings.append('ngspice returned a non-zero exit status.')
            warnings.extend(parsed['warnings'])
            if not log_text and process.stderr:
                log_text = process.stderr
            return NgspiceExecutionModel(
                schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
                request_id=spice_netlist.request_id,
                enabled=True,
                attempted=True,
                executable=executable,
                command=command,
                netlist_path=str(netlist_path),
                log_path=str(log_path),
                returncode=process.returncode,
                success=success,
                stdout=process.stdout or '',
                stderr=process.stderr or '',
                log_text=log_text,
                parsed=parsed,
                warnings=warnings,
            )
        except subprocess.TimeoutExpired as error:
            return NgspiceExecutionModel(
                schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
                request_id=spice_netlist.request_id,
                enabled=True,
                attempted=True,
                executable=executable,
                command=command,
                netlist_path=str(netlist_path),
                log_path=str(log_path),
                success=False,
                parsed=parse_ngspice_log(''),
                warnings=['ngspice execution timed out.'],
                error=str(error),
            )
        except Exception as error:  # noqa: BLE001
            return NgspiceExecutionModel(
                schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
                request_id=spice_netlist.request_id,
                enabled=True,
                attempted=True,
                executable=executable,
                command=command,
                netlist_path=str(netlist_path),
                log_path=str(log_path),
                success=False,
                parsed=parse_ngspice_log(''),
                warnings=['ngspice execution failed.'],
                error=str(error),
            )
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def build_netlist_from_circuit_model(model: CircuitModel) -> NetlistModel:
    ensure_circuit_model(model)
    pin_map: dict[str, list[tuple[str, str]]] = defaultdict(list)
    netlist_nets: list[NetlistNet] = []

    for net in model.nets:
        members = [str(member).strip() for member in net.members if str(member).strip()]
        for member in members:
            if '.' not in member:
                continue
            ref, pin = member.split('.', 1)
            if ref and pin:
                pin_map[ref].append((pin, net.name))
        netlist_nets.append(
            NetlistNet(
                name=net.name,
                kind=_normalize_net_kind(net.name),
                members=members,
            )
        )

    netlist_components: list[NetlistComponent] = []
    for component in model.components:
        selected_part = component.selected_part
        part = NetlistPart(
            part_id=selected_part.part_id,
            display_name=selected_part.display_name,
            library_uuid=selected_part.library_uuid,
            symbol_uuid=selected_part.symbol_uuid,
            pin_count=selected_part.pin_count,
            named_pin_count=selected_part.named_pin_count,
        )
        pins = [
            NetlistPin(pin=pin, net=net_name)
            for pin, net_name in sorted(pin_map.get(component.ref, []), key=lambda item: item[0])
        ]
        netlist_components.append(
            NetlistComponent(
                ref=component.ref,
                role=component.role,
                value=component.value,
                part=part,
                pins=pins,
                availability_status=component.availability_status,
            )
        )

    return NetlistModel(
        schema_version=NETLIST_SCHEMA_VERSION,
        request_id=model.request_id,
        project_id=model.project_id,
        source_model=NetlistSourceModel(
            schema_version=model.schema_version,
            request_id=model.request_id,
        ),
        components=netlist_components,
        nets=netlist_nets,
    )


def build_scd_document(spec: RequirementSpec, model: CircuitModel) -> SCDDocument:
    component_by_role = {component.role: component for component in model.components}
    component_by_ref = {component.ref: component for component in model.components}

    def describe_component(ref: str) -> str:
        component = component_by_ref.get(ref)
        if not component:
            return ref
        display_name = component.selected_part.display_name.strip() or component.selected_part.part_id.strip()
        if display_name:
            return f'{ref} ({display_name})'
        return ref

    u1 = component_by_role.get('buck_regulator')
    l1 = component_by_role.get('inductor')
    cin1 = component_by_role.get('input_capacitor')
    cout1 = component_by_role.get('output_capacitor')
    rfb1 = component_by_role.get('feedback_resistor_top')
    rfb2 = component_by_role.get('feedback_resistor_bottom')
    current_limit = component_by_role.get('current_limit_resistor')
    indicator = component_by_role.get('indicator')
    if current_limit and indicator:
        vcc_net = next((net.name for net in model.nets if net.name.startswith('VCC') or net.name.startswith('VIN')), 'VCC_5V')
        gnd_net = next((net.name for net in model.nets if net.name == 'GND'), 'GND')
        blocks = [
            SCDBlock(
                name='LED Indicator',
                role='Show that the supply rail is present',
                scope=f'{describe_component(current_limit.ref)}, {describe_component(indicator.ref)}, {vcc_net}, {gnd_net}',
                statements=[
                    f'{vcc_net} -> {current_limit.ref}.1',
                    f'{current_limit.ref}.2 -> {indicator.ref}.1',
                    f'{indicator.ref}.2 -> {gnd_net}',
                ],
                notes=[
                    f'{current_limit.ref} limits LED current.',
                    f'{indicator.ref} is modeled as the visual indicator load.',
                ],
                checks=[
                    f'{current_limit.ref} and {indicator.ref} form a series path.',
                    f'{indicator.ref}.2 returns to {gnd_net}.',
                ],
            ),
        ]
        document = SCDDocument(
            schema_version=SCD_SCHEMA_VERSION,
            title=spec.goal or 'LED Indicator Schematic',
            version='1.0',
            purpose=spec.goal or 'Build a complete two-component LED indicator schematic.',
            blocks=blocks,
            markdown='',
        )
        document.markdown = render_scd_document(document)
        document.summary = summarize_scd_document(document)
        parse_scd_document(document.markdown)
        return document

    if not all([u1, l1, cin1, cout1, rfb1, rfb2]):
        raise ValueError('Circuit model is missing expected power-stage roles for SCD generation.')

    vin_net = next((net.name for net in model.nets if net.name.startswith('VIN') or net.name.endswith('5V')), 'VIN_5V')
    vout_net = next((net.name for net in model.nets if net.name.startswith('+3V3')), '+3V3')
    fb_net = next((net.name for net in model.nets if net.name == 'FB'), 'FB')
    gnd_net = next((net.name for net in model.nets if net.name == 'GND'), 'GND')

    calculation_map = {calculation.name: calculation for calculation in model.calculations}
    inductance = calculation_map.get('inductance_estimate')
    feedback = calculation_map.get('feedback_ratio_bottom_resistor')

    blocks = [
        SCDBlock(
            name='Input Conditioning',
            role='Provide the filtered input rail to the regulator',
            scope=f'{describe_component(cin1.ref)}, {describe_component(u1.ref)}, {vin_net}, {gnd_net}',
            statements=[
                f'{vin_net} -> {cin1.ref} {cin1.value} -> {gnd_net}',
                f'{vin_net} -> {u1.ref}.VIN',
                f'{u1.ref}.GND -> {gnd_net}',
            ],
            notes=[
                f'{u1.ref} selected part: {u1.selected_part.display_name}',
                f'{cin1.ref} acts as the input decoupling capacitor.',
            ],
            checks=[
                f'{cin1.ref} value matches the expected input decoupling.',
                f'{u1.ref}.VIN is tied to the input rail.',
            ],
        ),
        SCDBlock(
            name='Buck Power Stage',
            role='Convert the input rail to the 3.3V output rail',
            scope=f'{describe_component(u1.ref)}, {describe_component(l1.ref)}, {describe_component(cout1.ref)}, {vout_net}',
            statements=[
                f'{u1.ref}.SW -> {l1.ref}.1',
                f'{l1.ref}.2 -> {vout_net}',
                f'{vout_net} -> {cout1.ref} {cout1.value} -> {gnd_net}',
            ],
            notes=[
                f'{l1.ref} value: {l1.value}',
                f'{u1.ref}.SW should stay local to the power stage.',
            ],
            checks=[
                f'{l1.ref} connects between the switching node and {vout_net}.',
                f'{cout1.ref} stabilizes the output rail.',
            ],
        ),
        SCDBlock(
            name='Feedback Network',
            role='Sense the output voltage and close the regulation loop',
            scope=f'{describe_component(rfb1.ref)}, {describe_component(rfb2.ref)}, {u1.ref}.FB, {fb_net}, {vout_net}',
            statements=[
                f'{vout_net} -> {rfb1.ref} {rfb1.value} -> {fb_net}',
                f'{fb_net} -> {rfb2.ref} {rfb2.value} -> {gnd_net}',
                f'{u1.ref}.FB -> {fb_net}',
            ],
            notes=[
                f'{rfb1.ref} and {rfb2.ref} implement the feedback divider.',
                f'{fb_net} should remain short and quiet near {u1.ref}.FB.',
            ],
            checks=[
                f'Feedback divider ratio matches the {vout_net} target.',
                f'{u1.ref}.FB is connected to the divider midpoint.',
            ],
        ),
    ]

    if inductance is not None:
        blocks[1].notes.append(f'Estimated inductance: {inductance.result:.2f} {inductance.unit}.')
    if feedback is not None:
        blocks[2].notes.append(f'Estimated feedback bottom resistor: {feedback.result:.0f} {feedback.unit}.')

    document = SCDDocument(
        schema_version=SCD_SCHEMA_VERSION,
        title=spec.goal or 'Theory Schematic',
        version='v1',
        purpose=spec.goal or 'Convert requirement text into a readable schematic construction description.',
        blocks=blocks,
        markdown='',
    )
    document.markdown = render_scd_document(document)
    parse_scd_document(document.markdown)
    return document


def _component_anchor(index: int, layout: dict[str, int]) -> dict[str, int]:
    col = index % layout['columns']
    row = index // layout['columns']
    return {
        'x': layout['origin_x'] + (col * layout['pitch_x']),
        'y': layout['origin_y'] + (row * layout['pitch_y']),
    }


def compute_rotation_from_neighbors(
    component_ref: str,
    nets: list[CircuitNet],
    placements: dict[str, dict[str, Any]],
) -> int:
    """Return the best rotation (0/90/180/270) so the component faces its neighbours.

    Analyses all nets the component participates in and finds the dominant
    direction toward the other connected components.  Falls back to 0 when
    there are no connected neighbours with known positions.
    """
    dx_total = 0.0
    dy_total = 0.0
    own_pos = placements.get(component_ref)
    if not own_pos:
        return 0

    own_x = float(own_pos.get('x', 0))
    own_y = float(own_pos.get('y', 0))
    peer_contributions = 0

    for net in nets:
        members = [str(m) for m in net.members]
        # Include nets that reference this component at least once.
        if not any(m.startswith(f'{component_ref}.') for m in members):
            continue

        # Gather neighbour refs on the same net (exclude self).
        peer_refs: set[str] = set()
        for member in members:
            ref, _pin = member.split('.', 1) if '.' in member else (member, '')
            if ref and ref != component_ref:
                peer_refs.add(ref)

        for peer_ref in peer_refs:
            peer_pos = placements.get(peer_ref)
            if not peer_pos:
                continue
            dx_total += float(peer_pos.get('x', 0)) - own_x
            dy_total += float(peer_pos.get('y', 0)) - own_y
            peer_contributions += 1

    if peer_contributions == 0:
        return 0

    # Determine dominant quadrant.
    if abs(dx_total) >= abs(dy_total):
        return 0 if dx_total >= 0 else 180
    else:
        return 90 if dy_total >= 0 else 270


def should_use_fixed_two_pin_rotation(component: CircuitComponent, model: CircuitModel) -> bool:
    if normalize_text(model.topology) == 'led_indicator':
        return normalize_text(component.role) in {'current_limit_resistor', 'indicator'}
    return False


# Known roles that should not be overridden by inference.
_PRESET_ROLES = frozenset({
    'input_protection', 'input_capacitor', 'buck_regulator', 'inductor',
    'output_capacitor', 'feedback_resistor_top', 'feedback_resistor_bottom',
    'connector', 'indicator',
})

# Keywords mapping net names to inferred roles.
_NET_ROLE_HINTS: dict[str, str] = {
    'VIN': 'input_capacitor',
    'VCC': 'input_capacitor',
    'VDD': 'input_capacitor',
    'VOUT': 'output_capacitor',
    'OUT': 'output_capacitor',
    'SW': 'inductor',
    'LX': 'inductor',
    'FB': 'feedback_resistor_top',
    'COMP': 'feedback_resistor_bottom',
    'EN': 'input_protection',
    'GND': '',  # too generic, don't infer from GND alone
}


def _infer_component_role(
    component: CircuitComponent,
    nets: list[CircuitNet],
) -> str:
    """Return a role for *component* when its assigned role is missing or generic.

    Uses net-name patterns and component-designator keywords as signals.
    Does NOT override an already-assigned concrete role.
    """
    current_role = (component.role or '').strip()
    if current_role in _PRESET_ROLES:
        return current_role

    # Collect every net the component participates in.
    connected_nets: list[str] = []
    for net in nets:
        members = [str(m) for m in net.members]
        if any(m.startswith(f'{component.ref}.') for m in members):
            connected_nets.append(net.name.upper())

    # ---- component-name hints (strong signals first) ----
    text = ' '.join([
        component.ref or '',
        component.value or '',
        component.selected_part.display_name or '',
        component.selected_part.package or '',
    ]).lower()

    if any(kw in text for kw in ('reg', 'ldo', 'buck', 'boost', 'ams1117', '1117', 'mp', 'tps')):
        return 'buck_regulator'
    if any(kw in text for kw in ('inductor', 'inductance', 'ferrite', 'bead')):
        return 'inductor'
    if any(kw in text for kw in ('conn', 'term', 'header', 'socket', 'pin header')):
        return 'connector'
    if any(kw in text for kw in ('led', 'indicator')):
        return 'indicator'
    if 'current_limit' in text or 'limit resistor' in text:
        return 'current_limit_resistor'

    # ---- net-name hints (for capacitors & passives) ----
    net_role_votes: dict[str, int] = {}
    for net_name in connected_nets:
        role = _NET_ROLE_HINTS.get(net_name, '')
        if role:
            net_role_votes[role] = net_role_votes.get(role, 0) + 1

    if net_role_votes:
        best_role = max(net_role_votes, key=lambda r: net_role_votes[r])
        if net_role_votes[best_role] >= 1:
            return best_role

    if 'cap' in text or 'capacitor' in text:
        for net_name in connected_nets:
            if net_name in ('VCC', 'VIN', 'VDD'):
                return 'input_capacitor'
            if net_name in ('VOUT', 'OUT'):
                return 'output_capacitor'
        return 'input_capacitor'
    if any(kw in text for kw in ('res', 'resistor')) and component.ref.lower().startswith('r'):
        for net_name in connected_nets:
            if net_name == 'FB':
                return 'feedback_resistor_top'

    return current_role or 'io'


def compile_execution_plan(model: CircuitModel, safe_wire_operations: list[ExecutionOperation] | None = None) -> ExecutionPlan:
    ensure_circuit_model(model)
    operations: list[ExecutionOperation] = []
    placeable_refs: set[str] = set()
    layout = get_schematic_layout_config()

    # Enrich components whose role is empty/generic before layout.
    enriched_components: list[dict[str, Any]] = []
    for component in model.components:
        comp_dict = asdict(component)
        comp_dict['role'] = _infer_component_role(component, model.nets)
        enriched_components.append(comp_dict)

    symbol_dims = build_symbol_dimensions_from_components(model.components)
    layout_context = compile_layout_context(
        components=enriched_components,
        nets=[asdict(net) for net in model.nets],
        origin_x=layout['origin_x'],
        origin_y=layout['origin_y'],
        symbol_dimensions=symbol_dims if symbol_dims else None,
    )
    layout_engine = str(layout_context.get('engine', 'rules'))
    component_placements = layout_context.get('componentPlacements', {})
    net_port_placements = layout_context.get('netPortPlacements', [])

    # Pre-compute rotations from neighbour directions (replaces uniform rotation=0).
    rotations: dict[str, int] = {}
    for component in model.components:
        rotations[component.ref] = 0 if should_use_fixed_two_pin_rotation(component, model) else compute_rotation_from_neighbors(
            component.ref, model.nets, component_placements,
        )

    for idx, component in enumerate(model.components):
        selected = component.selected_part
        place_uuid = selected.place_uuid or selected.symbol_uuid
        if not selected.library_uuid or not place_uuid:
            continue
        anchor_data = component_placements.get(component.ref, {})
        fallback_anchor = _component_anchor(idx, layout)
        anchor = {
            'x': int(anchor_data.get('x', fallback_anchor['x'])),
            'y': int(anchor_data.get('y', fallback_anchor['y'])),
        }
        operations.append(
            ExecutionOperation(
                id=f'op-place-{component.ref.lower()}',
                kind='place_component',
                payload={
                    'libraryUuid': selected.library_uuid,
                    'uuid': place_uuid,
                    'position': anchor,
                    'rotation': rotations.get(component.ref, 0),
                    'mirror': False,
                    'addIntoBom': True,
                    'addIntoPcb': True,
                },
                on_error='stop',
                notes=[
                    f'Place {component.ref} ({component.role}) rot={rotations.get(component.ref, 0)}',
                    f'Rule block={anchor_data.get("block", "unknown")} slot={anchor_data.get("slot", -1)}',
                    f'Layout engine={layout_engine}',
                ],
            )
        )
        placeable_refs.add(component.ref)

    safe_wire_operations = safe_wire_operations or []
    if safe_wire_operations:
        operations.extend(safe_wire_operations)

    safe_wiring_handles_terminals = bool(safe_wire_operations) and normalize_text(model.topology) == 'led_indicator'
    for placement in ([] if safe_wiring_handles_terminals else net_port_placements):
        if not isinstance(placement, dict):
            continue
        net_name = str(placement.get('netName', '') or '')
        if not net_name:
            continue
        operations.append(
            ExecutionOperation(
                id=f'op-label-{net_name.lower().replace("+", "p")}',
                kind='create_net_port',
                payload={
                    'direction': 'BI',
                    'net': net_name,
                    'position': {
                        'x': int(placement.get('x', layout['origin_x'] + layout['label_x_offset'])),
                        'y': int(placement.get('y', layout['origin_y'] + layout['label_y_start_offset'])),
                    },
                },
                on_error='continue',
                notes=[
                    'Net port is used as a robust fallback when exact wire endpoints are unavailable.',
                    f'Rule class={placement.get("netClass", "signal")} anchor={placement.get("anchorRef", "")}.{placement.get("anchorPin", "")}',
                ],
            )
        )
        if net_name in ('GND', '+3V3'):
            flag_kind = 'Ground' if net_name == 'GND' else 'Power'
            operations.append(
                ExecutionOperation(
                    id=f'op-flag-{net_name.lower().replace("+", "p")}',
                    kind='create_net_flag',
                    payload={
                        'identification': flag_kind,
                        'net': net_name,
                        'position': {
                            'x': int(placement.get('x', layout['origin_x'])) + 80,
                            'y': int(placement.get('y', layout['origin_y'])),
                        },
                    },
                    on_error='continue',
                )
            )

    operations.append(
        ExecutionOperation(
            id='op-check-connectivity',
            kind='inspect_connectivity',
            payload={
                'allSchematicPages': False,
                'tolerance': 2,
                'maxIssues': 200,
            },
            on_error='continue',
        )
    )
    operations.append(
        ExecutionOperation(
            id='op-check-drc',
            kind='check_drc',
            payload={
                'strict': True,
                'userInterface': False,
                'includeVerboseError': True,
            },
            on_error='continue',
        )
    )
    operations.append(
        ExecutionOperation(
            id='op-save',
            kind='save',
            payload={},
            on_error='continue',
        )
    )

    fallback_rules = [
        FallbackRule(
            trigger_code=ERROR_PART_UNAVAILABLE,
            strategy='replace_with_backup_candidate_and_recompile',
            detail='Choose the next candidate for the same role and regenerate plan.',
        ),
        FallbackRule(
            trigger_code=ERROR_PIN_MISSING,
            strategy='stop_and_request_pin_verified_symbol',
            detail='Do not continue auto-wiring without pin geometry.',
        ),
        FallbackRule(
            trigger_code=ERROR_WIRE_FAILED,
            strategy='retry_with_labels_then_manual_review',
            detail='Keep net labels and ask for user confirmation of final wiring.',
        ),
    ]

    if not placeable_refs:
        fallback_rules.append(
            FallbackRule(
                trigger_code=ERROR_PART_UNAVAILABLE,
                strategy='stop_without_execution',
                detail='No components had executable library/symbol mapping.',
            )
        )

    return ExecutionPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        request_id=model.request_id,
        target={'mode': 'active_document'},
        operations=operations,
        fallback_rules=fallback_rules,
    )


class BridgeControlClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.get_timeout_sec = to_float(env('BRIDGE_HTTP_GET_TIMEOUT_SEC', '15'), 15.0)
        self.post_timeout_sec = to_float(env('BRIDGE_HTTP_POST_TIMEOUT_SEC', '20'), 20.0)

    def _headers(self) -> dict[str, str]:
        headers = {'content-type': 'application/json'}
        if self.token:
            headers['x-bridge-control-token'] = self.token
        return headers

    def get_json(self, path: str) -> Any:
        req = urllib.request.Request(
            f'{self.base_url}{path}',
            headers=self._headers(),
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=self.get_timeout_sec) as response:
            return json.loads(response.read().decode('utf-8'))

    def post_json(self, path: str, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f'{self.base_url}{path}',
            data=data,
            headers=self._headers(),
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=self.post_timeout_sec) as response:
            return json.loads(response.read().decode('utf-8'))

    def bridge_request(self, client_id: str, domain: str, action: str, payload: dict[str, Any], request_id: str) -> dict[str, Any]:
        response = self.post_json(
            '/request',
            {
                'clientId': client_id,
                'request': {
                    'id': request_id,
                    'type': 'command.request',
                    'protocolVersion': '0.1.0',
                    'sessionId': 'server-text-to-schematic',
                    'command': {
                        'domain': domain,
                        'action': action,
                        'requiresConfirmation': False,
                        'payload': payload,
                    },
                },
            },
        )
        return response.get('response', {})

    def api_invoke(self, client_id: str, path: str, args: list[Any], request_id: str) -> tuple[bool, Any]:
        bridge = self.bridge_request(
            client_id=client_id,
            domain='system',
            action='api_invoke',
            payload={
                'path': path,
                'args': args,
            },
            request_id=request_id,
        )
        if bridge.get('status') != 'success':
            return False, bridge
        result = (
            bridge.get('result', {})
            .get('data', {})
            .get('result')
        )
        return True, result


ROLE_SEARCH_KEYWORDS: dict[str, list[str]] = {
    'buck_regulator': ['buck', '降压', '3.3V', '2A'],
    'inductor': ['inductor', '电感', '4.7uH'],
    'input_capacitor': ['capacitor', '电容', '22uF', '25V'],
    'output_capacitor': ['capacitor', '电容', '22uF', '10V'],
    'feedback_resistor_top': ['resistor', '电阻', '200k'],
    'feedback_resistor_bottom': ['resistor', '电阻', '44.2k'],
    'current_limit_resistor': ['resistor', '电阻', '1k'],
    'indicator': ['LED', 'red LED', '发光二极管', '指示灯'],
}

ROLE_FILTER_RULES: dict[str, dict[str, Any]] = {
    'buck_regulator': {
        'prefer_tokens': ['buck', '降压', 'step-down', 'tps', 'mp', 'sy8'],
        'reject_tokens': ['ldo', 'linear', 'boost', '升压', 'charge pump'],
    },
    'inductor': {
        'prefer_tokens': ['inductor', '电感', 'uh', 'µh', 'μh'],
        'reject_tokens': ['bead', 'ferrite', '变压器', 'transformer'],
        'target_uH': 4.7,
    },
    'input_capacitor': {
        'prefer_tokens': ['capacitor', '电容', 'mlcc', 'x5r', 'x7r'],
        'reject_tokens': ['supercap'],
        'target_uF': 22.0,
    },
    'output_capacitor': {
        'prefer_tokens': ['capacitor', '电容', 'mlcc', 'x5r', 'x7r'],
        'reject_tokens': ['supercap'],
        'target_uF': 22.0,
    },
    'feedback_resistor_top': {
        'prefer_tokens': ['resistor', '电阻', '200k'],
        'reject_tokens': ['pot', 'trimmer', '可调'],
        'target_ohm': 200000.0,
    },
    'feedback_resistor_bottom': {
        'prefer_tokens': ['resistor', '电阻', '44.2k', '43k', '47k'],
        'reject_tokens': ['pot', 'trimmer', '可调'],
        'target_ohm': 44200.0,
    },
    'current_limit_resistor': {
        'prefer_tokens': ['resistor', '电阻', '1k', '1000'],
        'reject_tokens': ['pot', 'trimmer', '可调'],
        'target_ohm': 1000.0,
    },
    'indicator': {
        'prefer_tokens': ['led', '发光二极管', '指示灯', 'red', '红'],
        'reject_tokens': ['driver', 'controller', 'module', 'strip'],
    },
}


def flatten_search_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        flattened: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                flattened.append(item)
            else:
                flattened.extend(flatten_search_items(item))
        return flattened
    if isinstance(payload, dict):
        keys = ['items', 'list', 'rows', 'records', 'result', 'data', 'devices', 'symbols']
        for key in keys:
            value = payload.get(key)
            if value is not None:
                nested = flatten_search_items(value)
                if nested:
                    return nested
        if any(k in payload for k in ('uuid', 'id', 'name', 'title')):
            return [payload]
    return []


def map_item_to_candidate(role: str, item: dict[str, Any], library_uuid: str) -> PartCandidate:
    item_library_uuid = str(item.get('libraryUuid', '') or item.get('library_uuid', '') or library_uuid)
    place_uuid = str(item.get('uuid', '') or item.get('deviceUuid', '') or item.get('id', '') or '')
    part_id = str(item.get('id', '') or item.get('deviceUuid', '') or item.get('uuid', '') or item.get('symbolUuid', '') or f'{role}-auto')
    display_name = str(item.get('name', '') or item.get('title', '') or item.get('displayName', '') or part_id)
    symbol_uuid = str(item.get('symbolUuid', '') or item.get('symbol_uuid', '') or place_uuid or item.get('id', ''))
    lcsc_id = str(item.get('lcscId', '') or item.get('lcsc_id', '') or item.get('c', ''))
    package = str(item.get('package', '') or item.get('packageName', '') or item.get('encapsulation', ''))
    manufacturer = str(item.get('manufacturer', '') or item.get('brand', ''))
    mpn = str(item.get('mpn', '') or item.get('partNumber', '') or item.get('model', ''))
    pin_count_raw = item.get('pinCount', item.get('pin_count', 0))
    try:
        pin_count = int(pin_count_raw)
    except (TypeError, ValueError):
        pin_count = 0
    named_pin_count_raw = item.get('namedPinCount', item.get('named_pin_count', 0))
    try:
        named_pin_count = int(named_pin_count_raw)
    except (TypeError, ValueError):
        named_pin_count = 0
    return PartCandidate(
        part_id=part_id,
        display_name=display_name,
        lcsc_id=lcsc_id,
        manufacturer=manufacturer,
        mpn=mpn,
        package=package,
        library_uuid=item_library_uuid,
        place_uuid=place_uuid,
        symbol_uuid=symbol_uuid,
        pin_count=pin_count,
        named_pin_count=named_pin_count,
        availability_status='unknown',
    )


def _candidate_text(candidate: PartCandidate) -> str:
    return normalize_text(
        ' '.join(
            [
                candidate.display_name,
                candidate.manufacturer,
                candidate.mpn,
                candidate.package,
                candidate.lcsc_id,
            ]
        )
    )


def _extract_first_unit_value(text: str, units: list[str]) -> float | None:
    for unit in units:
        pattern = re.compile(rf'(\d+(?:\.\d+)?)\s*{re.escape(unit)}', re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            continue
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            continue
    return None


def _extract_resistance_ohm(text: str) -> float | None:
    patterns = [
        re.compile(r'(\d+(?:\.\d+)?)\s*k(?:ohm|Ω)?', re.IGNORECASE),
        re.compile(r'(\d+(?:\.\d+)?)\s*m(?:ohm|Ω)?', re.IGNORECASE),
        re.compile(r'(\d+(?:\.\d+)?)\s*(?:ohm|Ω|r)\b', re.IGNORECASE),
    ]
    for index, pattern in enumerate(patterns):
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if index == 0:
            return value * 1000.0
        if index == 1:
            return value * 1_000_000.0
        return value
    return None


def _closeness_score(value: float, target: float, full_score: int) -> int:
    if value <= 0 or target <= 0:
        return 0
    ratio = abs(value - target) / target
    if ratio <= 0.15:
        return full_score
    if ratio <= 0.30:
        return int(full_score * 0.6)
    if ratio <= 0.60:
        return int(full_score * 0.2)
    return -6


def score_candidate_for_role(role: str, candidate: PartCandidate, include_pin_count: bool = True) -> int:
    score = 0
    text = _candidate_text(candidate)
    rule = ROLE_FILTER_RULES.get(role, {})
    prefer_tokens = [normalize_text(token) for token in rule.get('prefer_tokens', [])]
    reject_tokens = [normalize_text(token) for token in rule.get('reject_tokens', [])]

    if candidate.library_uuid and (candidate.place_uuid or candidate.symbol_uuid):
        score += 20
    if candidate.lcsc_id:
        score += 8
    if include_pin_count:
        if candidate.pin_count > 0:
            score += 50
        else:
            score -= 8
        if candidate.named_pin_count > 0:
            score += 12

    prefer_hits = sum(1 for token in prefer_tokens if token and token in text)
    reject_hits = sum(1 for token in reject_tokens if token and token in text)
    score += prefer_hits * 6
    score -= reject_hits * 10

    target_uf = rule.get('target_uF')
    if isinstance(target_uf, (int, float)):
        uf = _extract_first_unit_value(text, ['uf', 'µf', 'μf'])
        if uf is not None:
            score += _closeness_score(uf, float(target_uf), 24)

    target_uh = rule.get('target_uH')
    if isinstance(target_uh, (int, float)):
        uh = _extract_first_unit_value(text, ['uh', 'µh', 'μh'])
        if uh is not None:
            score += _closeness_score(uh, float(target_uh), 22)

    target_ohm = rule.get('target_ohm')
    if isinstance(target_ohm, (int, float)):
        ohm = _extract_resistance_ohm(text)
        if ohm is not None:
            score += _closeness_score(ohm, float(target_ohm), 28)

    return score


def is_candidate_rejected(role: str, candidate: PartCandidate) -> bool:
    text = _candidate_text(candidate)
    rule = ROLE_FILTER_RULES.get(role, {})
    reject_tokens = [normalize_text(token) for token in rule.get('reject_tokens', [])]
    prefer_tokens = [normalize_text(token) for token in rule.get('prefer_tokens', [])]
    has_reject = any(token and token in text for token in reject_tokens)
    has_prefer = any(token and token in text for token in prefer_tokens)
    if role == 'buck_regulator' and has_reject and not has_prefer:
        return True
    if role.startswith('feedback_resistor') and has_reject:
        return True
    if role == 'buck_regulator' and is_truthy_env('BRIDGE_REQUIRE_NAMED_PINS', 'false') and candidate.named_pin_count <= 0:
        return True
    if not candidate.library_uuid or not (candidate.place_uuid or candidate.symbol_uuid):
        return True
    return False


def requires_named_pins(role: str) -> bool:
    if not is_truthy_env('BRIDGE_REQUIRE_NAMED_PINS', 'false'):
        return False
    return normalize_text(role) in ('buck_regulator',)


def try_search_path(
    client: BridgeControlClient,
    client_id: str,
    path: str,
    keyword: str,
    library_uuid: str,
    request_prefix: str,
) -> list[dict[str, Any]]:
    candidate_args: list[list[Any]] = [
        [keyword],
        [keyword, library_uuid] if library_uuid else [keyword],
        [{'keyword': keyword, 'libraryUuid': library_uuid, 'page': 1, 'pageSize': 12}],
    ]
    for index, args in enumerate(candidate_args):
        try:
            ok, result = client.api_invoke(
                client_id=client_id,
                path=path,
                args=args,
                request_id=f'{request_prefix}-{index + 1}',
            )
        except Exception:  # noqa: BLE001
            continue
        if not ok:
            continue
        items = flatten_search_items(result)
        if items:
            return items
    return []


def resolve_system_library_uuid(client: BridgeControlClient, client_id: str) -> str:
    paths = [
        'LIB_LibrariesList.getSystemLibraryUuid',
        'lib_LibrariesList.getSystemLibraryUuid',
    ]
    for index, path in enumerate(paths):
        try:
            ok, result = client.api_invoke(
                client_id=client_id,
                path=path,
                args=[],
                request_id=f'lib-system-{index + 1}',
            )
        except Exception:  # noqa: BLE001
            continue
        if ok and isinstance(result, (str, int)):
            value = str(result).strip()
            if value:
                return value
    return ''


def auto_search_catalog(
    control_url: str,
    control_token: str,
    client_id: str,
    role_keywords: dict[str, list[str]],
) -> tuple[dict[str, list[PartCandidate]], list[str], dict[str, Any]]:
    client = BridgeControlClient(control_url, control_token)
    library_uuid = resolve_system_library_uuid(client, client_id)
    require_pin_geometry = is_truthy_env('BRIDGE_REQUIRE_PIN_GEOMETRY', 'true')
    allow_pinless_fallback = is_truthy_env('BRIDGE_ALLOW_PINLESS_FALLBACK', 'true')
    cache_root = Path(env('BRIDGE_CACHE_DIR', '.where/cache'))
    cache_path = cache_root / 'auto-search-cache-v2.json'
    cache_payload = load_json_file(cache_path, {})
    if not isinstance(cache_payload, dict):
        cache_payload = {}
    search_cache = cache_payload.get('searchResults', {})
    if not isinstance(search_cache, dict):
        search_cache = {}
    pin_geometry_cache = cache_payload.get('pinGeometry', {})
    if not isinstance(pin_geometry_cache, dict):
        pin_geometry_cache = {}
    search_paths = [
        'LIB_Device.search',
        'LIB_Symbol.search',
        'lib_Device.search',
        'lib_Symbol.search',
    ]
    catalog: dict[str, list[PartCandidate]] = {}
    logs: list[str] = []
    diagnostics: dict[str, Any] = {
        'requirePinGeometry': require_pin_geometry,
        'allowPinlessFallback': allow_pinless_fallback,
        'roles': {},
        'pinSourceStats': {},
        'cachePath': str(cache_path),
        'searchCacheHitCount': 0,
        'searchCacheMissCount': 0,
    }
    pin_source_stats: dict[str, int] = {}
    max_pin_probe_per_role = to_int_env('BRIDGE_MAX_PIN_PROBE_PER_ROLE', 16)
    max_ranked_candidates_per_role = to_int_env('BRIDGE_MAX_RANKED_CANDIDATES_PER_ROLE', 8)
    time_budget_sec = to_float(env('BRIDGE_AUTO_SEARCH_TIME_BUDGET_SEC', '120'), 120.0)
    started_at = time.monotonic()
    budget_exhausted = False
    for role, keywords in role_keywords.items():
        if time.monotonic() - started_at > time_budget_sec:
            budget_exhausted = True
            diagnostics['roles'][role] = {
                'rawHitCount': 0,
                'pinProbeCount': 0,
                'strictCount': 0,
                'relaxedCount': 0,
                'rejectedCount': 0,
                'missingPinGeometryCount': 0,
                'duplicateCount': 0,
                'selectedMode': 'skipped_time_budget',
            }
            continue
        strict_found: list[PartCandidate] = []
        strict_scored: list[tuple[int, PartCandidate]] = []
        relaxed_found: list[PartCandidate] = []
        relaxed_scored: list[tuple[int, PartCandidate]] = []
        raw_candidates: list[tuple[int, PartCandidate]] = []
        seen_part_ids: set[str] = set()
        require_named_pins = requires_named_pins(role)
        raw_hit_count = 0
        pin_probe_count = 0
        duplicate_count = 0
        rejected_count = 0
        missing_pin_geometry_count = 0
        for keyword in keywords:
            if time.monotonic() - started_at > time_budget_sec:
                budget_exhausted = True
                break
            normalized = keyword.strip()
            if not normalized:
                continue
            items: list[dict[str, Any]] = []
            for path_index, path in enumerate(search_paths):
                cache_key = f'{role}|{path}|{normalized}'
                if cache_key in search_cache:
                    cached_items = search_cache.get(cache_key)
                    items = [item for item in cached_items if isinstance(item, dict)] if isinstance(cached_items, list) else []
                    diagnostics['searchCacheHitCount'] += 1
                    if items:
                        break
                    continue
                items = try_search_path(
                    client=client,
                    client_id=client_id,
                    path=path,
                    keyword=normalized,
                    library_uuid=library_uuid,
                    request_prefix=f'search-{role}-{path_index + 1}',
                )
                search_cache[cache_key] = items
                diagnostics['searchCacheMissCount'] += 1
                if items:
                    break
            if not items:
                continue
            raw_hit_count += len(items)
            for item in items[:8]:
                if time.monotonic() - started_at > time_budget_sec:
                    budget_exhausted = True
                    break
                candidate = map_item_to_candidate(role, item, library_uuid)
                if is_candidate_rejected(role, candidate):
                    rejected_count += 1
                    continue
                if candidate.part_id in seen_part_ids:
                    duplicate_count += 1
                    continue
                seen_part_ids.add(candidate.part_id)
                score = score_candidate_for_role(role, candidate, include_pin_count=True)
                raw_candidates.append((score, candidate))
            if len(raw_candidates) >= 24:
                break

        ranked_candidates = [item for _, item in sorted(raw_candidates, key=lambda pair: pair[0], reverse=True)]
        candidate_limit = min(len(ranked_candidates), max_ranked_candidates_per_role)
        for candidate in ranked_candidates[:candidate_limit]:
            if time.monotonic() - started_at > time_budget_sec:
                budget_exhausted = True
                break
            if candidate.pin_count <= 0:
                if pin_probe_count >= max_pin_probe_per_role:
                    continue
                candidate = enrich_candidate_pin_geometry(
                    client=client,
                    client_id=client_id,
                    candidate=candidate,
                    cache=pin_geometry_cache,
                    request_id_prefix=f'pin-enrich-{role}',
                    stats=pin_source_stats,
                )
                pin_probe_count += 1
            score = score_candidate_for_role(role, candidate, include_pin_count=True)
            has_required_pins = candidate.pin_count > 0 and (not require_named_pins or candidate.named_pin_count > 0)
            if has_required_pins:
                strict_found.append(candidate)
                strict_scored.append((score, candidate))
                if len(strict_found) >= 10:
                    break
                continue
            missing_pin_geometry_count += 1
            if require_pin_geometry:
                if allow_pinless_fallback:
                    relaxed_found.append(candidate)
                    relaxed_scored.append((score, candidate))
                continue
            relaxed_found.append(candidate)
            relaxed_scored.append((score, candidate))

        chosen_mode = 'none'
        selected: list[PartCandidate] = []
        if strict_found:
            ranked = [item for _, item in sorted(strict_scored, key=lambda pair: pair[0], reverse=True)]
            selected = ranked[:4]
            chosen_mode = 'strict'
        elif relaxed_found and allow_pinless_fallback:
            ranked = [item for _, item in sorted(relaxed_scored, key=lambda pair: pair[0], reverse=True)]
            selected = ranked[:4]
            chosen_mode = 'pinless_fallback'

        if selected:
            catalog[role] = selected
            logs.append(
                f'Auto-search resolved {len(selected)} candidates for role {role} '
                f'(raw={raw_hit_count}, strict={len(strict_found)}, relaxed={len(relaxed_found)}, mode={chosen_mode}).'
            )
        else:
            logs.append(
                f'Auto-search found no candidates for role {role} '
                f'(raw={raw_hit_count}, rejected={rejected_count}, noPin={missing_pin_geometry_count}, requirePin={require_pin_geometry}).'
            )
        diagnostics['roles'][role] = {
            'rawHitCount': raw_hit_count,
            'pinProbeCount': pin_probe_count,
            'strictCount': len(strict_found),
            'relaxedCount': len(relaxed_found),
            'rejectedCount': rejected_count,
            'missingPinGeometryCount': missing_pin_geometry_count,
            'duplicateCount': duplicate_count,
            'selectedMode': chosen_mode,
        }
    diagnostics['pinSourceStats'] = pin_source_stats
    diagnostics['timeBudgetSec'] = time_budget_sec
    diagnostics['budgetExhausted'] = budget_exhausted
    cache_payload['searchResults'] = search_cache
    cache_payload['pinGeometry'] = pin_geometry_cache
    cache_payload['updatedAt'] = iso_now()
    save_json_file(cache_path, cache_payload)
    if budget_exhausted:
        logs.append('Auto-search stopped early due to time budget exhaustion.')
    return catalog, logs, diagnostics


def _to_bridge_request(request_id: str, op: ExecutionOperation) -> dict[str, Any]:
    action_map = {
        'place_component': ('schematic', 'place_component'),
        'create_wire': ('schematic', 'create_wire'),
        'annotate_net': ('schematic', 'annotate_net'),
        'create_net_port': ('schematic', 'create_net_port'),
        'create_net_flag': ('schematic', 'create_net_flag'),
        'save': ('schematic', 'save'),
        'inspect_connectivity': ('schematic', 'inspect_connectivity'),
        'check_drc': ('schematic', 'check_drc'),
    }
    if op.kind not in action_map:
        raise ValueError(f'Unsupported operation kind: {op.kind}')
    domain, action = action_map[op.kind]
    return {
        'id': request_id,
        'type': 'command.request',
        'protocolVersion': '0.1.0',
        'sessionId': 'server-text-to-schematic',
        'command': {
            'domain': domain,
            'action': action,
            'requiresConfirmation': False,
            'payload': op.payload,
        },
    }


def build_component_placement_map(model: CircuitModel) -> dict[str, dict[str, Any]]:
    placement_map: dict[str, dict[str, Any]] = {}
    layout = get_schematic_layout_config()

    enriched_components: list[dict[str, Any]] = []
    for component in model.components:
        comp_dict = asdict(component)
        comp_dict['role'] = _infer_component_role(component, model.nets)
        enriched_components.append(comp_dict)

    symbol_dims = build_symbol_dimensions_from_components(model.components)
    layout_context = compile_layout_context(
        components=enriched_components,
        nets=[asdict(net) for net in model.nets],
        origin_x=layout['origin_x'],
        origin_y=layout['origin_y'],
        symbol_dimensions=symbol_dims if symbol_dims else None,
    )
    component_placements = layout_context.get('componentPlacements', {})
    # Pre-compute rotations from neighbour directions.
    rotations: dict[str, int] = {}
    for component in model.components:
        rotations[component.ref] = 0 if should_use_fixed_two_pin_rotation(component, model) else compute_rotation_from_neighbors(
            component.ref, model.nets, component_placements,
        )

    for index, component in enumerate(model.components):
        selected = component.selected_part
        place_uuid = selected.place_uuid or selected.symbol_uuid
        if not selected.library_uuid or not place_uuid:
            continue
        anchor_data = component_placements.get(component.ref, {})
        fallback_anchor = _component_anchor(index, layout)
        anchor = {
            'x': int(anchor_data.get('x', fallback_anchor['x'])),
            'y': int(anchor_data.get('y', fallback_anchor['y'])),
        }
        placement_map[component.ref] = {
            'ref': component.ref,
            'role': component.role,
            'x': anchor['x'],
            'y': anchor['y'],
            'rotation': rotations.get(component.ref, 0),
            'mirror': False,
            'libraryUuid': selected.library_uuid,
            'placeUuid': place_uuid,
            'symbolUuid': selected.symbol_uuid,
            'block': anchor_data.get('block', ''),
        }
    return placement_map


def fetch_symbol_file_base64(client: BridgeControlClient, client_id: str, symbol_uuid: str, library_uuid: str, request_id: str) -> str:
    bridge = client.bridge_request(
        client_id=client_id,
        domain='system',
        action='file_manager_get_symbol_file_by_symbol_uuid',
        payload={
            'symbolUuid': symbol_uuid,
            'libraryUuid': library_uuid,
        },
        request_id=request_id,
    )
    if bridge.get('status') != 'success':
        return ''
    file_payload = (
        bridge.get('result', {})
        .get('data', {})
        .get('file', {})
    )
    if not isinstance(file_payload, dict):
        return ''
    base64_payload = file_payload.get('base64')
    return str(base64_payload) if isinstance(base64_payload, str) else ''


def fetch_device_file_base64(client: BridgeControlClient, client_id: str, device_uuid: str, request_id: str) -> str:
    if not device_uuid:
        return ''
    bridge = client.bridge_request(
        client_id=client_id,
        domain='system',
        action='file_manager_get_device_file_by_device_uuid',
        payload={
            'deviceUuid': device_uuid,
        },
        request_id=request_id,
    )
    if bridge.get('status') != 'success':
        return ''
    file_payload = (
        bridge.get('result', {})
        .get('data', {})
        .get('file', {})
    )
    if not isinstance(file_payload, dict):
        return ''
    base64_payload = file_payload.get('base64')
    return str(base64_payload) if isinstance(base64_payload, str) else ''


def fetch_symbol_source_by_open_document(
    client: 'BridgeControlClient',
    client_id: str,
    symbol_uuid: str,
    library_uuid: str,
    request_id: str,
) -> str:
    opened = client.bridge_request(
        client_id=client_id,
        domain='project',
        action='open_library_document',
        payload={
            'libraryUuid': library_uuid,
            'libraryType': 'symbol',
            'uuid': symbol_uuid,
        },
        request_id=f'{request_id}-open',
    )
    if opened.get('status') != 'success':
        return ''
    ok, result = client.api_invoke(
        client_id=client_id,
        path='sys_FileManager.getDocumentSource',
        args=[],
        request_id=f'{request_id}-source',
    )
    if not ok:
        return ''
    if isinstance(result, str):
        return result
    return str(result) if result is not None else ''


def resolve_pin_for_selector(pins: list[dict[str, Any]], selector: str) -> dict[str, Any] | None:
    normalized_selector = normalize_text(selector)
    if not normalized_selector:
        return None
    if normalized_selector.isdigit():
        for pin in pins:
            if normalize_text(str(pin.get('pinNumber', ''))) == normalized_selector:
                return pin
    exact_name_candidates: list[dict[str, Any]] = []
    contains_name_candidates: list[dict[str, Any]] = []
    for pin in pins:
        pin_number = normalize_text(str(pin.get('pinNumber', '')))
        pin_name = normalize_text(str(pin.get('pinName', '')))
        if pin_number == normalized_selector or pin_name == normalized_selector:
            exact_name_candidates.append(pin)
        elif normalized_selector in pin_name:
            contains_name_candidates.append(pin)
    if exact_name_candidates:
        return exact_name_candidates[0]
    if contains_name_candidates:
        return contains_name_candidates[0]
    return None


def resolve_pin_with_role_fallback(
    pins: list[dict[str, Any]],
    selector: str,
    component_role: str,
) -> dict[str, Any] | None:
    resolved = resolve_pin_for_selector(pins, selector)
    if resolved is not None:
        return resolved

    normalized_role = normalize_text(component_role)
    normalized_selector = normalize_text(selector)
    if normalized_role != 'buck_regulator' or not normalized_selector:
        return None

    fallback_number_map: dict[str, list[str]] = {
        'vin': ['5', '6', '4'],
        'in': ['5', '6', '4'],
        'vcc': ['5', '6', '4'],
        'vdd': ['5', '6', '4'],
        'gnd': ['2', '3'],
        'pgnd': ['2', '3'],
        'agnd': ['2', '3'],
        'sw': ['1', '4'],
        'lx': ['1', '4'],
        'fb': ['3', '2'],
        'vfb': ['3', '2'],
        'en': ['4', '6'],
        'enable': ['4', '6'],
    }
    fallback_numbers = fallback_number_map.get(normalized_selector, [])
    if not fallback_numbers:
        return None

    for number in fallback_numbers:
        for pin in pins:
            if normalize_text(str(pin.get('pinNumber', ''))) == number:
                return pin
    return None


def build_manhattan_wire_points(source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, float]]:
    x1 = float(source['x'])
    y1 = float(source['y'])
    x2 = float(target['x'])
    y2 = float(target['y'])
    if abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5:
        return [{'x': x1, 'y': y1}, {'x': x2, 'y': y2}]
    return [
        {'x': x1, 'y': y1},
        {'x': x2, 'y': y1},
        {'x': x2, 'y': y2},
    ]


def operation_id_fragment(value: str) -> str:
    fragment = re.sub(r'[^a-z0-9]+', '-', normalize_text(value)).strip('-')
    return fragment or 'net'


def build_external_net_terminal(endpoint: dict[str, Any], net_name: str) -> dict[str, float]:
    kind = _normalize_net_kind(net_name)
    offset = to_float(env('BRIDGE_EXTERNAL_NET_STUB_LENGTH', '80'), 80.0)
    direction = -1.0 if kind == 'power' else 1.0
    return {
        'x': float(endpoint['x']) + direction * offset,
        'y': float(endpoint['y']),
    }


def set_designator_in_source_text(source: str, primitive_id: str, designator: str) -> tuple[str, bool]:
    updated_lines: list[str] = []
    changed = False
    for line in source.splitlines():
        record = parse_source_record(line.strip())
        if not record:
            updated_lines.append(line)
            continue
        header = record['header']
        body = record['body']
        if (
            str(header.get('type', '')) == 'ATTR'
            and str(body.get('parentId', '')) == primitive_id
            and str(body.get('key', '')) == 'Designator'
        ):
            body['value'] = designator
            body['valueVisible'] = True
            updated_lines.append(f'{json.dumps(header, separators=(",", ":"))}||{json.dumps(body, ensure_ascii=False, separators=(",", ":"))}|')
            changed = True
            continue
        updated_lines.append(line)
    return '\n'.join(updated_lines), changed


def set_component_designator(
    client: 'BridgeControlClient',
    client_id: str,
    primitive_id: str,
    designator: str,
    request_id: str,
) -> bool:
    if not primitive_id or not designator:
        return False
    source_response = client.bridge_request(
        client_id=client_id,
        domain='system',
        action='file_manager_get_document_source',
        payload={},
        request_id=f'{request_id}-source',
    )
    if source_response.get('status') != 'success':
        return False
    source = (
        source_response.get('result', {})
        .get('data', {})
        .get('source', '')
    )
    if not isinstance(source, str) or not source:
        return False
    updated_source, changed = set_designator_in_source_text(source, primitive_id, designator)
    if not changed:
        return False
    set_response = client.bridge_request(
        client_id=client_id,
        domain='system',
        action='file_manager_set_document_source',
        payload={'source': updated_source},
        request_id=f'{request_id}-set',
    )
    return set_response.get('status') == 'success'


def build_safe_wire_operations(
    model: CircuitModel,
    control_url: str,
    control_token: str,
    client_id: str,
) -> tuple[list[ExecutionOperation], list[str], list[str], dict[str, Any]]:
    client = BridgeControlClient(control_url, control_token)
    placement_map = build_component_placement_map(model)
    pin_map: dict[str, list[dict[str, Any]]] = {}
    symbol_pin_cache: dict[str, tuple[list[dict[str, Any]], str]] = {}
    logs: list[str] = []
    issues: list[str] = []
    wiring_mode = normalize_text(env('BRIDGE_WIRING_MODE', 'full')) or 'full'
    max_wire_distance = to_float(env('BRIDGE_WIRE_MAX_DISTANCE', '260'), 260.0)
    diagnostics: dict[str, Any] = {
        'components': {},
        'nets': {},
        'missingSelectors': {},
    }

    for ref, placement in placement_map.items():
        symbol_cache_key = f'{placement["libraryUuid"]}:{placement["symbolUuid"]}'
        cached = symbol_pin_cache.get(symbol_cache_key)
        if cached is not None:
            parsed_pins, pin_source_mode = cached
            base64_payload = ''
            source_text = 'cached'
        else:
            parsed_pins = []
            source_text = ''
            base64_payload = fetch_symbol_file_base64(
                client=client,
                client_id=client_id,
                symbol_uuid=str(placement['symbolUuid']),
                library_uuid=str(placement['libraryUuid']),
                request_id=f'pin-file-{model.request_id}-{ref.lower()}',
            )
            if base64_payload:
                parsed_pins = parse_symbol_pins_from_base64(base64_payload)
                pin_source_mode = 'archive_base64'
            else:
                parsed_pins = []
                pin_source_mode = 'missing'
            if not parsed_pins:
                device_uuid = str(placement.get('placeUuid', '') or '')
                device_base64 = fetch_device_file_base64(
                    client=client,
                    client_id=client_id,
                    device_uuid=device_uuid,
                    request_id=f'pin-device-{model.request_id}-{ref.lower()}',
                )
                resolved_symbol_uuid = parse_device_symbol_uuid_from_base64(device_base64)
                if resolved_symbol_uuid:
                    resolved_base64 = fetch_symbol_file_base64(
                        client=client,
                        client_id=client_id,
                        symbol_uuid=resolved_symbol_uuid,
                        library_uuid=str(placement['libraryUuid']),
                        request_id=f'pin-symbol-{model.request_id}-{ref.lower()}',
                    )
                    resolved_pins = parse_symbol_pins_from_base64(resolved_base64)
                    if resolved_pins:
                        parsed_pins = resolved_pins
                        placement['symbolUuid'] = resolved_symbol_uuid
                        pin_source_mode = 'device_symbol_archive'
            symbol_pin_cache[symbol_cache_key] = (parsed_pins, pin_source_mode)
        absolute_pins: list[dict[str, Any]] = []
        if parsed_pins:
            for pin in parsed_pins:
                endpoint_local = resolve_pin_endpoint_local(pin)
                origin_local = {'x': float(pin.get('x', 0.0)), 'y': float(pin.get('y', 0.0))}
                absolute = transform_point(
                    {'x': endpoint_local['x'], 'y': endpoint_local['y']},
                    placement,
                )
                absolute_origin = transform_point(origin_local, placement)
                absolute_pins.append(
                    {
                        'pinNumber': str(pin.get('pinNumber', '')),
                        'pinName': str(pin.get('pinName', '')),
                        'x': absolute['x'],
                        'y': absolute['y'],
                        'origin': {'x': absolute_origin['x'], 'y': absolute_origin['y']},
                    }
                )
        elif is_truthy_env('BRIDGE_ALLOW_TWO_PIN_VIRTUAL_PINS', 'true') and is_two_pin_virtual_role(str(placement.get('role', ''))):
            absolute_pins = build_virtual_two_pin_geometry(str(placement.get('role', '')), placement)
            pin_source_mode = 'virtual_two_pin'
        pin_map[ref] = absolute_pins
        logs.append(f'Pin map resolved for {ref}: {len(absolute_pins)} pins.')
        diagnostics['components'][ref] = {
            'libraryUuid': placement['libraryUuid'],
            'symbolUuid': placement['symbolUuid'],
            'pinCount': len(absolute_pins),
            'virtualPinCount': sum(1 for pin in absolute_pins if pin.get('virtual')),
            'symbolFetchOk': bool(source_text or base64_payload or cached),
            'pinSourceMode': pin_source_mode,
        }

    wire_operations: list[ExecutionOperation] = []
    wire_index = 0
    for net in model.nets:
        endpoints: list[dict[str, Any]] = []
        missing_members: list[str] = []
        for member in net.members:
            if '.' not in member:
                continue
            ref, selector = member.split('.', 1)
            pins = pin_map.get(ref, [])
            component_role = str(placement_map.get(ref, {}).get('role', ''))
            pin = resolve_pin_with_role_fallback(pins, selector, component_role)
            if pin is None:
                issues.append(f'{ERROR_PIN_MISSING}:{net.name}:{member}')
                missing_members.append(member)
                diagnostics['missingSelectors'].setdefault(ref, []).append(selector)
                continue
            attach = adjust_schematic_wire_command_point(pin)
            origin = pin.get('origin')
            adjusted_origin = adjust_schematic_wire_command_point(origin) if isinstance(origin, dict) else None
            endpoints.append({
                'ref': ref,
                'selector': selector,
                'x': attach['x'],
                'y': attach['y'],
                'origin': adjusted_origin,
            })
        diagnostics['nets'][net.name] = {
            'memberCount': len(net.members),
            'resolvedEndpoints': len(endpoints),
            'missingMembers': missing_members,
        }
        if len(endpoints) == 1 and wiring_mode != 'labels' and _normalize_net_kind(net.name) in {'power', 'ground'}:
            endpoint = endpoints[0]
            terminal = build_external_net_terminal(endpoint, net.name)
            net_id = operation_id_fragment(net.name)
            if _normalize_net_kind(net.name) == 'ground':
                wire_index += 1
                wire_operations.append(
                    ExecutionOperation(
                        id=f'op-terminal-flag-{net_id}',
                        kind='create_net_flag',
                        payload={
                            'identification': 'Ground',
                            'net': net.name,
                            'position': terminal,
                        },
                        on_error='continue',
                        notes=[f'Create ground symbol connected to {endpoint["ref"]}.{endpoint["selector"]}.'],
                    )
                )
            else:
                wire_operations.append(
                    ExecutionOperation(
                        id=f'op-terminal-port-{net_id}',
                        kind='create_net_port',
                        payload={
                            'direction': 'BI',
                            'net': net.name,
                            'position': terminal,
                        },
                        on_error='continue',
                        notes=[f'Create power/net port connected to {endpoint["ref"]}.{endpoint["selector"]}.'],
                    )
                )
            wire_index += 1
            wire_operations.append(
                ExecutionOperation(
                    id=f'op-wire-terminal-{wire_index:03d}',
                    kind='create_wire',
                    payload={
                        'points': build_manhattan_wire_points(terminal, endpoint),
                        'netName': net.name,
                    },
                    on_error='continue',
                    notes=[
                        f'Wire external net terminal {net.name} to {endpoint["ref"]}.{endpoint["selector"]}',
                    ],
                )
            )
            continue
        if len(endpoints) < 2:
            continue
        source = endpoints[0]
        for target in endpoints[1:]:
            if wiring_mode == 'labels':
                continue
            if wiring_mode == 'hybrid':
                src_block = placement_map.get(source['ref'], {}).get('block', '')
                tgt_block = placement_map.get(target['ref'], {}).get('block', '')
                if not src_block or src_block != tgt_block:
                    continue
                if abs(source['x'] - target['x']) > max_wire_distance or abs(source['y'] - target['y']) > max_wire_distance:
                    continue
            elif wiring_mode != 'full':
                continue
            wire_index += 1
            wire_operations.append(
                ExecutionOperation(
                    id=f'op-wire-safe-{wire_index:03d}',
                    kind='create_wire',
                    payload={
                        'points': build_wire_points_with_pin_stubs(source, target),
                        'netName': net.name,
                    },
                    on_error='continue',
                    notes=[
                        f'Safe wire via pin mapping: {source["ref"]}.{source["selector"]} -> {target["ref"]}.{target["selector"]}',
                    ],
                )
            )
    logs.append(f'Safe wiring generated {len(wire_operations)} wire operations.')
    return wire_operations, logs, issues, diagnostics


def execute_plan(plan: ExecutionPlan, control_url: str, control_token: str, client_id: str) -> dict[str, Any]:
    client = BridgeControlClient(control_url, control_token)
    results: list[dict[str, Any]] = []
    failed_count = 0
    fallback_events: list[dict[str, str]] = []
    execution_page: dict[str, str] = {}

    if is_truthy_env('BRIDGE_CREATE_NEW_PAGE', 'true'):
        try:
            info = client.bridge_request(
                client_id=client_id,
                domain='schematic',
                action='get_current_schematic_info',
                payload={},
                request_id=f'{plan.request_id}-schematic-info',
            )
            info_data = info.get('result', {}).get('data', {})
            schematic_uuid = str(
                info_data.get('schematicUuid')
                or info_data.get('uuid')
                or (info_data.get('schematic', {}) if isinstance(info_data.get('schematic', {}), dict) else {}).get('uuid', '')
                or ''
            )
            if schematic_uuid:
                created = client.bridge_request(
                    client_id=client_id,
                    domain='schematic',
                    action='create_schematic_page',
                    payload={'schematicUuid': schematic_uuid},
                    request_id=f'{plan.request_id}-schematic-new-page',
                )
                created_data = created.get('result', {}).get('data', {})
                page_uuid = str(
                    created_data.get('schematicPageUuid')
                    or (created_data.get('schematicPage', {}) if isinstance(created_data.get('schematicPage', {}), dict) else {}).get('uuid', '')
                    or (created_data.get('page', {}) if isinstance(created_data.get('page', {}), dict) else {}).get('uuid', '')
                    or ''
                )
                page_name = str(
                    (created_data.get('schematicPage', {}) if isinstance(created_data.get('schematicPage', {}), dict) else {}).get('name', '')
                    or (created_data.get('page', {}) if isinstance(created_data.get('page', {}), dict) else {}).get('name', '')
                    or ''
                )
                if page_uuid:
                    execution_page = {'uuid': page_uuid, 'name': str(page_name or '')}
                    opened_ok = False
                    for attempt in range(3):
                        opened = client.bridge_request(
                            client_id=client_id,
                            domain='project',
                            action='open_document',
                            payload={'documentUuid': page_uuid},
                            request_id=f'{plan.request_id}-schematic-open-page-{attempt + 1}',
                        )
                        opened_ok = opened.get('status') == 'success'
                        if opened_ok:
                            break
                        time.sleep(0.2)
                    if not opened_ok:
                        return {
                            'ok': False,
                            'failedCount': 1,
                            'results': [],
                            'fallbackEvents': [
                                {
                                    'trigger': ERROR_EXECUTION_FAILED,
                                    'strategy': 'open_new_page_failed',
                                }
                            ],
                            'page': execution_page,
                        }
        except Exception:
            pass

    for index, op in enumerate(plan.operations):
        request_id = f'{plan.request_id}-exec-{index + 1:03d}'
        request_payload = _to_bridge_request(request_id, op)
        try:
            response = client.post_json('/request', {'clientId': client_id, 'request': request_payload})
            bridge = response.get('response', {})
            status = bridge.get('status')
            ok = status == 'success'
            entry = {
                'operationId': op.id,
                'kind': op.kind,
                'status': status,
                'ok': ok,
                'response': bridge,
            }
            results.append(entry)
            if not ok:
                failed_count += 1
                fallback_events.append({
                    'trigger': ERROR_EXECUTION_FAILED,
                    'strategy': 'collect_error_and_continue' if op.on_error == 'continue' else 'stop_execution',
                })
                if op.on_error != 'continue':
                    break
        except urllib.error.URLError as error:
            failed_count += 1
            results.append({
                'operationId': op.id,
                'kind': op.kind,
                'status': 'transport_error',
                'ok': False,
                'error': str(error),
            })
            fallback_events.append({'trigger': ERROR_EXECUTION_FAILED, 'strategy': 'stop_execution'})
            break

    return {
        'ok': failed_count == 0,
        'failedCount': failed_count,
        'results': results,
        'fallbackEvents': fallback_events,
        'page': execution_page,
    }


def resolve_client_id(control_url: str, control_token: str) -> str:
    explicit = env('BRIDGE_TARGET_CLIENT_ID')
    if explicit:
        return explicit
    client = BridgeControlClient(control_url, control_token)
    payload = client.get_json('/sessions')
    sessions = payload.get('sessions', [])
    if not sessions:
        raise RuntimeError('No connected bridge sessions were found.')
    first = sessions[0]
    client_id = str(first.get('clientId', ''))
    if not client_id:
        raise RuntimeError('Connected session did not provide a clientId.')
    return client_id


def write_output_files(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        'requirement': output_dir / 'requirement-spec.json',
        'schematic_construction_description_md': output_dir / 'schematic-construction-description.md',
        'schematic_construction_description_json': output_dir / 'schematic-construction-description.json',
        'circuit': output_dir / 'circuit-model.json',
        'netlist': output_dir / 'netlist.json',
        'spice_netlist': output_dir / 'spice-netlist.cir',
        'spice_netlist_json': output_dir / 'spice-netlist.json',
        'ngspice_execution_json': output_dir / 'ngspice-execution.json',
        'ngspice_execution_log': output_dir / 'ngspice-execution.log',
        'ngspice_feedback_json': output_dir / 'ngspice-feedback.json',
        'plan': output_dir / 'execution-plan.json',
        'summary': output_dir / 'pipeline-summary.json',
    }
    for key in ('requirement', 'circuit', 'netlist', 'plan', 'summary'):
        path = paths[key]
        value = payload.get(key)
        if value is None:
            continue
        with path.open('w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write('\n')
    spice_netlist = payload.get('spice_netlist')
    if isinstance(spice_netlist, dict):
        cir_path = paths['spice_netlist']
        json_path = paths['spice_netlist_json']
        cir_path.write_text(str(spice_netlist.get('text', '') or ''), encoding='utf-8')
        with json_path.open('w', encoding='utf-8') as file:
            json.dump(spice_netlist, file, ensure_ascii=False, indent=2)
            file.write('\n')
    ngspice_execution = payload.get('ngspice_execution')
    if isinstance(ngspice_execution, dict):
        json_path = paths['ngspice_execution_json']
        log_path = paths['ngspice_execution_log']
        with json_path.open('w', encoding='utf-8') as file:
            json.dump(ngspice_execution, file, ensure_ascii=False, indent=2)
            file.write('\n')
        log_path.write_text(str(ngspice_execution.get('log_text', '') or ''), encoding='utf-8')
    ngspice_feedback = payload.get('ngspice_feedback')
    if isinstance(ngspice_feedback, dict):
        json_path = paths['ngspice_feedback_json']
        with json_path.open('w', encoding='utf-8') as file:
            json.dump(ngspice_feedback, file, ensure_ascii=False, indent=2)
            file.write('\n')
    scd = payload.get('schematic_construction_description')
    if isinstance(scd, dict):
        md_path = paths['schematic_construction_description_md']
        json_path = paths['schematic_construction_description_json']
        md_text = str(scd.get('markdown', '') or '')
        md_path.write_text(md_text, encoding='utf-8')
        with json_path.open('w', encoding='utf-8') as file:
            json.dump(scd, file, ensure_ascii=False, indent=2)
            file.write('\n')
    return {name: str(path) for name, path in paths.items()}


def run() -> None:
    spec = requirement_from_env()
    ensure_requirement(spec)
    catalog = load_part_catalog()
    pipeline_logs: list[str] = []
    auto_search_enabled = is_truthy_env('BRIDGE_AUTO_SEARCH_LIB', 'true')
    control_url = env('BRIDGE_CONTROL_URL', 'http://127.0.0.1:8788')
    control_token = env('BRIDGE_CONTROL_TOKEN')
    selected_client_id = env('BRIDGE_TARGET_CLIENT_ID')
    if auto_search_enabled:
        try:
            client_id = selected_client_id or resolve_client_id(control_url, control_token)
            auto_catalog, auto_logs, auto_diagnostics = auto_search_catalog(
                control_url=control_url,
                control_token=control_token,
                client_id=client_id,
                role_keywords=ROLE_SEARCH_KEYWORDS,
            )
            pipeline_logs.extend(auto_logs)
            for role, candidates in auto_catalog.items():
                if role not in catalog or not catalog[role]:
                    catalog[role] = candidates
            if not auto_catalog:
                pipeline_logs.append('Auto-search ran but no library candidates were discovered.')
        except Exception as error:  # noqa: BLE001
            pipeline_logs.append(f'Auto-search skipped due to runtime error: {error}')
            auto_diagnostics = {'error': str(error)}
    else:
        auto_diagnostics = {'enabled': False}

    model = synthesize_circuit_model(spec, catalog)
    netlist = build_netlist_from_circuit_model(model)
    spice_netlist = build_spice_netlist_from_netlist(netlist)
    ngspice_execution = execute_ngspice_netlist(spice_netlist)
    ngspice_feedback = build_ngspice_feedback(spec, model, spice_netlist, ngspice_execution)
    model.risks = list(dict.fromkeys(model.risks + ngspice_feedback.risk_updates))
    spec.unknowns = list(dict.fromkeys(spec.unknowns + ngspice_feedback.requirement_unknowns))
    scd_document = build_scd_document(spec, model)
    wiring_mode = normalize_text(env('BRIDGE_WIRING_MODE', 'full')) or 'full'
    safe_wiring_enabled = is_truthy_env('BRIDGE_ENABLE_SAFE_WIRING', 'true')
    if wiring_mode == 'labels':
        safe_wiring_enabled = False
    safe_wire_operations: list[ExecutionOperation] = []
    safe_wiring_issues: list[str] = []
    if safe_wiring_enabled:
        try:
            client_id = selected_client_id or resolve_client_id(control_url, control_token)
            generated_wires, wire_logs, wire_issues, wire_diagnostics = build_safe_wire_operations(
                model=model,
                control_url=control_url,
                control_token=control_token,
                client_id=client_id,
            )
            safe_wire_operations = generated_wires
            safe_wiring_issues = wire_issues
            pipeline_logs.extend(wire_logs)
        except Exception as error:  # noqa: BLE001
            pipeline_logs.append(f'Safe wiring skipped due to runtime error: {error}')
            wire_diagnostics = {'error': str(error)}
    else:
        wire_diagnostics = {'enabled': False}

    plan = compile_execution_plan(model, safe_wire_operations=safe_wire_operations)
    requested_layout_engine = normalize_text(env('BRIDGE_LAYOUT_ENGINE', 'elk')) or 'elk'

    execute_enabled = normalize_text(env('BRIDGE_EXECUTE_PLAN', 'false')) in ('1', 'true', 'yes', 'on')
    execution_result: dict[str, Any] = {
        'enabled': execute_enabled,
        'startedAt': iso_now(),
    }
    if execute_enabled:
        client_id = resolve_client_id(control_url, control_token)
        execution_result['clientId'] = client_id
        execution_result['result'] = execute_plan(plan, control_url, control_token, client_id)
    execution_result['finishedAt'] = iso_now()

    summary = {
        'requestId': spec.request_id,
        'pipeline': {
            'requirementSchema': REQ_SCHEMA_VERSION,
            'schematicConstructionSchema': SCD_SCHEMA_VERSION,
            'circuitSchema': MODEL_SCHEMA_VERSION,
            'netlistSchema': NETLIST_SCHEMA_VERSION,
            'spiceNetlistSchema': SPICE_NETLIST_SCHEMA_VERSION,
            'ngspiceExecutionSchema': NGSPICE_EXECUTION_SCHEMA_VERSION,
            'ngspiceFeedbackSchema': NGSPICE_FEEDBACK_SCHEMA_VERSION,
            'planSchema': PLAN_SCHEMA_VERSION,
        },
        'log': [
            f'REQ parsed goal: {spec.goal}',
            f'SCD normalized blocks: {len(scd_document.blocks)} / statements: {sum(len(block.statements) for block in scd_document.blocks)}',
            f'MODEL synthesized topology: {model.topology}',
            f'NETLIST components: {len(netlist.components)} / nets: {len(netlist.nets)}',
            f'SPICE lines: {len(spice_netlist.lines)} / warnings: {len(spice_netlist.warnings)}',
            f'NGSPICE enabled: {ngspice_execution.enabled} attempted: {ngspice_execution.attempted} success: {ngspice_execution.success}',
            f'NGSPICE feedback risks: {len(ngspice_feedback.risk_updates)} / recommendations: {len(ngspice_feedback.recommendations)}',
            f'PLAN compiled operations: {len(plan.operations)}',
            f'LAYOUT engine requested: {requested_layout_engine}',
            f'WIRING mode: {wiring_mode}',
            f'EXEC mode: {"execute" if execute_enabled else "dry-run"}',
        ] + pipeline_logs,
        'openRisks': model.risks,
        'simulationFeedback': asdict(ngspice_feedback),
        'safeWiring': {
            'enabled': safe_wiring_enabled,
            'generatedWireCount': len(safe_wire_operations),
            'issues': safe_wiring_issues,
            'diagnostics': wire_diagnostics,
        },
        'autoSearch': auto_diagnostics,
        'execution': execution_result,
    }

    output_bundle = {
        'requirement': asdict(spec),
        'schematic_construction_description': asdict(scd_document),
        'circuit': asdict(model),
        'netlist': asdict(netlist),
        'spice_netlist': {
            'schema_version': spice_netlist.schema_version,
            'request_id': spice_netlist.request_id,
            'source_netlist': spice_netlist.source_netlist,
            'warnings': spice_netlist.warnings,
            'node_map': spice_netlist.node_map,
            'lines': [
                {
                    'ref': line.ref,
                    'kind': line.kind,
                    'line': line.line,
                    'supported': line.supported,
                    'notes': line.notes,
                }
                for line in spice_netlist.lines
            ],
            'text': render_spice_netlist(spice_netlist),
        },
        'ngspice_execution': asdict(ngspice_execution),
        'ngspice_feedback': asdict(ngspice_feedback),
        'plan': asdict(plan),
        'summary': summary,
    }
    output_dir = Path(env('BRIDGE_PIPELINE_OUTPUT_DIR', '.where/pipeline-output')) / spec.request_id
    output_files = write_output_files(output_bundle, output_dir)

    result = {
        'requestId': spec.request_id,
        'generatedAt': iso_now(),
        'outputFiles': output_files,
        'requirement': asdict(spec),
        'schematic_construction_description': asdict(scd_document),
        'circuit': asdict(model),
        'netlist': asdict(netlist),
        'spice_netlist': {
            'schema_version': spice_netlist.schema_version,
            'request_id': spice_netlist.request_id,
            'source_netlist': spice_netlist.source_netlist,
            'warnings': spice_netlist.warnings,
            'node_map': spice_netlist.node_map,
            'lines': [
                {
                    'ref': line.ref,
                    'kind': line.kind,
                    'line': line.line,
                    'supported': line.supported,
                    'notes': line.notes,
                }
                for line in spice_netlist.lines
            ],
            'text': render_spice_netlist(spice_netlist),
        },
        'ngspice_execution': asdict(ngspice_execution),
        'ngspice_feedback': asdict(ngspice_feedback),
        'plan': asdict(plan),
        'summary': summary,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('Server text-to-schematic pipeline failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)
