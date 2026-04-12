#!/usr/bin/env python3
from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQ_SCHEMA_VERSION = 'requirement-spec.v1'
MODEL_SCHEMA_VERSION = 'circuit-model.v1'
PLAN_SCHEMA_VERSION = 'execution-plan.v1'

ERROR_PART_UNAVAILABLE = 'PART_UNAVAILABLE'
ERROR_PIN_MISSING = 'PIN_MISSING'
ERROR_WIRE_FAILED = 'WIRE_FAILED'
ERROR_EXECUTION_FAILED = 'EXECUTION_FAILED'


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value: Any, fallback: float) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def env(name: str, fallback: str = '') -> str:
    value = os.environ.get(name)
    return value if isinstance(value, str) and value else fallback


def parse_json_env(name: str, fallback: Any) -> Any:
    raw = env(name)
    if not raw:
        return fallback
    return json.loads(raw)


def normalize_text(value: str) -> str:
    return value.strip().lower()


def is_truthy_env(name: str, fallback: str = 'false') -> bool:
    return normalize_text(env(name, fallback)) in ('1', 'true', 'yes', 'on')


def to_int_env(name: str, fallback: int) -> int:
    raw = env(name)
    if not raw:
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def normalize_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return number
        return None
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except ValueError:
            return None
    return None


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes')
    return False


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
        candidate.pin_count = cache[cache_key]
        return candidate
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
                symbol_uuid=candidate.symbol_uuid,
                library_uuid=candidate.library_uuid,
                request_id=f'{request_id_prefix}-src-{candidate.symbol_uuid[:8]}',
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
    cache[cache_key] = pin_count
    candidate.pin_count = pin_count
    return candidate


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
    symbol_uuid: str = ''
    pin_count: int = 0
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
                    symbol_uuid=str(entry.get('symbol_uuid', '') or entry.get('symbolUuid', '')),
                    pin_count=int(entry.get('pin_count', 0) or entry.get('pinCount', 0) or 0),
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
            0 if c.library_uuid and c.symbol_uuid else 1,
            0 if c.pin_count > 0 else 1,
        ),
    )
    selected = sorted_candidates[0]
    availability = selected.availability_status if selected.availability_status in ('available', 'unavailable') else 'unknown'
    return selected, sorted_candidates, availability


def synthesize_circuit_model(spec: RequirementSpec, catalog: dict[str, list[PartCandidate]]) -> CircuitModel:
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
        if not selected.library_uuid or not selected.symbol_uuid:
            risks.append(f'{component.ref} lacks library/symbol mapping and cannot be auto-placed yet.')
        if selected.pin_count <= 0:
            risks.append(f'{component.ref} pin geometry is not confirmed.')
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


def ensure_circuit_model(model: CircuitModel) -> None:
    if model.schema_version != MODEL_SCHEMA_VERSION:
        raise ValueError(f'Unsupported circuit schema_version: {model.schema_version}')
    if not model.components:
        raise ValueError('Circuit model must include at least one component.')
    if not model.nets:
        raise ValueError('Circuit model must include nets.')


def _component_anchor(index: int) -> dict[str, int]:
    x_origin = -120
    y_origin = -40
    return {'x': x_origin + (index * 80), 'y': y_origin}


