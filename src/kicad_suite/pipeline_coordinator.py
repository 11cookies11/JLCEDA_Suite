#!/usr/bin/env python3
"""Top-level pipeline orchestration for circuit-model to KiCad output."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapters.kicad_cli import resolve_kicad_cli
from .compile_kicad_execution_plan import KiCadExecutionPlan, compile_plan, normalize_net_kind, write_output
from .env_utils import is_truthy_env
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import write_project
from .parts.workflow import run_parts_pipeline
from .pipeline_event_log import append_pipeline_event, pipeline_event_log_path
from .pipeline_postprocess import apply_postprocess, pin_project_libraries
from .pipeline_summary import build_run_pipeline_summary
from .simulation_planner import write_simulation_artifacts


def _clean_project_output_dir(output: Path, project_name: str) -> Path:
    """Remove stale generated KiCad project files before a fresh pipeline run."""
    project_dir = output / project_name
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def _resolve_kicad_python() -> str:
    explicit = os.environ.get("KICAD_PYTHON_BIN", "")
    if explicit:
        return explicit
    cli = resolve_kicad_cli()
    if cli:
        candidate = Path(cli).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return ""


def _generate_board_from_plan(plan_file: str, project_dir: Path) -> dict[str, Any]:
    if not is_truthy_env("KICAD_GENERATE_PCB", "true"):
        return {"attempted": False, "enabled": False}
    python_bin = _resolve_kicad_python()
    if not python_bin:
        return {
            "attempted": True,
            "success": False,
            "warnings": ["KiCad Python was not found; PCB was not generated."],
        }
    script = Path(__file__).resolve().parents[2] / "scripts" / "generate_pcb_from_plan.py"
    board_file = project_dir / f"{project_dir.name}.kicad_pcb"
    process = subprocess.run(
        [python_bin, str(script), plan_file, str(board_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(process.stdout)
    except Exception:
        payload = {}
    warnings: list[str] = []
    if process.stderr:
        warnings.append(process.stderr.strip())
    if process.returncode != 0:
        warnings.append(process.stdout.strip() or "PCB generation failed.")
    if payload.get("skipped"):
        warnings.extend(str(item) for item in payload.get("skipped", []))
    return {
        "attempted": True,
        "success": process.returncode == 0,
        "return_code": process.returncode,
        "python": python_bin,
        "script": str(script),
        "board_file": payload.get("board", str(board_file)),
        "footprints": int(payload.get("footprints", 0) or 0),
        "nets": int(payload.get("nets", 0) or 0),
        "warnings": warnings,
    }


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def build_netlist(model: dict[str, Any]) -> dict[str, Any]:
    """Build a netlist dict from the circuit model's nets and components."""
    from collections import defaultdict

    request_id = str(model.get("request_id", ""))
    project_id = str(model.get("project_id", request_id))
    pin_by_ref: dict[str, list[dict[str, str]]] = defaultdict(list)
    for net in model.get("nets", []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get("name", ""))
        for member in net.get("members", []):
            member_str = str(member).strip()
            if "." in member_str:
                ref, pin = member_str.rsplit(".", 1)
                if ref and pin:
                    pin_by_ref[ref].append({"pin": pin, "pin_name": "", "net": net_name})

    components: list[dict[str, Any]] = []
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", "")).strip()
        if not ref:
            continue
        selected_part = component.get("selected_part", {})
        part = selected_part if isinstance(selected_part, dict) else {}
        components.append(
            {
                "ref": ref,
                "role": str(component.get("role", "")),
                "value": str(component.get("value", "")),
                "part": {
                    "part_id": str(part.get("part_id", "")),
                    "display_name": str(part.get("display_name", "")),
                    "library_uuid": str(part.get("library_uuid", "")),
                    "symbol_uuid": str(part.get("symbol_uuid", "")),
                    "pin_count": int(part.get("pin_count", 0) or 0),
                    "named_pin_count": int(part.get("named_pin_count", 0) or 0),
                },
                "pins": sorted(pin_by_ref.get(ref, []), key=lambda item: item.get("pin", "")),
                "availability_status": str(component.get("availability_status", "unknown")),
            }
        )

    nets: list[dict[str, Any]] = []
    for net in model.get("nets", []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get("name", "")).strip()
        if not net_name:
            continue
        nets.append(
            {
                "name": net_name,
                "kind": str(net.get("kind", normalize_net_kind(net_name))),
                "members": [str(member) for member in net.get("members", [])],
            }
        )

    return {
        "schema_version": "netlist.v1",
        "request_id": request_id,
        "project_id": project_id,
        "source_model": {
            "schema_version": str(model.get("schema_version", "")),
            "request_id": request_id,
        },
        "components": components,
        "nets": nets,
    }


