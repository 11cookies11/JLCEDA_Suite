#!/usr/bin/env python3
"""Top-level pipeline orchestration for circuit-model to KiCad output."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .board_generator import generate_board_from_plan
from .circuit_model_io import load_dual_circuit_model, project_root_from_model_path, save_resolved_circuit_model
from .compile_kicad_execution_plan import KiCadExecutionPlan, compile_plan, write_output
from .ir_compiler import build_ir
from .ir_to_kicad import ir_to_kicad
from .env_utils import is_truthy_env
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import write_hierarchical_project, write_project
from .parts.workflow import run_parts_pipeline
from .parts.resolve import apply_selected_parts_to_model
from .pipeline_event_log import append_pipeline_event, pipeline_event_log_path
from .pipeline_postprocess import apply_postprocess, pin_project_libraries
from .pipeline_summary import build_run_pipeline_summary
from .project_resolution import write_project_resolution
from .netlist_builder import build_netlist
from .simulation_planner import write_simulation_artifacts


def _clean_project_output_dir(output: Path, project_name: str) -> Path:
    """Remove stale generated KiCad project files before a fresh pipeline run."""
    project_dir = output / project_name
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def run_pipeline(model_path: str, output_dir: str) -> dict[str, Any]:
    """Run full pipeline: model -> netlist -> plan -> KiCad output -> postprocess -> ERC."""
    model_path_obj = Path(model_path)
    model = load_dual_circuit_model(model_path_obj)
    project_name = model.get("topology", model.get("request_id", "kicad_project"))
    source_project_dir = project_root_from_model_path(model_path_obj.resolve())

    explicit_workspace = os.environ.get("KICAD_WORKSPACE", "")

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

    resolved_model = apply_selected_parts_to_model(model, parts_result.get("selections", [])) if parts_result else model
    save_resolved_circuit_model(model_path_obj, resolved_model)
    _ = build_netlist(resolved_model)

    ir = build_ir(resolved_model)
    append_pipeline_event(
        event_log,
        "ir-compiled",
        "Resolved Hardware IR compiled",
        {"component_count": len(ir.get("components", [])), "net_count": len(ir.get("nets", []))},
    )
    plan: KiCadExecutionPlan = ir_to_kicad(ir)
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
    board_result = generate_board_from_plan(str(plan_file), project_dir)
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

    # Re-render once more after post-processing so the final schematic files are
    # guaranteed to come from the clean renderer, not from any late text patch.
    final_schematic_path = Path(str(write_result.get("schematic_file", "")) or str(schematic_file))
    final_project_dir = final_schematic_path.parent if str(final_schematic_path.parent) != "." else project_dir
    final_project_dir.mkdir(parents=True, exist_ok=True)
    final_write_result = write_hierarchical_project(
        asdict(plan),
        final_project_dir,
        final_schematic_path,
        dsl_sheets=model.get("sheets", []) if isinstance(model, dict) else None,
    )
    postprocess["final_write"] = {
        "project_file": final_write_result.get("project_file", ""),
        "schematic_file": final_write_result.get("schematic_file", ""),
    }

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

    project_resolution_result = write_project_resolution(
        resolved_model,
        project_output_dir / "build",
        parts_result=parts_result,
        generator_name="hwtool",
        generator_version="",
    )
    append_pipeline_event(
        event_log,
        "project-resolution",
        "project resolution manifest written",
        {
            "path": project_resolution_result.get("path", ""),
            "component_count": project_resolution_result.get("manifest", {}).get("summary", {}).get("component_count", 0),
            "verified_count": project_resolution_result.get("manifest", {}).get("summary", {}).get("verified_count", 0),
            "needs_reselection_count": project_resolution_result.get("manifest", {}).get("summary", {}).get("needs_reselection_count", 0),
        },
    )

    # Final overwrite: guarantee the on-disk schematic files are the clean
    # renderer output, after every postprocess/validation step has already run.
    final_write_result = write_project(asdict(plan))
    postprocess["final_write"] = {
        "project_file": final_write_result.get("project_file", ""),
        "schematic_file": final_write_result.get("schematic_file", ""),
    }

    summary = build_run_pipeline_summary(
        project_name=project_name,
        output_dir=output,
        model_path=model_path,
        plan_file=plan_file,
        write_result=write_result,
        erc_result=erc_result,
        parts_result=parts_result,
        project_resolution_result=project_resolution_result,
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