def compile_execution_plan(model: CircuitModel, safe_wire_operations: list[ExecutionOperation] | None = None) -> ExecutionPlan:
    ensure_circuit_model(model)
    operations: list[ExecutionOperation] = []
    placeable_refs: set[str] = set()

    for idx, component in enumerate(model.components):
        selected = component.selected_part
        if not selected.library_uuid or not selected.symbol_uuid:
            continue
        anchor = _component_anchor(idx)
        operations.append(
            ExecutionOperation(
                id=f'op-place-{component.ref.lower()}',
                kind='place_component',
                payload={
                    'libraryUuid': selected.library_uuid,
                    'uuid': selected.symbol_uuid,
                    'position': anchor,
                    'rotation': 0,
                    'mirror': False,
                    'addIntoBom': True,
                    'addIntoPcb': True,
                },
                on_error='stop',
                notes=[f'Place {component.ref} ({component.role})'],
            )
        )
        placeable_refs.add(component.ref)

    safe_wire_operations = safe_wire_operations or []
    if safe_wire_operations:
        operations.extend(safe_wire_operations)

    for net in model.nets:
        operations.append(
            ExecutionOperation(
                id=f'op-label-{net.name.lower().replace("+", "p")}',
                kind='annotate_net',
                payload={
                    'netName': net.name,
                    'position': {'x': 360, 'y': 40 + (len(operations) * 12)},
                },
                on_error='continue',
                notes=['Net label is used as a robust fallback when exact wire endpoints are unavailable.'],
            )
        )
        if net.name in ('GND', '+3V3'):
            flag_kind = 'Ground' if net.name == 'GND' else 'Power'
            operations.append(
                ExecutionOperation(
                    id=f'op-flag-{net.name.lower().replace("+", "p")}',
                    kind='create_net_flag',
                    payload={
                        'identification': flag_kind,
                        'net': net.name,
                        'position': {'x': 420, 'y': 40 + (len(operations) * 12)},
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
    part_id = str(item.get('id', '') or item.get('uuid', '') or item.get('deviceUuid', '') or item.get('symbolUuid', '') or f'{role}-auto')
    display_name = str(item.get('name', '') or item.get('title', '') or item.get('displayName', '') or part_id)
    symbol_uuid = str(item.get('uuid', '') or item.get('symbolUuid', '') or item.get('id', ''))
    lcsc_id = str(item.get('lcscId', '') or item.get('lcsc_id', '') or item.get('c', ''))
    package = str(item.get('package', '') or item.get('packageName', '') or item.get('encapsulation', ''))
    manufacturer = str(item.get('manufacturer', '') or item.get('brand', ''))
    mpn = str(item.get('mpn', '') or item.get('partNumber', '') or item.get('model', ''))
    pin_count_raw = item.get('pinCount', item.get('pin_count', 0))
    try:
        pin_count = int(pin_count_raw)
    except (TypeError, ValueError):
        pin_count = 0
    return PartCandidate(
        part_id=part_id,
        display_name=display_name,
        lcsc_id=lcsc_id,
        manufacturer=manufacturer,
        mpn=mpn,
        package=package,
        library_uuid=library_uuid,
        symbol_uuid=symbol_uuid,
        pin_count=pin_count,
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


def score_candidate_for_role(role: str, candidate: PartCandidate) -> int:
    score = 0
    text = _candidate_text(candidate)
    rule = ROLE_FILTER_RULES.get(role, {})
    prefer_tokens = [normalize_text(token) for token in rule.get('prefer_tokens', [])]
    reject_tokens = [normalize_text(token) for token in rule.get('reject_tokens', [])]

    if candidate.library_uuid and candidate.symbol_uuid:
        score += 20
    if candidate.lcsc_id:
        score += 8
    if candidate.pin_count > 0:
        score += 50
    else:
        score -= 8

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
    if not candidate.library_uuid or not candidate.symbol_uuid:
        return True
    return False


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
    }
    pin_geometry_cache: dict[str, int] = {}
    pin_source_stats: dict[str, int] = {}
    max_pin_probe_per_role = to_int_env('BRIDGE_MAX_PIN_PROBE_PER_ROLE', 16)
    time_budget_sec = to_float(env('BRIDGE_AUTO_SEARCH_TIME_BUDGET_SEC', '25'), 25.0)
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
                items = try_search_path(
                    client=client,
                    client_id=client_id,
                    path=path,
                    keyword=normalized,
                    library_uuid=library_uuid,
                    request_prefix=f'search-{role}-{path_index + 1}',
                )
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
                if any(existing.part_id == candidate.part_id for existing in strict_found) or any(existing.part_id == candidate.part_id for existing in relaxed_found):
                    duplicate_count += 1
                    continue
                score = score_candidate_for_role(role, candidate)
                if candidate.pin_count > 0:
                    strict_found.append(candidate)
                    strict_scored.append((score, candidate))
                    continue
                missing_pin_geometry_count += 1
                if require_pin_geometry:
                    if allow_pinless_fallback:
                        relaxed_found.append(candidate)
                        relaxed_scored.append((score, candidate))
                    continue
                relaxed_found.append(candidate)
                relaxed_scored.append((score, candidate))
            if len(strict_found) >= 10:
                break

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
    if budget_exhausted:
        logs.append('Auto-search stopped early due to time budget exhaustion.')
    return catalog, logs, diagnostics


def _to_bridge_request(request_id: str, op: ExecutionOperation) -> dict[str, Any]:
    action_map = {
        'place_component': ('schematic', 'place_component'),
        'create_wire': ('schematic', 'create_wire'),
        'annotate_net': ('schematic', 'annotate_net'),
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
    for index, component in enumerate(model.components):
        selected = component.selected_part
        if not selected.library_uuid or not selected.symbol_uuid:
            continue
        anchor = _component_anchor(index)
        placement_map[component.ref] = {
            'ref': component.ref,
            'x': anchor['x'],
            'y': anchor['y'],
            'rotation': 0,
            'mirror': False,
            'libraryUuid': selected.library_uuid,
            'symbolUuid': selected.symbol_uuid,
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


def build_safe_wire_operations(
    model: CircuitModel,
    control_url: str,
    control_token: str,
    client_id: str,
) -> tuple[list[ExecutionOperation], list[str], list[str], dict[str, Any]]:
    client = BridgeControlClient(control_url, control_token)
    placement_map = build_component_placement_map(model)
    pin_map: dict[str, list[dict[str, Any]]] = {}
    logs: list[str] = []
    issues: list[str] = []
    diagnostics: dict[str, Any] = {
        'components': {},
        'nets': {},
        'missingSelectors': {},
    }

    for ref, placement in placement_map.items():
        base64_payload = fetch_symbol_file_base64(
            client=client,
            client_id=client_id,
            symbol_uuid=str(placement['symbolUuid']),
            library_uuid=str(placement['libraryUuid']),
            request_id=f'pin-file-{model.request_id}-{ref.lower()}',
        )
        parsed_pins = parse_symbol_pins_from_base64(base64_payload)
        absolute_pins: list[dict[str, Any]] = []
        for pin in parsed_pins:
            absolute = transform_point(
                {'x': float(pin.get('x', 0.0)), 'y': float(pin.get('y', 0.0))},
                placement,
            )
            absolute_pins.append(
                {
                    'pinNumber': str(pin.get('pinNumber', '')),
                    'pinName': str(pin.get('pinName', '')),
                    'x': absolute['x'],
                    'y': absolute['y'],
                }
            )
        pin_map[ref] = absolute_pins
        logs.append(f'Pin map resolved for {ref}: {len(absolute_pins)} pins.')
        diagnostics['components'][ref] = {
            'libraryUuid': placement['libraryUuid'],
            'symbolUuid': placement['symbolUuid'],
            'pinCount': len(absolute_pins),
            'symbolFetchOk': bool(base64_payload),
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
            pin = resolve_pin_for_selector(pins, selector)
            if pin is None:
                issues.append(f'{ERROR_PIN_MISSING}:{net.name}:{member}')
                missing_members.append(member)
                diagnostics['missingSelectors'].setdefault(ref, []).append(selector)
                continue
            endpoints.append({'ref': ref, 'selector': selector, 'x': pin['x'], 'y': pin['y']})
        diagnostics['nets'][net.name] = {
            'memberCount': len(net.members),
            'resolvedEndpoints': len(endpoints),
            'missingMembers': missing_members,
        }
        if len(endpoints) < 2:
            continue
        source = endpoints[0]
        for target in endpoints[1:]:
            wire_index += 1
            wire_operations.append(
                ExecutionOperation(
                    id=f'op-wire-safe-{wire_index:03d}',
                    kind='create_wire',
                    payload={
                        'points': [
                            {'x': source['x'], 'y': source['y']},
                            {'x': target['x'], 'y': target['y']},
                        ],
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
        'circuit': output_dir / 'circuit-model.json',
        'plan': output_dir / 'execution-plan.json',
        'summary': output_dir / 'pipeline-summary.json',
    }
    for key, path in paths.items():
        with path.open('w', encoding='utf-8') as file:
            json.dump(payload[key], file, ensure_ascii=False, indent=2)
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
    safe_wiring_enabled = is_truthy_env('BRIDGE_ENABLE_SAFE_WIRING', 'true')
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
            'circuitSchema': MODEL_SCHEMA_VERSION,
            'planSchema': PLAN_SCHEMA_VERSION,
        },
        'log': [
            f'REQ parsed goal: {spec.goal}',
            f'MODEL synthesized topology: {model.topology}',
            f'PLAN compiled operations: {len(plan.operations)}',
            f'EXEC mode: {"execute" if execute_enabled else "dry-run"}',
        ] + pipeline_logs,
        'openRisks': model.risks,
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
        'circuit': asdict(model),
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
        'circuit': asdict(model),
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
