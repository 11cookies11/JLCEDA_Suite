#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .env_utils import env, parse_json_env, is_truthy_env, to_float, normalize_text
from .schema_versions import (
    CIRCUIT_MODEL_SCHEMA_VERSION,
    NGSPICE_EXECUTION_SCHEMA_VERSION,
    NGSPICE_FEEDBACK_SCHEMA_VERSION,
    NETLIST_SCHEMA_VERSION,
    REQUIREMENT_SPEC_SCHEMA_VERSION,
    SPICE_NETLIST_SCHEMA_VERSION,
)

# --- data models ---


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


# --- utility ---


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_net_kind(name: str) -> str:
    normalized = name.strip().upper()
    if normalized in {'GND', 'AGND', 'DGND', 'PGND', 'SGND'}:
        return 'ground'
    if normalized.startswith('+') or any(token in normalized for token in ('VCC', 'VDD', 'VIN', 'VOUT', 'VBAT', 'PWR')):
        return 'power'
    return 'signal'


def _sanitize_spice_node_name(name: str) -> str:
    sanitized = re.sub(r'[^A-Za-z0-9_]', '_', name.strip())
    if sanitized and sanitized[0].isdigit():
        sanitized = f'N_{sanitized}'
    return sanitized or 'UNNAMED'


def _netlist_component_kind(component: NetlistComponent) -> str:
    role = component.role.lower()
    if role.endswith('_capacitor') or 'capacitor' in role:
        return 'C'
    if role.endswith('_resistor') or 'resistor' in role:
        return 'R'
    if role.endswith('_inductor') or 'inductor' in role:
        return 'L'
    if 'diode' in role or 'led' in role or 'indicator' in role:
        return 'D'
    return 'U'


TWO_PIN_VIRTUAL_PIN_ROLES = {
    'current_limit_resistor',
    'feedback_resistor_top',
    'feedback_resistor_bottom',
    'input_capacitor',
    'output_capacitor',
    'inductor',
    'indicator',
}


def _is_two_pin_virtual_role(role: str) -> bool:
    return role in TWO_PIN_VIRTUAL_PIN_ROLES


# --- requirement / catalog ---


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
        schema_version=REQUIREMENT_SPEC_SCHEMA_VERSION,
        request_id='default-001',
        project_id='default-001',
        goal='5V to 3.3V buck converter, 2A output',
        electrical_targets=ElectricalTargets(
            vin_min_v=4.5,
            vin_max_v=5.5,
            vout_target_v=3.3,
            iout_max_a=2.0,
        ),
    )


def requirement_from_env() -> RequirementSpec:
    raw = parse_json_env('BRIDGE_REQUIREMENT_SPEC_JSON', {})
    if isinstance(raw, dict) and raw.get('goal'):
        req = raw
        schema_ver = str(req.get('schema_version', REQUIREMENT_SPEC_SCHEMA_VERSION))
        targets = req.get('electrical_targets', req.get('electricalTargets', {}))
        if not isinstance(targets, dict):
            targets = {}
        return RequirementSpec(
            schema_version=schema_ver,
            request_id=str(req.get('request_id', 'env-001')),
            project_id=str(req.get('project_id', 'env-001')),
            goal=str(req.get('goal', '')),
            electrical_targets=ElectricalTargets(
                vin_min_v=float(targets.get('vin_min_v', targets.get('vinMinV', 4.5))),
                vin_max_v=float(targets.get('vin_max_v', targets.get('vinMaxV', 5.5))),
                vout_target_v=float(targets.get('vout_target_v', targets.get('voutTargetV', 3.3))),
                iout_max_a=float(targets.get('iout_max_a', targets.get('ioutMaxA', 2.0))),
                ripple_limit_mv=float(targets.get('ripple_limit_mv', targets.get('rippleLimitMv', 50.0))),
                efficiency_target_percent=float(targets.get('efficiency_target_percent', targets.get('efficiencyTargetPercent', 85.0))),
                switching_frequency_hz=float(targets.get('switching_frequency_hz', targets.get('switchingFrequencyHz', 500000.0))),
            ),
            constraints=req.get('constraints', {}),
            preferences=req.get('preferences', {}),
            acceptance_criteria=req.get('acceptance_criteria', req.get('acceptanceCriteria', [])),
            unknowns=req.get('unknowns', []),
        )
    text = env('BRIDGE_REQUIREMENT_TEXT')
    if text:
        return RequirementSpec(
            schema_version=REQUIREMENT_SPEC_SCHEMA_VERSION,
            request_id='text-001',
            project_id='text-001',
            goal=text.strip(),
            electrical_targets=ElectricalTargets(
                vin_min_v=4.5,
                vin_max_v=5.5,
                vout_target_v=3.3,
                iout_max_a=2.0,
            ),
        )
    return build_default_requirement()


