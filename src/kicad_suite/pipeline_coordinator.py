#!/usr/bin/env python3
"""Top-level pipeline orchestration for circuit-model to KiCad output."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .circuit_pipeline import (
    CircuitComponent,
    CircuitModel,
    CircuitNet,
    PartCandidate,
    build_netlist_from_circuit_model,
)
from .compile_kicad_execution_plan import KiCadExecutionPlan, compile_plan, write_output
from .env_utils import is_truthy_env
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import write_project
from .parts.workflow import run_parts_pipeline
from .pipeline_postprocess import apply_postprocess
from .pipeline_summary import build_run_pipeline_summary


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def build_netlist(model: dict[str, Any]) -> dict[str, Any]:
    components = []
    for component in model.get("components", []):
        selected_part = component.get("selected_part", {})
        components.append(
            CircuitComponent(
                ref=str(component.get("ref", "")),
                role=str(component.get("role", "")),
                value=str(component.get("value", "")),
                selected_part=PartCandidate(
                    part_id=str(selected_part.get("part_id", "")),
                    display_name=str(selected_part.get("display_name", "")),
                    package=str(selected_part.get("package", "")),
                    pin_count=int(selected_part.get("pin_count", 0)),
                    named_pin_count=int(selected_part.get("named_pin_count", 0)),
                    availability_status=str(selected_part.get("availability_status", "unknown")),
                ),
                candidate_parts=[],
                availability_status=str(component.get("availability_status", "unknown")),
            )
        )

    nets = []
    for net in model.get("nets", []):
        nets.append(
            CircuitNet(
                name=str(net.get("name", "")),
                members=[str(member) for member in net.get("members", [])],
                notes=[str(note) for note in net.get("notes", [])],
            )
        )

    circuit = CircuitModel(
        schema_version=str(model.get("schema_version", "circuit-model.v1")),
        request_id=str(model.get("request_id", "test")),
        project_id=str(model.get("project_id", "test")),
        topology=str(model.get("topology", "test")),
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
    project_name = model.get("topology", model.get("request_id", "kicad_project"))
    source_project_dir = Path(model_path).resolve().parent
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    os.environ["KICAD_PROJECT_NAME"] = project_name
    os.environ["KICAD_OUTPUT_DIR"] = str(output)
    os.environ["KICAD_SOURCE_PROJECT_DIR"] = str(source_project_dir)
    os.environ["KICAD_TOPOLOGY"] = model.get("topology", "")

    netlist = build_netlist(model)
    plan: KiCadExecutionPlan = compile_plan(model, netlist)
    plan_file = write_output(plan)
    write_result = write_project(asdict(plan))

    schematic_file = Path(write_result.get("schematic_file", ""))
    project_dir = schematic_file.parent if schematic_file.exists() else output / project_name
    postprocess = apply_postprocess(schematic_file, project_dir)

    erc_result: dict[str, Any] = {"enabled": False, "attempted": False, "finding_count": 0}
    os.environ["KICAD_SCHEMATIC_FILE"] = str(write_result.get("schematic_file", ""))
    try:
        erc_result = run_erc(emit=False)
    except Exception as exc:  # noqa: BLE001
        erc_result = {
            "enabled": False,
            "attempted": True,
            "success": False,
            "finding_count": 0,
            "error": str(exc),
        }

    parts_result: dict[str, Any] = {}
    if is_truthy_env("KICAD_PARTS_PIPELINE", "false"):
        try:
            parts_result = run_parts_pipeline(
                model,
                output,
                project_name=project_name,
                run_importer=is_truthy_env("KICAD_PARTS_IMPORT", "false"),
            )
        except Exception as exc:  # noqa: BLE001
            parts_result = {"error": str(exc)}

    summary = build_run_pipeline_summary(
        project_name=project_name,
        output_dir=output,
        model_path=model_path,
        plan_file=plan_file,
        write_result=write_result,
        erc_result=erc_result,
        parts_result=parts_result,
        plan_diagnostics=asdict(plan.diagnostics) if hasattr(plan, "diagnostics") else {},
        postprocess=postprocess,
    )
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_pipeline.py <circuit-model.json> <output-dir>")
        sys.exit(1)
    result = run_pipeline(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
