#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .circuit_pipeline import (
    build_netlist_from_circuit_model,
    build_ngspice_feedback,
    build_spice_netlist_from_netlist,
    execute_ngspice_netlist,
    load_part_catalog,
    render_spice_netlist,
    requirement_from_env,
    synthesize_circuit_model,
)
from .compile_kicad_execution_plan import compile_plan, write_output
from .env_utils import is_truthy_env, env
from .kicad_erc_runner import run as run_kicad_erc
from .kicad_project_writer import write_project
from .parts.workflow import run_parts_pipeline


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write('\n')


def run() -> None:
    spec = requirement_from_env()
    catalog = load_part_catalog()
    model = synthesize_circuit_model(spec, catalog)
    netlist = build_netlist_from_circuit_model(model)
    spice_netlist = build_spice_netlist_from_netlist(netlist)
    ngspice_execution = execute_ngspice_netlist(spice_netlist)
    ngspice_feedback = build_ngspice_feedback(spec, model, spice_netlist, ngspice_execution)

    plan = compile_plan(asdict(model), asdict(netlist))
    plan_file = write_output(plan)
    write_summary = write_project(asdict(plan))
    erc_summary: dict[str, Any] = {
        'enabled': False,
        'attempted': False,
        'warnings': ['KiCad ERC disabled by KICAD_RUN_ERC.'],
    }
    if is_truthy_env('KICAD_RUN_ERC', 'false'):
        os.environ['KICAD_EXECUTION_PLAN_FILE'] = plan_file
        erc_summary = run_kicad_erc(emit=False)

    # Optional: run Parts Pipeline (LCSC resolve → select → part.lock.yaml)
    parts_result: dict[str, Any] = {}
    if is_truthy_env('KICAD_PARTS_PIPELINE', 'false'):
        output_dir = Path(plan.target.output_dir)
        project_name = env('KICAD_PROJECT_NAME', model.topology or spec.request_id)
        try:
            parts_result = run_parts_pipeline(
                asdict(model),
                output_dir,
                project_name=project_name,
                run_importer=is_truthy_env('KICAD_PARTS_IMPORT', 'false'),
            )
        except Exception as parts_error:
            parts_result = {"error": str(parts_error)}

    output_dir = Path(plan.target.output_dir)
    requirement_file = output_dir / 'requirement-spec.json'
    circuit_file = output_dir / 'circuit-model.json'
    netlist_file = output_dir / 'netlist.json'
    spice_file = output_dir / 'spice-netlist.cir'
    ngspice_file = output_dir / 'ngspice-execution.json'
    feedback_file = output_dir / 'ngspice-feedback.json'
    pipeline_file = output_dir / 'text-to-kicad-summary.json'

    write_json(requirement_file, asdict(spec))
    write_json(circuit_file, asdict(model))
    write_json(netlist_file, asdict(netlist))
    spice_file.write_text(render_spice_netlist(spice_netlist), encoding='utf-8')
    write_json(ngspice_file, asdict(ngspice_execution))
    write_json(feedback_file, asdict(ngspice_feedback))

    summary = {
        'schema_version': 'text-to-kicad-summary.v1',
        'request_id': spec.request_id,
        'topology': model.topology,
        'output_files': {
            'requirement': str(requirement_file),
            'circuit_model': str(circuit_file),
            'netlist': str(netlist_file),
            'spice_netlist': str(spice_file),
            'ngspice_execution': str(ngspice_file),
            'ngspice_feedback': str(feedback_file),
            'kicad_execution_plan': plan_file,
            'kicad_project': write_summary.get('project_file'),
            'kicad_schematic': write_summary.get('schematic_file'),
            'kicad_write_summary': write_summary.get('summary_file'),
            'kicad_erc_summary': erc_summary.get('summary_file'),
            'kicad_erc_report': erc_summary.get('output_file'),
            'part_lock': parts_result.get('lock_file', ''),
            'part_risk_report': parts_result.get('risk_report_file', ''),
        },
        'counts': {
            'components': len(model.components),
            'nets': len(netlist.nets),
            'kicad_symbols': len(plan.symbols),
        },
        'diagnostics': {
            'model_risks': model.risks,
            'kicad': asdict(plan.diagnostics),
            'kicad_erc': erc_summary,
            'ngspice': {
                'enabled': ngspice_execution.enabled,
                'attempted': ngspice_execution.attempted,
                'success': ngspice_execution.success,
                'warnings': ngspice_execution.warnings,
                'error': ngspice_execution.error,
                'recommendations': ngspice_feedback.recommendations,
            },
            'parts_pipeline': parts_result.get('summary', parts_result.get('warning', parts_result.get('error', ''))),
        },
    }
    write_json(pipeline_file, summary)
    summary['output_files']['pipeline_summary'] = str(pipeline_file)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:  # noqa: BLE001
        print('Text-to-KiCad pipeline failed.', file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)
