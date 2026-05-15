#!/usr/bin/env python3
"""KiCad pipeline runner: circuit-model.json → netlist → execution-plan → KiCad files → ERC."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .circuit_pipeline import (
    NetlistModel,
    build_netlist_from_circuit_model,
)
from .compile_kicad_execution_plan import compile_plan, write_output, KiCadExecutionPlan
from .env_utils import is_truthy_env
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import write_project
from .parts_pipeline import run_parts_pipeline


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open('r', encoding='utf-8') as f:
        return json.load(f)


def build_netlist(model: dict[str, Any]) -> dict[str, Any]:
    from .circuit_pipeline import (
        CircuitModel, CircuitComponent, CircuitNet, PartCandidate,
        CircuitCalculation, DesignDecision, ElectricalTargets, RequirementSpec,
    )
    components = []
    for c in model.get('components', []):
        sp = c.get('selected_part', {})
        components.append(CircuitComponent(
            ref=str(c.get('ref', '')),
            role=str(c.get('role', '')),
            value=str(c.get('value', '')),
            selected_part=PartCandidate(
                part_id=str(sp.get('part_id', '')),
                display_name=str(sp.get('display_name', '')),
                package=str(sp.get('package', '')),
                pin_count=int(sp.get('pin_count', 0)),
                named_pin_count=int(sp.get('named_pin_count', 0)),
                availability_status=str(sp.get('availability_status', 'unknown')),
            ),
            candidate_parts=[],
            availability_status=str(c.get('availability_status', 'unknown')),
        ))
    nets = []
    for n in model.get('nets', []):
        nets.append(CircuitNet(
            name=str(n.get('name', '')),
            members=[str(m) for m in n.get('members', [])],
            notes=[str(note) for note in n.get('notes', [])],
        ))
    circuit = CircuitModel(
        schema_version=str(model.get('schema_version', 'circuit-model.v1')),
        request_id=str(model.get('request_id', 'test')),
        project_id=str(model.get('project_id', 'test')),
        topology=str(model.get('topology', 'test')),
        components=components,
        nets=nets,
        calculations=[],
        design_decisions=[],
        risks=[],
    )
    netlist_obj = build_netlist_from_circuit_model(circuit)
    return asdict(netlist_obj)


def run_pipeline(model_path: str, output_dir: str) -> dict[str, Any]:
    model = load_json(model_path)
    project_name = model.get('topology', model.get('request_id', 'kicad_project'))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    os.environ['KICAD_PROJECT_NAME'] = project_name
    os.environ['KICAD_OUTPUT_DIR'] = str(output)
    netlist = build_netlist(model)
    plan: KiCadExecutionPlan = compile_plan(model, netlist)
    plan_file = write_output(plan)

    result = write_project(asdict(plan))

    erc_result = {'enabled': False, 'attempted': False, 'finding_count': 0}
    os.environ['KICAD_SCHEMATIC_FILE'] = str(result['schematic_file'])
    try:
        erc_result = run_erc(emit=False)
    except Exception as exc:
        erc_result = {'error': str(exc)}

    # Optional: run Parts Pipeline
    parts_result: dict[str, Any] = {}
    if is_truthy_env('KICAD_PARTS_PIPELINE', 'false'):
        try:
            parts_result = run_parts_pipeline(
                model,
                output,
                project_name=project_name,
                run_importer=is_truthy_env('KICAD_PARTS_IMPORT', 'false'),
            )
        except Exception as exc:
            parts_result = {"error": str(exc)}

    summary = {
        'project_name': project_name,
        'output_dir': str(output),
        'files': {
            'circuit_model': str(model_path),
            'execution_plan': plan_file,
            'project': result.get('project_file'),
            'schematic': result.get('schematic_file'),
            'summary': result.get('summary_file'),
            'part_lock': parts_result.get('lock_file', ''),
            'part_risk_report': parts_result.get('risk_report_file', ''),
        },
        'counts': {
            'symbols': result.get('symbol_count', 0),
            'nets': result.get('net_count', 0),
        },
        'erc': {
            'success': erc_result.get('success', False),
            'findings': erc_result.get('finding_count', 0),
            'executable': erc_result.get('executable', ''),
        },
        'diagnostics': asdict(plan.diagnostics) if hasattr(plan, 'diagnostics') else {},
    }
    return summary


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python run_pipeline.py <circuit-model.json> <output-dir>')
        sys.exit(1)
    result = run_pipeline(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