def run_pipeline(model_path: str, output_dir: str) -> dict[str, Any]:
    """Run full pipeline: model -> netlist -> plan -> KiCad output -> postprocess -> ERC."""
    model = load_json(model_path)
    project_name = model.get("topology", model.get("request_id", "kicad_project"))
    source_project_dir = Path(model_path).resolve().parent

    explicit_workspace = os.environ.get("KICAD_WORKSPACE", "")
    workspace = explicit_workspace
    if not workspace:
        candidate = source_project_dir
        if (candidate / "libraries" / "symbols").exists():
            workspace = str(candidate)

    output = Path(output_dir)
    if not explicit_workspace:
        os.environ.pop("KICAD_WORKSPACE", None)

    output.mkdir(parents=True, exist_ok=True)
    project_output_dir = _clean_project_output_dir(output, project_name)
    event_log = pipeline_event_log_path(output)
    os.environ["KICAD_PROJECT_NAME"] = project_name
    os.environ["KICAD_OUTPUT_DIR"] = str(output)
    os.environ["KICAD_SOURCE_PROJECT_DIR"] = str(source_project_dir)
    os.environ["KICAD_TOPOLOGY"] = model.get("topology", "")
    append_pipeline_event(
        event_log,
        "run_pipeline",
        "pipeline started",
        {"model_path": model_path, "project_name": project_name, "output_dir": str(output), "project_output_dir": str(project_output_dir)},
    )

    netlist = build_netlist(model)
    simulation_result = write_simulation_artifacts(model, output)
    simulation_result["event_log_file"] = str(event_log)
    append_pipeline_event(
        event_log,
        "simulation-plan",
        "simulation artifacts generated",
        {
            "profile_file": simulation_result.get("profile_file", ""),
            "plan_file": simulation_result.get("plan_file", ""),
            "task_plan_file": simulation_result.get("task_plan_file", ""),
            "scenario_count": simulation_result.get("plan", {}).get("summary", {}).get("scenario_count", 0),
        },
    )
    plan: KiCadExecutionPlan = compile_plan(model, netlist)
    plan_file = write_output(plan)
    write_result = write_project(asdict(plan))
    append_pipeline_event(
        event_log,
        "kicad-generation",
        "KiCad execution plan written",
        {
            "plan_file": plan_file,
            "project_file": write_result.get("project_file", ""),
            "schematic_file": write_result.get("schematic_file", ""),
        },
    )

    schematic_file = Path(write_result.get("schematic_file", ""))
    project_dir = schematic_file.parent if schematic_file.exists() else output / project_name
    postprocess = apply_postprocess(schematic_file, project_dir)
    board_result = _generate_board_from_plan(str(plan_file), project_dir)
    if board_result.get("attempted"):
        postprocess["board_generation"] = board_result
        append_pipeline_event(
            event_log,
            "kicad-board",
            "board generation completed",
            {
                "attempted": board_result.get("attempted", False),
                "success": board_result.get("success", False),
                "board_file": board_result.get("board_file", ""),
                "warnings": board_result.get("warnings", []),
            },
        )
    if board_result.get("success"):
        write_result["board_file"] = board_result.get("board_file", "")
        write_result["board_footprints"] = board_result.get("footprints", 0)
        write_result["net_count"] = board_result.get("nets", 0)
    elif board_result.get("warnings"):
        write_result.setdefault("board_warnings", []).extend(board_result.get("warnings", []))

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
    append_pipeline_event(
        event_log,
        "kicad-erc",
        "ERC completed",
        {
            "attempted": erc_result.get("attempted", False),
            "success": erc_result.get("success", False),
            "summary_file": erc_result.get("summary_file", ""),
            "output_file": erc_result.get("output_file", ""),
            "warnings": erc_result.get("warnings", []),
        },
    )
    postprocess["project_library_pins_after_erc"] = pin_project_libraries(project_dir)

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
        append_pipeline_event(
            event_log,
            "parts-pipeline",
            "parts pipeline completed",
            {
                "lock_file": parts_result.get("lock_file", ""),
                "risk_report_file": parts_result.get("risk_report_file", ""),
                "error": parts_result.get("error", ""),
            },
        )

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
        simulation_result=simulation_result,
    )
    append_pipeline_event(
        event_log,
        "run_pipeline",
        "pipeline finished",
        {
            "summary_file": summary.get("files", {}).get("summary", ""),
            "event_log": str(event_log),
        },
    )
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_pipeline.py <circuit-model.json> <output-dir>")
        sys.exit(1)
    result = run_pipeline(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
