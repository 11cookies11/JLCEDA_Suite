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


def _inject_jlc_symbols(schematic_path: Path) -> bool:
    """Replace JLC-MCP 2-pin stubs with full symbol definitions from library files."""
    import re
    sym_dir = schematic_path.parent / 'libraries' / 'symbols'
    if not sym_dir.exists():
        return False

    sch = schematic_path.read_text(encoding='utf-8')
    lib_start = sch.find('(lib_symbols')
    if lib_start < 0:
        return False

    depth = 0
    lib_end = lib_start
    for i in range(lib_start, len(sch)):
        if sch[i] == '(':
            depth += 1
        elif sch[i] == ')':
            depth -= 1
            if depth == 0:
                lib_end = i + 1
                break
    lib_section = sch[lib_start:lib_end]

    replaced = 0
    for lib_file in sorted(sym_dir.glob('JLC-MCP-*.kicad_sym')):
        lib_name = lib_file.stem
        lib_content = lib_file.read_text(encoding='utf-8')
        for sym_match in re.finditer(r'\(symbol\s+\"([^\"]+)\"', lib_content):
            sym_name = sym_match.group(1)
            if re.search(r'_\d+_\d+$', sym_name):
                continue
            full_lib_id = lib_name + ':' + sym_name
            if ('(symbol "' + full_lib_id + '"') not in lib_section:
                continue
            s = sym_match.start()
            d2, e = 0, s
            for j in range(s, len(lib_content)):
                if lib_content[j] == '(':
                    d2 += 1
                elif lib_content[j] == ')':
                    d2 -= 1
                    if d2 == 0:
                        e = j + 1
                        break
            full_def = lib_content[s:e]
            derived = []
            pat = re.compile(r'\(symbol\s+\"' + re.escape(sym_name) + r'_\d+_\d+\"')
            for dm in pat.finditer(lib_content):
                ds = dm.start()
                d3, de2 = 0, ds
                for j in range(ds, len(lib_content)):
                    if lib_content[j] == '(':
                        d3 += 1
                    elif lib_content[j] == ')':
                        d3 -= 1
                        if d3 == 0:
                            de2 = j + 1
                            break
                dname = dm.group(0).split('"')[1]
                derived.append((dname, lib_content[ds:de2]))
            si = lib_section.find('(symbol "' + full_lib_id + '"')
            if si < 0:
                continue
            d4, se = 0, si
            for j in range(si, len(lib_section)):
                if lib_section[j] == '(':
                    d4 += 1
                elif lib_section[j] == ')':
                    d4 -= 1
                    if d4 == 0:
                        se = j + 1
                        break
            old_stub = lib_section[si:se]
            new_content = full_def.replace('(symbol "' + sym_name + '"', '(symbol "' + full_lib_id + '"', 1)
            for dname, ddef in derived:
                prefixed = lib_name + ':' + dname
                ddef2 = ddef.replace('(symbol "' + dname + '"', '(symbol "' + prefixed + '"', 1)
                new_content += '\n' + ddef2
            lib_section = lib_section.replace(old_stub, new_content.strip(), 1)
            replaced += 1

    if replaced > 0:
        new_sch = sch[:lib_start] + lib_section + sch[lib_end:]
        schematic_path.write_text(new_sch, encoding='utf-8')
    return replaced > 0


def run_pipeline(model_path: str, output_dir: str) -> dict[str, Any]:
    model = load_json(model_path)
    project_name = model.get('topology', model.get('request_id', 'kicad_project'))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    os.environ['KICAD_PROJECT_NAME'] = project_name
    os.environ['KICAD_OUTPUT_DIR'] = str(output)
    os.environ['KICAD_TOPOLOGY'] = model.get('topology', '')
    netlist = build_netlist(model)
    plan: KiCadExecutionPlan = compile_plan(model, netlist)
    plan_file = write_output(plan)

    result = write_project(asdict(plan))

    # Post-process: inject full JLC-MCP symbol definitions (replace 2-pin stubs)
    schematic_file = Path(result.get('schematic_file', ''))
    symbols_injected = False
    if schematic_file.exists():
        try:
            symbols_injected = _inject_jlc_symbols(schematic_file)
        except Exception:
            pass

    # Auto-register JLC-MCP libraries: fix sym/fp-lib-tables, 3D paths, global registration
    project_dir = schematic_file.parent if schematic_file.exists() else output / project_name
    try:
        import subprocess, sys
        install_script = str(Path(__file__).resolve().parents[2] / 'scripts' / 'install_jlc_mcp_parts.py')
        subprocess.run(
            [sys.executable, install_script, '--project-dir', str(project_dir), '--register-only'],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception:
        pass

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
        'symbols_injected': symbols_injected,
    }
    return summary


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python run_pipeline.py <circuit-model.json> <output-dir>')
        sys.exit(1)
    result = run_pipeline(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