def ensure_requirement(spec: RequirementSpec) -> None:
    if not spec.electrical_targets.vin_min_v:
        spec.electrical_targets.vin_min_v = 4.5
    if not spec.electrical_targets.vin_max_v:
        spec.electrical_targets.vin_max_v = 5.5
    if not spec.electrical_targets.vout_target_v:
        spec.electrical_targets.vout_target_v = 3.3
    if not spec.electrical_targets.iout_max_a:
        spec.electrical_targets.iout_max_a = 1.0


def ensure_circuit_model(model: CircuitModel) -> None:
    if not model.topology:
        model.topology = 'buck'


# --- circuit synthesis ---


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
        if selected.pin_count <= 0 and not _is_two_pin_virtual_role(component.role):
            risks.append(f'{component.ref} pin geometry is not confirmed.')
        if component.availability_status == 'unavailable':
            risks.append(f'{component.ref} selected part is currently marked unavailable.')

    return CircuitModel(
        schema_version=CIRCUIT_MODEL_SCHEMA_VERSION,
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
        schema_version=CIRCUIT_MODEL_SCHEMA_VERSION,
        request_id=spec.request_id,
        project_id=spec.project_id,
        topology=str(spec.preferences.get('topology', 'buck')),
        components=components,
        nets=nets,
        calculations=calculations,
        design_decisions=decisions,
        risks=risks,
    )


# --- netlist ---


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


# --- spice netlist ---


