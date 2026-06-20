#!/usr/bin/env python3
"""Top-level pipeline orchestration for circuit-model to KiCad output."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .adapters.board_generator import generate_board_from_plan
from .domain.core.circuit_model_io import load_dual_circuit_model, project_root_from_model_path, save_resolved_circuit_model
from .domain.core.compile_kicad_execution_plan import KiCadExecutionPlan, write_output
from .shared.env_utils import is_truthy_env
from .domain.core.ir_compiler import build_ir
from .domain.core.ir_to_kicad import ir_to_kicad
from .adapters.kicad_erc_runner import run as run_erc
from .adapters.kicad_project_writer import write_project
from .domain.core.netlist_builder import build_netlist
from .application_services.placement_planner import write_placement_plan
from .domain.core.parts.resolve import apply_selected_parts_to_model
from .domain.core.parts.workflow import run_parts_pipeline
from .orchestration.pipeline_event_log import append_pipeline_event, pipeline_event_log_path
from .orchestration.pipeline_postprocess import apply_postprocess, pin_project_libraries
from .orchestration.pipeline_summary import build_run_pipeline_summary
from .orchestration.project_resolution import write_project_resolution
from .domain.core.simulation_planner import write_simulation_artifacts
from .domain.core.validation.circuit_sanity import run as run_circuit_sanity


@dataclass
class PipelineRunState:
    model_path: Path
    output_dir: Path
    model: dict[str, Any]
    project_name: str
    source_project_dir: Path
    project_output_dir: Path
    event_log: Path
    simulation_result: dict[str, Any] = field(default_factory=dict)
    parts_result: dict[str, Any] = field(default_factory=dict)
    resolved_model: dict[str, Any] = field(default_factory=dict)
    sanity_result: dict[str, Any] = field(default_factory=dict)
    plan: KiCadExecutionPlan | None = None
    plan_file: str = ""
    placement_result: dict[str, Any] = field(default_factory=dict)
    write_result: dict[str, Any] = field(default_factory=dict)
    final_write_result: dict[str, Any] = field(default_factory=dict)
    postprocess: dict[str, Any] = field(default_factory=dict)
    erc_result: dict[str, Any] = field(default_factory=dict)
    project_resolution_result: dict[str, Any] = field(default_factory=dict)


def _clean_project_output_dir(output: Path, project_name: str) -> Path:
    """Remove generated artifacts without touching KiCad history or user files."""
    project_dir = output / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    generated_names = {
        "fp-lib-table",
        "sym-lib-table",
        "kicad-write-summary.json",
        "agent-report.json",
        "jlc-mcp-install-report.json",
    }
    for path in project_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in generated_names or path.suffix in {".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_prl"}:
            path.unlink()
    return project_dir


def _prepare_pipeline_run(model_path: str, output_dir: str) -> PipelineRunState:
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
    os.environ["KICAD_TOPOLOGY"] = str(model.get("topology", ""))
    append_pipeline_event(
        event_log,
        "run_pipeline",
        "pipeline started",
        {
            "model_path": model_path,
            "project_name": project_name,
            "output_dir": str(output),
            "project_output_dir": str(project_output_dir),
        },
    )
    return PipelineRunState(
        model_path=model_path_obj,
        output_dir=output,
        model=model,
        project_name=project_name,
        source_project_dir=source_project_dir,
        project_output_dir=project_output_dir,
        event_log=event_log,
    )


def _run_simulation_stage(state: PipelineRunState) -> None:
    state.simulation_result = write_simulation_artifacts(state.model, state.output_dir)
    state.simulation_result["event_log_file"] = str(state.event_log)
    append_pipeline_event(
        state.event_log,
        "simulation-plan",
        "simulation artifacts generated",
        {
            "profile_file": state.simulation_result.get("profile_file", ""),
            "plan_file": state.simulation_result.get("plan_file", ""),
            "task_plan_file": state.simulation_result.get("task_plan_file", ""),
            "scenario_count": state.simulation_result.get("plan", {}).get("summary", {}).get("scenario_count", 0),
        },
    )


def _run_parts_stage(state: PipelineRunState) -> None:
    if not is_truthy_env("KICAD_PARTS_PIPELINE", "false"):
        state.parts_result = {}
        return
    try:
        state.parts_result = run_parts_pipeline(
            state.model,
            state.output_dir,
            project_name=state.project_name,
            run_importer=is_truthy_env("KICAD_PARTS_IMPORT", "false"),
        )
    except Exception as exc:  # noqa: BLE001
        state.parts_result = {"error": str(exc)}
    append_pipeline_event(
        state.event_log,
        "parts-pipeline",
        "parts pipeline completed",
        {
            "lock_file": state.parts_result.get("lock_file", ""),
            "risk_report_file": state.parts_result.get("risk_report_file", ""),
            "error": state.parts_result.get("error", ""),
        },
    )


def _circuit_sanity_stage(state: PipelineRunState) -> None:
    """Gate: catch obviously-wrong connections before we spend time on IR/KiCad."""
    report = run_circuit_sanity(
        state.resolved_model.get("components", []),
        state.resolved_model.get("nets", []),
    )
    state.sanity_result = {
        "ok": report.ok,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "checks": list(report.checks),
    }
    append_pipeline_event(
        state.event_log,
        "circuit-sanity",
        "circuit sanity check completed",
        {
            "ok": report.ok,
            "error_count": len(report.errors),
            "warning_count": len(report.warnings),
        },
    )
    if not report.ok:
        raise ValueError(
            "Circuit sanity check failed:\n" + "\n".join(f"  - {e}" for e in report.errors)
        )


def _resolve_model_stage(state: PipelineRunState) -> None:
    selections = state.parts_result.get("selections", []) if state.parts_result else []
    state.resolved_model = apply_selected_parts_to_model(state.model, selections) if selections else state.model
    save_resolved_circuit_model(state.model_path, state.resolved_model)
    _ = build_netlist(state.resolved_model)


def _run_placement_stage(state: PipelineRunState) -> None:
    placement_root = state.source_project_dir
    state.placement_result = write_placement_plan(placement_root, state.resolved_model)
    append_pipeline_event(
        state.event_log,
        "placement-planner",
        "pcb placement plan generated",
        {
            "plan_file": state.placement_result.get("plan_file", ""),
            "report_file": state.placement_result.get("report_file", ""),
            "region_count": state.placement_result.get("plan", {}).get("summary", {}).get("region_count", 0),
            "placed_count": state.placement_result.get("plan", {}).get("summary", {}).get("placed_count", 0),
            "unassigned_count": state.placement_result.get("plan", {}).get("summary", {}).get("unassigned_count", 0),
        },
    )


def _build_ir_and_plan_stage(state: PipelineRunState) -> None:
    ir = build_ir(state.resolved_model)
    append_pipeline_event(
        state.event_log,
        "ir-compiled",
        "Resolved Hardware IR compiled",
        {"component_count": len(ir.get("components", [])), "net_count": len(ir.get("nets", []))},
    )
    state.plan = ir_to_kicad(ir)
    state.plan_file = write_output(state.plan)
    state.write_result = write_project(asdict(state.plan))
    append_pipeline_event(
        state.event_log,
        "kicad-generation",
        "KiCad execution plan written",
        {
            "plan_file": state.plan_file,
            "project_file": state.write_result.get("project_file", ""),
            "schematic_file": state.write_result.get("schematic_file", ""),
        },
    )


def _render_and_postprocess_stage(state: PipelineRunState) -> Path:
    schematic_file = Path(state.write_result.get("schematic_file", ""))
    project_dir = schematic_file.parent if schematic_file.exists() else state.output_dir / state.project_name
    state.postprocess = apply_postprocess(schematic_file, project_dir)
    # Log 3D model handling
    sync_status = state.postprocess.get("library_sync", {})
    norm_status = state.postprocess.get("model_path_normalization", {})
    append_pipeline_event(
        state.event_log,
        "kicad-3dmodels",
        "3D model sync and path normalization",
        {
            "models_copied": int(sync_status.get("counts", {}).get("3dmodels", 0) or 0),
            "paths_normalized": int(norm_status.get("updated_references", 0) or 0),
            "unresolved": len(norm_status.get("unresolved_references", []) or []),
        },
    )
    board_result = generate_board_from_plan(
        str(state.plan_file),
        project_dir,
        state.source_project_dir,
    )
    if board_result.get("attempted"):
        state.postprocess["board_generation"] = board_result
        append_pipeline_event(
            state.event_log,
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
        state.write_result["board_file"] = board_result.get("board_file", "")
        state.write_result["board_footprints"] = board_result.get("footprints", 0)
        state.write_result["net_count"] = board_result.get("nets", 0)
    elif board_result.get("attempted"):
        warnings = [str(item) for item in board_result.get("warnings", []) if str(item)]
        state.write_result.setdefault("board_warnings", []).extend(warnings)
        raise ValueError("PCB generation failed validation: " + "; ".join(warnings[:3]))

    state.postprocess["final_normalization"] = apply_postprocess(schematic_file, project_dir)
    return project_dir


def _run_erc_and_resolution_stage(state: PipelineRunState, project_dir: Path) -> None:
    os.environ["KICAD_SCHEMATIC_FILE"] = str(state.write_result.get("schematic_file", ""))
    state.erc_result = {"enabled": False, "attempted": False, "finding_count": 0}
    try:
        state.erc_result = run_erc(emit=False)
    except Exception as exc:  # noqa: BLE001
        state.erc_result = {
            "enabled": False,
            "attempted": True,
            "success": False,
            "finding_count": 0,
            "error": str(exc),
        }
    append_pipeline_event(
        state.event_log,
        "kicad-erc",
        "ERC completed",
        {
            "attempted": state.erc_result.get("attempted", False),
            "success": state.erc_result.get("success", False),
            "summary_file": state.erc_result.get("summary_file", ""),
            "output_file": state.erc_result.get("output_file", ""),
            "warnings": state.erc_result.get("warnings", []),
        },
    )
    state.postprocess["project_library_pins_after_erc"] = pin_project_libraries(project_dir)
    state.project_resolution_result = write_project_resolution(
        state.resolved_model,
        state.project_output_dir / "build",
        parts_result=state.parts_result,
        generator_name="hwtool",
        generator_version="",
    )
    append_pipeline_event(
        state.event_log,
        "project-resolution",
        "project resolution manifest written",
        {
            "path": state.project_resolution_result.get("path", ""),
            "component_count": state.project_resolution_result.get("manifest", {}).get("summary", {}).get("component_count", 0),
            "verified_count": state.project_resolution_result.get("manifest", {}).get("summary", {}).get("verified_count", 0),
            "needs_reselection_count": state.project_resolution_result.get("manifest", {}).get("summary", {}).get("needs_reselection_count", 0),
        },
    )


def _finish_pipeline(state: PipelineRunState) -> dict[str, Any]:
    # Final overwrite: guarantee the on-disk schematic files are the clean
    # renderer output, after every postprocess/validation step has already run.
    state.final_write_result = write_project(asdict(state.plan) if state.plan is not None else {})
    state.postprocess["final_write"] = {
        "project_file": state.final_write_result.get("project_file", ""),
        "schematic_file": state.final_write_result.get("schematic_file", ""),
    }

    summary = build_run_pipeline_summary(
        project_name=state.project_name,
        output_dir=state.output_dir,
        model_path=str(state.model_path),
        plan_file=state.plan_file,
        write_result=state.write_result,
        erc_result=state.erc_result,
        parts_result=state.parts_result,
        project_resolution_result=state.project_resolution_result,
        placement_result=state.placement_result,
        plan_diagnostics=asdict(state.plan.diagnostics) if state.plan is not None and hasattr(state.plan, "diagnostics") else {},
        postprocess=state.postprocess,
        simulation_result=state.simulation_result,
    )
    append_pipeline_event(
        state.event_log,
        "run_pipeline",
        "pipeline finished",
        {
            "summary_file": summary.get("files", {}).get("summary", ""),
            "event_log": str(state.event_log),
        },
    )
    return summary


def run_pipeline(model_path: str, output_dir: str) -> dict[str, Any]:
    """Run full pipeline: model -> netlist -> plan -> KiCad output -> postprocess -> ERC."""
    state = _prepare_pipeline_run(model_path, output_dir)
    _run_simulation_stage(state)
    _run_parts_stage(state)
    _resolve_model_stage(state)
    _circuit_sanity_stage(state)
    _run_placement_stage(state)
    _build_ir_and_plan_stage(state)
    project_dir = _render_and_postprocess_stage(state)
    _run_erc_and_resolution_stage(state, project_dir)
    return _finish_pipeline(state)
