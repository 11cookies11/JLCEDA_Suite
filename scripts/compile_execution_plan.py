#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from schematic_layout_rules import compile_layout_context


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


def to_int_env(name: str, fallback: int) -> int:
    raw = env(name)
    if not raw:
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


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


def get_schematic_layout_config() -> dict[str, int]:
    return {
        'origin_x': to_int_env('BRIDGE_SCH_PLACE_ORIGIN_X', 420),
        'origin_y': to_int_env('BRIDGE_SCH_PLACE_ORIGIN_Y', 220),
        'columns': max(1, to_int_env('BRIDGE_SCH_PLACE_COLUMNS', 4)),
        'pitch_x': max(20, to_int_env('BRIDGE_SCH_PLACE_PITCH_X', 120)),
        'pitch_y': max(20, to_int_env('BRIDGE_SCH_PLACE_PITCH_Y', 100)),
        'label_x_offset': to_int_env('BRIDGE_SCH_LABEL_X_OFFSET', 420),
        'label_y_start_offset': to_int_env('BRIDGE_SCH_LABEL_Y_START_OFFSET', -120),
        'label_y_step': max(8, to_int_env('BRIDGE_SCH_LABEL_Y_STEP', 28)),
        'flag_x_offset': to_int_env('BRIDGE_SCH_FLAG_X_OFFSET', 500),
    }


def component_anchor(index: int, layout: dict[str, int]) -> dict[str, int]:
    col = index % layout['columns']
    row = index // layout['columns']
    return {
        'x': layout['origin_x'] + col * layout['pitch_x'],
        'y': layout['origin_y'] + row * layout['pitch_y'],
    }


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
    layout = get_schematic_layout_config()
    layout_context = compile_layout_context(
        components=[item for item in components if isinstance(item, dict)],
        nets=[item for item in nets if isinstance(item, dict)],
        origin_x=layout['origin_x'],
        origin_y=layout['origin_y'],
    )
    component_placements = layout_context.get('componentPlacements', {})
    net_port_placements = layout_context.get('netPortPlacements', [])

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
        ref = str(component.get('ref', f'U{index + 1}'))
        anchor_data = component_placements.get(ref, {})
        anchor = {
            'x': int(anchor_data.get('x', component_anchor(index, layout)['x'])),
            'y': int(anchor_data.get('y', component_anchor(index, layout)['y'])),
        }
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
                notes=[f'Place {ref}.', f'Rule block={anchor_data.get("block", "unknown")}'],
            )
        )

    for placement in net_port_placements:
        if not isinstance(placement, dict):
            continue
        net_name = normalize_net_name(str(placement.get('netName', '')))
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
                    'Net-port fallback is robust in current JLCEDA runtime when label creation is unavailable.',
                    f'Rule class={placement.get("netClass", "signal")} anchor={placement.get("anchorRef", "")}.{placement.get("anchorPin", "")}',
                ],
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
                        'position': {
                            'x': int(placement.get('x', layout['origin_x'])) + 80,
                            'y': int(placement.get('y', layout['origin_y'])),
                        },
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
                        'position': {
                            'x': int(placement.get('x', layout['origin_x'])) + 80,
                            'y': int(placement.get('y', layout['origin_y'])),
                        },
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