def build_spice_netlist_from_netlist(netlist: NetlistModel) -> SpiceNetlistModel:
    spice_lines: list[SpiceNetlistLine] = []
    node_map: dict[str, str] = {}
    ref_counter: dict[str, int] = defaultdict(int)

    for component in netlist.components:
        kind = _netlist_component_kind(component)
        ref_counter[kind] += 1
        prefix = kind
        index = ref_counter[kind]
        pins = component.pins
        if not pins:
            spice_lines.append(
                SpiceNetlistLine(
                    ref=f'{prefix}{index}',
                    kind=kind,
                    line=f'* {prefix}{index} has no pin connections',
                    supported=False,
                    notes=['No pin data available.'],
                )
            )
            continue

        net_names = [item.net for item in pins]
        nodes: list[str] = []
        unsupported_pins: list[str] = []
        for net_name in net_names:
            mapped = node_map.get(net_name)
            if not mapped:
                sanitized = _sanitize_spice_node_name(net_name)
                node_map[net_name] = sanitized
                mapped = sanitized
            nodes.append(mapped)

        if component.role == 'buck_regulator' and int(component.part.named_pin_count) >= 4:
            # Spice source: Vin SW FB GND
            spice_lines.append(
                SpiceNetlistLine(
                    ref=f'{prefix}{index}',
                    kind=kind,
                    line=f'* {prefix}{index} ({component.value}) is a switching regulator -- subcircuit placeholder',
                    supported=False,
                    notes=['Switching regulator requires a vendor SPICE model.'],
                )
            )
            continue

        if kind == 'R':
            if len(nodes) >= 2:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'{prefix}{index} {nodes[0]} {nodes[1]} {component.value}',
                        supported=True,
                    )
                )
            else:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'* {prefix}{index} has fewer than 2 connections',
                        supported=False,
                        notes=unsupported_pins,
                    )
                )

        elif kind == 'C':
            if len(nodes) >= 2:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'{prefix}{index} {nodes[0]} {nodes[1]} {component.value}',
                        supported=True,
                    )
                )
            else:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'* {prefix}{index} has fewer than 2 connections',
                        supported=False,
                        notes=unsupported_pins,
                    )
                )

        elif kind == 'L':
            if len(nodes) >= 2:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'{prefix}{index} {nodes[0]} {nodes[1]} {component.value}',
                        supported=True,
                    )
                )
            else:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'* {prefix}{index} has fewer than 2 connections',
                        supported=False,
                        notes=unsupported_pins,
                    )
                )

        elif kind == 'D':
            if len(nodes) >= 2:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'{prefix}{index} {nodes[0]} {nodes[1]} LED',
                        supported=True,
                    )
                )
            else:
                spice_lines.append(
                    SpiceNetlistLine(
                        ref=f'{prefix}{index}',
                        kind=kind,
                        line=f'* {prefix}{index} has fewer than 2 connections',
                        supported=False,
                        notes=unsupported_pins,
                    )
                )

        else:
            spice_lines.append(
                SpiceNetlistLine(
                    ref=f'{prefix}{index}',
                    kind=kind,
                    line=f'* {prefix}{index} ({component.value}) not yet supported in SPICE exporter',
                    supported=False,
                    notes=['Component kind not recognized for SPICE export.'],
                )
            )

    # Vsource
    spice_lines.insert(
        0,
        SpiceNetlistLine(
            ref='V1',
            kind='V',
            line=f'V1 {node_map.get("VIN_5V", "VIN_5V")} {node_map.get("GND", "GND")} DC 5.0',
            supported=True,
        ),
    )

    # Analysis
    spice_lines.append(
        SpiceNetlistLine(
            ref='OP',
            kind='analysis',
            line='.op',
            supported=True,
        )
    )
    spice_lines.append(
        SpiceNetlistLine(
            ref='END',
            kind='control',
            line='.end',
            supported=True,
        )
    )

    warnings: list[str] = []
    unsupported_count = sum(1 for item in spice_lines if not item.supported)
    if unsupported_count:
        warnings.append(f'{unsupported_count} spice lines are not fully supported.')
    if len(node_map) < 2:
        warnings.append('Spice net has fewer than 2 nodes; simulation may be unreliable.')

    return SpiceNetlistModel(
        schema_version=SPICE_NETLIST_SCHEMA_VERSION,
        request_id=netlist.request_id,
        source_netlist=f'{netlist.source_model.schema_version}::{netlist.request_id}',
        lines=spice_lines,
        node_map=node_map,
        warnings=warnings,
    )


def render_spice_netlist(spice_netlist: SpiceNetlistModel) -> str:
    parts: list[str] = [f'* Ngspice netlist generated at {_iso_now()}']
    parts.append(f'* Source: {spice_netlist.source_netlist}')
    for node_name, spice_name in sorted(spice_netlist.node_map.items(), key=lambda item: item[1]):
        parts.append(f'* Node map: {node_name} -> {spice_name}')
    parts.append('')
    for item in spice_netlist.lines:
        if not item.supported and item.notes:
            for note in item.notes:
                parts.append(f'* Note: {note}')
        parts.append(item.line)
    return '\n'.join(parts) + '\n'


# --- ngspice ---


