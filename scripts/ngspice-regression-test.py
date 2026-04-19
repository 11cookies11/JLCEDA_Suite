#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server_text_to_schematic import (  # noqa: E402
    CircuitComponent,
    CircuitModel,
    CircuitNet,
    DesignDecision,
    ElectricalTargets,
    NgspiceExecutionModel,
    NetlistComponent,
    NetlistModel,
    NetlistNet,
    NetlistPart,
    NetlistPin,
    NetlistSourceModel,
    PartCandidate,
    REQ_SCHEMA_VERSION,
    MODEL_SCHEMA_VERSION,
    NETLIST_SCHEMA_VERSION,
    NGSPICE_EXECUTION_SCHEMA_VERSION,
    SPICE_NETLIST_SCHEMA_VERSION,
    RequirementSpec,
    build_ngspice_feedback,
    build_spice_netlist_from_netlist,
    parse_ngspice_log,
)


def load_samples() -> dict[str, Any]:
    fixture_path = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'ngspice' / 'regression-samples.json'
    return json.loads(fixture_path.read_text(encoding='utf-8'))


def build_netlist(sample: dict[str, Any]) -> NetlistModel:
    netlist_payload = sample['netlist']
    components: list[NetlistComponent] = []
    for component in netlist_payload.get('components', []):
        pins = [
            NetlistPin(pin=str(pin.get('pin', '')), net=str(pin.get('net', '')))
            for pin in component.get('pins', [])
        ]
        components.append(
            NetlistComponent(
                ref=str(component.get('ref', '')),
                role=str(component.get('role', '')),
                value=str(component.get('value', '')),
                part=NetlistPart(
                    part_id=f'{component.get("ref", "part")}-part',
                    display_name=str(component.get('role', 'part')),
                ),
                pins=pins,
                availability_status='available',
            )
        )
    nets = [
        NetlistNet(
            name=str(net.get('name', '')),
            kind=str(net.get('kind', 'signal')),
            members=[str(member) for member in net.get('members', [])],
        )
        for net in netlist_payload.get('nets', [])
    ]
    return NetlistModel(
        schema_version=NETLIST_SCHEMA_VERSION,
        request_id='regression-rc-lowpass',
        project_id='fixture-project',
        source_model=NetlistSourceModel(schema_version=MODEL_SCHEMA_VERSION, request_id='regression-rc-lowpass'),
        components=components,
        nets=nets,
    )


def build_circuit_model(netlist: NetlistModel) -> CircuitModel:
    components = [
        CircuitComponent(
            ref=component.ref,
            role=component.role,
            value=component.value,
            selected_part=PartCandidate(part_id=component.part.part_id, display_name=component.part.display_name),
            candidate_parts=[],
            availability_status=component.availability_status,
        )
        for component in netlist.components
    ]
    nets = [
        CircuitNet(
            name=net.name,
            members=net.members,
        )
        for net in netlist.nets
    ]
    return CircuitModel(
        schema_version=MODEL_SCHEMA_VERSION,
        request_id=netlist.request_id,
        project_id=netlist.project_id,
        topology='rc_lowpass',
        components=components,
        nets=nets,
        calculations=[],
        design_decisions=[
            DesignDecision(
                title='Use RC low-pass sample',
                rationale='Fixture regression case for ngspice feedback wiring.',
            )
        ],
        risks=[],
    )


def build_requirement(request_id: str) -> RequirementSpec:
    return RequirementSpec(
        schema_version=REQ_SCHEMA_VERSION,
        request_id=request_id,
        project_id='fixture-project',
        goal='Regression sample for ngspice feedback',
        electrical_targets=ElectricalTargets(
            vin_min_v=5.0,
            vin_max_v=5.0,
            vout_target_v=3.3,
            iout_max_a=1.0,
        ),
        constraints={},
        preferences={},
        acceptance_criteria=['Simulation feedback should be structure-preserving.'],
        unknowns=[],
    )


def assert_contains_all(actual: list[str], expected: list[str], label: str) -> None:
    missing = [item for item in expected if item not in actual]
    if missing:
        raise AssertionError(f'{label} missing expected entries: {missing}')


def run_sample(sample: dict[str, Any]) -> dict[str, Any]:
    expected = sample['expected']
    netlist = build_netlist(sample)
    model = build_circuit_model(netlist)
    requirement = build_requirement(netlist.request_id)
    spice = build_spice_netlist_from_netlist(netlist)
    parsed = parse_ngspice_log('Operating point\nv(out) = 1.23\n')
    execution = NgspiceExecutionModel(
        schema_version=NGSPICE_EXECUTION_SCHEMA_VERSION,
        request_id=netlist.request_id,
        enabled=True,
        attempted=True,
        executable='ngspice',
        command=['ngspice'],
        netlist_path='fixture.cir',
        log_path='fixture.log',
        returncode=0,
        success=True,
        stdout='',
        stderr='',
        log_text='Operating point\nv(out) = 1.23\n',
        parsed=parsed,
        warnings=[],
        error='',
    )
    feedback = build_ngspice_feedback(requirement, model, spice, execution)
    if parsed.get('analysisKinds') != expected.get('analysisKinds', []):
        raise AssertionError(f'{sample["name"]}: analysisKinds mismatch: {parsed.get("analysisKinds")} != {expected.get("analysisKinds")}')
    if feedback.ok != bool(expected.get('ok', False)):
        raise AssertionError(f'{sample["name"]}: ok mismatch: {feedback.ok} != {expected.get("ok")}')
    assert_contains_all(feedback.risk_updates, expected.get('risk_contains', []), f'{sample["name"]} risk_updates')
    assert_contains_all(feedback.recommendations, expected.get('recommendation_contains', []), f'{sample["name"]} recommendations')
    return {
        'sample': sample['name'],
        'spiceSchema': spice.schema_version,
        'feedbackSchema': feedback.schema_version,
        'feedback': asdict(feedback),
    }


def main() -> int:
    fixture = load_samples()
    results = [run_sample(sample) for sample in fixture.get('samples', [])]
    print(json.dumps({
        'schema_version': 'ngspice-regression-results.v1',
        'ok': True,
        'resultCount': len(results),
        'results': results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
