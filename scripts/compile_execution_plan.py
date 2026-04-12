#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


MODEL_SCHEMA_VERSION = 'circuit-model.v1'
PLAN_SCHEMA_VERSION = 'execution-plan.v1'


def env(name: str, fallback: str = '') -> str:
    value = os.environ.get(name)
    return value if isinstance(value, str) and value else fallback


def parse_json_env(name: str) -> dict[str, Any] | None:
    raw = env(name)
    if not raw:
        return None
    return json.loads(raw)


def load_circuit_model() -> dict[str, Any]:
    from_env = parse_json_env('BRIDGE_CIRCUIT_MODEL_JSON')
    if from_env is not None:
        return from_env

    file_path = env('BRIDGE_CIRCUIT_MODEL_FILE')
    if not file_path:
        raise ValueError('BRIDGE_CIRCUIT_MODEL_JSON or BRIDGE_CIRCUIT_MODEL_FILE is required.')
    with Path(file_path).open('r', encoding='utf-8') as file:
        return json.load(file)


def normalize_net_name(net_name: str) -> str:
    return str(net_name or '').strip()


def is_ground_net(net_name: str) -> bool:
    return normalize_net_name(net_name).upper() in ('GND', 'AGND', 'PGND')


def is_power_net(net_name: str) -> bool:
    normalized = normalize_net_name(net_name).upper()
    if normalized in ('3V3', '+3V3', '5V', '+5V', '12V', '+12V', 'VIN', 'VCC', 'VDD'):
        return True
    return normalized.startswith('+')


def component_anchor(index: int) -> dict[str, int]:
    col = index % 5
    row = index // 5
    return {'x': -120 + col * 90, 'y': -60 + row * 90}


@dataclass
class ExecutionOperation:
    id: str
    kind: str
    payload: dict[str, Any]
    on_error: str = 'continue'
    notes: list[str] = field(default_factory=list)


@dataclass
class FallbackRule:
    trigger_code: str
    strategy: str
    detail: str


@dataclass
class ExecutionPlan:
    schema_version: str
    request_id: str
    target: dict[str, Any]
    operations: list[ExecutionOperation]
    fallback_rules: list[FallbackRule]


def compile_plan(circuit_model: dict[str, Any]) -> ExecutionPlan:
    schema_version = str(circuit_model.get('schema_version', ''))
    if schema_version != MODEL_SCHEMA_VERSION:
        raise ValueError(f'Unsupported circuit schema_version: {schema_version}')

    request_id = str(circuit_model.get('request_id') or uuid.uuid4())
    components = circuit_model.get('components', [])
    nets = circuit_model.get('nets', [])

    operations: list[ExecutionOperation] = []

    for index, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        ref = str(component.get('ref', f'U{index + 1}'))
        selected = component.get('selected_part', {})
        if not isinstance(selected, dict):
            continue
        library_uuid = str(selected.get('library_uuid', ''))
        symbol_uuid = str(selected.get('symbol_uuid', ''))
        if not library_uuid or not symbol_uuid:
            continue
        anchor = component_anchor(index)
        operations.append(
            ExecutionOperation(
                id=f'op-place-{ref.lower()}',
                kind='place_component',
                payload={
                    'libraryUuid': library_uuid,
                    'uuid': symbol_uuid,
                    'position': anchor,
                    'rotation': 0,
                    'mirror': False,
                    'addIntoBom': True,
                    'addIntoPcb': True,
                },
                on_error='stop',
                notes=[f'Place {ref}.'],
            )
        )

    for net in nets:
        if not isinstance(net, dict):
            continue
        net_name = normalize_net_name(str(net.get('name', '')))
        if not net_name:
            continue
        operations.append(
            ExecutionOperation(
                id=f'op-label-{net_name.lower().replace("+", "p")}',
                kind='annotate_net',
                payload={
                    'netName': net_name,
                    'position': {'x': 360, 'y': 40 + len(operations) * 12},
                },
                on_error='continue',
                notes=['Label-based fallback is deterministic when wire endpoints are unknown.'],
            )
        )
        if is_ground_net(net_name):
            operations.append(
                ExecutionOperation(
                    id='op-flag-gnd',
                    kind='create_net_flag',
                    payload={
                        'identification': 'Ground',
                        'net': net_name,
                        'position': {'x': 420, 'y': 40 + len(operations) * 12},
                    },
                    on_error='continue',
                )
            )
        elif is_power_net(net_name):
            operations.append(
                ExecutionOperation(
                    id=f'op-flag-{net_name.lower().replace("+", "p")}',
                    kind='create_net_flag',
                    payload={
                        'identification': 'Power',
                        'net': net_name,
                        'position': {'x': 420, 'y': 40 + len(operations) * 12},
                    },
                    on_error='continue',
                )
            )

    operations.extend(
        [
            ExecutionOperation(
                id='op-check-connectivity',
                kind='inspect_connectivity',
                payload={'allSchematicPages': False, 'tolerance': 2, 'maxIssues': 200},
                on_error='continue',
            ),
            ExecutionOperation(
                id='op-check-drc',
                kind='check_drc',
                payload={'strict': True, 'userInterface': False, 'includeVerboseError': True},
                on_error='continue',
            ),
            ExecutionOperation(
                id='op-save',
                kind='save',
                payload={},
                on_error='continue',
            ),
        ]
    )

    fallback_rules = [
        FallbackRule(
            trigger_code='PART_UNAVAILABLE',
            strategy='replace_with_backup_candidate_and_recompile',
            detail='Choose the next candidate for the same role and regenerate plan.',
        ),
        FallbackRule(
            trigger_code='PIN_MISSING',
            strategy='stop_and_request_pin_verified_symbol',
            detail='Do not continue auto-wiring without pin geometry.',
        ),
        FallbackRule(
            trigger_code='WIRE_FAILED',
            strategy='retry_with_labels_then_manual_review',
            detail='Keep net labels and ask for user confirmation of final wiring.',
        ),
        FallbackRule(
            trigger_code='EXECUTION_FAILED',
            strategy='collect_error_and_replan',
            detail='Collect bridge error, then regenerate from corrected context.',
        ),
    ]

    if not any(item.kind == 'place_component' for item in operations):
        fallback_rules.append(
            FallbackRule(
                trigger_code='PART_UNAVAILABLE',
                strategy='stop_without_execution',
                detail='No components had executable library/symbol mapping.',
            )
        )

    return ExecutionPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        request_id=request_id,
        target={'mode': 'active_document'},
        operations=operations,
        fallback_rules=fallback_rules,
    )


def write_output(plan: ExecutionPlan) -> str:
    output_file = env('BRIDGE_EXECUTION_PLAN_FILE')
    if not output_file:
        output_root = Path(env('BRIDGE_PIPELINE_OUTPUT_DIR', '.where/pipeline-output'))
        output_dir = output_root / plan.request_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / 'execution-plan.json'
    else:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as file:
        json.dump(asdict(plan), file, ensure_ascii=False, indent=2)
        file.write('\n')
    return str(output_path)


def run() -> None:
    circuit_model = load_circuit_model()
    plan = compile_plan(circuit_model)
    output_path = write_output(plan)
    print(
        json.dumps(
            {
                'requestId': plan.request_id,
                'schemaVersion': plan.schema_version,
                'operationCount': len(plan.operations),
                'outputFile': output_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('Compile execution plan failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)