def parse_ngspice_log(log_text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        'analysisKinds': [],
        'warnings': [],
        'errors': [],
        'measurements': {},
        'scalarValues': {},
    }
    lines = log_text.split('\n')
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if 'warning' in stripped.lower():
            parsed['warnings'].append(stripped)
        if 'error' in stripped.lower():
            parsed['errors'].append(stripped)
        if lower in {'operating point', 'op'} or lower.startswith('operating point '):
            if 'op' not in parsed['analysisKinds']:
                parsed['analysisKinds'].append('op')
        if lower.startswith('transient analysis') or lower.startswith('tran analysis'):
            if 'tran' not in parsed['analysisKinds']:
                parsed['analysisKinds'].append('tran')
        if lower.startswith('ac analysis'):
            if 'ac' not in parsed['analysisKinds']:
                parsed['analysisKinds'].append('ac')
        if 'Analysis' in stripped and ':' in stripped:
            analysis_kind = stripped.split(':', 1)[-1].strip()
            if analysis_kind not in parsed['analysisKinds']:
                parsed['analysisKinds'].append(analysis_kind)
        if '=' in stripped and any(token in stripped.lower() for token in ('v(', 'i(', 'dc', 'ac', 'tran')):
            key, _, val = stripped.partition('=')
            key = key.strip()
            try:
                parsed['scalarValues'][key] = float(val.strip())
            except ValueError:
                parsed['measurements'][key] = val.strip()
    return parsed


def build_ngspice_feedback(
    spec: RequirementSpec,
    model: CircuitModel,
    spice_netlist: SpiceNetlistModel,
    ngspice_execution: NgspiceExecutionModel,
) -> NgspiceFeedbackModel:
    ok = ngspice_execution.success
    summary_parts: list[str] = []
    risk_updates: list[str] = list(model.risks)
    requirement_unknowns: list[str] = list(spec.unknowns)
    recommendations: list[str] = []

    if ngspice_execution.success:
        summary_parts.append('Ngspice simulation completed successfully.')
        parsed = ngspice_execution.parsed
        analysis_kinds = parsed.get('analysisKinds', [])
        if analysis_kinds:
            recommendations.append(f'Observed analyses: {", ".join(analysis_kinds)}.')
        recommendations.append('Capture measurement lines into a regression fixture for later comparison.')
        vout = parsed.get('scalarValues', {}).get('v(+3v3)', None)
        if vout is not None:
            target = spec.electrical_targets.vout_target_v
            deviation = abs(vout - target)
            if deviation < 0.05 * target:
                summary_parts.append(f'Output voltage {vout:.3f}V is within 5% of target {target}V.')
            else:
                summary_parts.append(f'Output voltage {vout:.3f}V deviates from target {target}V by {deviation:.3f}V.')
                risk_updates.append(f'VOUT deviation {deviation:.3f}V exceeds expected tolerance.')
                recommendations.append('Check feedback resistor values and inductor selection.')
    else:
        summary_parts.append('Ngspice simulation did not complete successfully.')
        if ngspice_execution.error:
            summary_parts.append(f'Error: {ngspice_execution.error}')
            risk_updates.append(f'ngspice execution error: {ngspice_execution.error}')
        if ngspice_execution.returncode is not None:
            risk_updates.append(f'ngspice returned exit code {ngspice_execution.returncode}.')
        risk_updates.append('Simulation failed; circuit behavior is not verified.')
        risk_updates.append('ngspice execution failed and must be resolved before accepting the circuit.')
        recommendations.append('Verify SPICE netlist correctness and ngspice installation.')
        recommendations.append('Review ngspice errors before regenerating the circuit.')
        recommendations.append('Add a simple .op or .tran regression case to confirm the exporter and executor are wired correctly.')

    if ngspice_execution.parsed.get('warnings'):
        summary_parts.append(f'{len(ngspice_execution.parsed["warnings"])} ngspice warnings logged.')

    if ngspice_execution.parsed.get('errors'):
        summary_parts.append(f'{len(ngspice_execution.parsed["errors"])} ngspice errors logged.')
        ok = False

    unsupported = [item for item in spice_netlist.lines if not item.supported]
    if unsupported:
        summary_parts.append(f'{len(unsupported)} spice lines are not supported; simulation may be incomplete.')
        recommendations.append('Consider replacing unsupported components with SPICE-compatible equivalents.')
        recommendations.append('Resolve unsupported SPICE exports or provide richer component models.')

    return NgspiceFeedbackModel(
        schema_version=NGSPICE_FEEDBACK_SCHEMA_VERSION,
        request_id=spec.request_id,
        ok=ok,
        summary=' '.join(summary_parts),
        risk_updates=risk_updates,
        requirement_unknowns=requirement_unknowns,
        recommendations=recommendations,
        evidence={
            'topology': model.topology,
            'componentCount': len(model.components),
            'netCount': len(model.nets),
            'spiceLineCount': len(spice_netlist.lines),
            'ngspiceReturnCode': ngspice_execution.returncode,
        },
    )


def resolve_ngspice_executable() -> str | None:
    explicit = env('NGSPICE_BIN')
    if explicit:
        return explicit
    located = shutil.which('ngspice') or shutil.which('ngspice.exe')
    if located:
        return located
    candidates = [
        Path('C:/Program Files/ngspice/bin/ngspice.exe'),
        Path('C:/Program Files (x86)/ngspice/bin/ngspice.exe'),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def execute_ngspice_netlist(spice_netlist: SpiceNetlistModel) -> NgspiceExecutionModel:
    enabled = is_truthy_env('NGSPICE_ENABLED', 'true')
    if not enabled:
        return NgspiceExecutionModel(
            schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
            request_id=spice_netlist.request_id,
            enabled=False,
            attempted=False,
            executable='',
            command=[],
            netlist_path='',
            log_path='',
            warnings=['ngspice disabled by NGSPICE_ENABLED=false.'],
        )

    executable = resolve_ngspice_executable()
    if not executable:
        return NgspiceExecutionModel(
            schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
            request_id=spice_netlist.request_id,
            enabled=True,
            attempted=False,
            executable='',
            command=[],
            netlist_path='',
            log_path='',
            warnings=['ngspice executable not found.'],
            error='Install ngspice or set NGSPICE_BIN environment variable.',
        )

    output_dir = Path(env('NGSPICE_OUTPUT_DIR', tempfile.mkdtemp(prefix='ngspice_')))
    output_dir.mkdir(parents=True, exist_ok=True)
    netlist_text = render_spice_netlist(spice_netlist)
    netlist_path = output_dir / 'netlist.cir'
    log_path = output_dir / 'ngspice.log'
    netlist_path.write_text(netlist_text, encoding='utf-8')

    command = [executable, '-b', str(netlist_path), '-o', str(log_path)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
        returncode: int | None = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired:
        return NgspiceExecutionModel(
            schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
            request_id=spice_netlist.request_id,
            enabled=True,
            attempted=True,
            executable=executable,
            command=command,
            netlist_path=str(netlist_path),
            log_path=str(log_path),
            returncode=None,
            success=False,
            error='ngspice timed out after 30 seconds.',
        )
    except Exception as exc:
        return NgspiceExecutionModel(
            schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
            request_id=spice_netlist.request_id,
            enabled=True,
            attempted=True,
            executable=executable,
            command=command,
            netlist_path=str(netlist_path),
            log_path=str(log_path),
            returncode=None,
            success=False,
            error=str(exc),
        )

    log_text = ''
    if log_path.exists():
        log_text = log_path.read_text(encoding='utf-8', errors='replace')

    parsed = parse_ngspice_log(log_text)
    success = returncode == 0 and not parsed.get('errors')

    return NgspiceExecutionModel(
        schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
        request_id=spice_netlist.request_id,
        enabled=True,
        attempted=True,
        executable=executable,
        command=command,
        netlist_path=str(netlist_path),
        log_path=str(log_path),
        returncode=returncode,
        success=success,
        stdout=stdout,
        stderr=stderr,
        log_text=log_text,
        parsed=parsed,
    )
