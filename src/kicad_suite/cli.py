#!/usr/bin/env python3
"""Unified command-line entrypoint for KiCad Agent Suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .run_pipeline import run_pipeline
from .server_eda_target import run as run_eda_target
from .server_text_to_kicad import run as run_text_to_kicad
from .artifact_validator import main as validate_artifacts_main
from .compile_kicad_execution_plan import run as run_compile_plan
from .circuit_pipeline import diagnose_ngspice_environment
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import run as run_write_project
from .model_api import CircuitModelRepository, ModelApiService
from .project_state import (
    ProjectState,
    is_mutating_operation,
    is_validate_operation,
    is_build_operation,
)
from .report_system import build_report, format_report, FORMAT_JSON, FORMAT_MARKDOWN, FORMAT_TEXT
from .simulation_planner import (
    build_simulation_plan,
    load_circuit_model,
    load_simulation_profile,
    simulation_plan_to_dict,
)
from .validation.common import load_json


def _print_json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _pipeline_handler(args: argparse.Namespace) -> int:
    return _print_json(run_pipeline(str(args.model_path), str(args.output_dir)))


def _text_to_kicad_handler(args: argparse.Namespace) -> int:
    run_text_to_kicad()
    return 0


def _eda_target_handler(args: argparse.Namespace) -> int:
    run_eda_target()
    return 0


def _compile_plan_handler(args: argparse.Namespace) -> int:
    run_compile_plan()
    return 0


def _write_project_handler(args: argparse.Namespace) -> int:
    run_write_project()
    return 0


def _erc_handler(args: argparse.Namespace) -> int:
    run_erc()
    return 0


def _validate_artifacts_handler(args: argparse.Namespace) -> int:
    forwarded: list[str] = ["--summary", str(args.summary)]
    if args.strict:
        forwarded.append("--strict")
    if args.require_erc:
        forwarded.append("--require-erc")
    if args.json:
        forwarded.append("--json")
    return validate_artifacts_main(forwarded)


def _ngspice_doctor_handler(args: argparse.Namespace) -> int:
    return _print_json(diagnose_ngspice_environment())


def _simulation_plan_handler(args: argparse.Namespace) -> int:
    model = load_circuit_model(args.model_path)
    profile = load_simulation_profile(args.profile_path) if args.profile_path else None
    plan = build_simulation_plan(model, profile)
    return _print_json(simulation_plan_to_dict(plan))


def _model_api_handler(args: argparse.Namespace) -> int:
    request = load_json(args.request_path)
    payload = request.setdefault("payload", {})
    options = request.setdefault("options", {})
    if args.config_path is not None:
        payload.setdefault("config", str(args.config_path))
    if args.dry_run:
        options["dry_run"] = True
    if args.validate_only:
        options["validate_only"] = True
    if args.no_commit:
        options["commit"] = False
    if args.no_strict:
        options["strict"] = False
    if args.no_diff:
        options["return_diff"] = False
    if args.no_snapshot:
        options["return_snapshot"] = False
    service = ModelApiService.from_repository(CircuitModelRepository(args.model_path))
    result = service.handle_dict(request)
    _print_json(result)

    # Update project state after successful API operations.
    if result.get("success") and _should_update_project_state(request):
        operation = request.get("operation", "")
        ps = ProjectState(args.model_path.parent)
        ps.load()
        if is_mutating_operation(operation):
            ps.mark_dirty(reason=f"api:{operation}")
        elif is_validate_operation(operation):
            diag = result.get("diagnostics", {})
            if diag.get("ok"):
                ps.mark_valid({"errors": diag.get("errors", []), "warnings": diag.get("warnings", [])})
            else:
                ps.mark_invalid({"errors": diag.get("errors", []), "warnings": diag.get("warnings", [])})
        elif is_build_operation(operation):
            ps.mark_built({"operation": operation})
    return 0 if result.get("success") else 1


def _should_update_project_state(request: dict[str, Any]) -> bool:
    """Return True only when an API request reflects committed project state."""
    options = request.get("options", {})
    if not isinstance(options, dict):
        return True
    if options.get("dry_run") or options.get("validate_only"):
        return False
    if options.get("commit") is False:
        return False
    return True


def _resolve_project_path(args: argparse.Namespace) -> Path:
    """Resolve project path from --path flag, defaulting to CWD."""
    path = args.path if getattr(args, "path", None) else Path.cwd()
    return Path(path).resolve()


def _project_status_handler(args: argparse.Namespace) -> int:
    ps = ProjectState(_resolve_project_path(args))
    ps.load()
    status = ps.get_status()
    stale = ps.is_stale()
    _print_json({"status": status, "stale": stale})
    return 0


def _project_inspect_handler(args: argparse.Namespace) -> int:
    ps = ProjectState(_resolve_project_path(args))
    ps.load()
    payload = {
        "project": ps.state.get("project", {}),
        "status": ps.get_status(),
        "stale": ps.is_stale(),
        "summary": ps.get_summary(),
        "dsl": ps.state.get("dsl", {}),
        "build": ps.state.get("build", {}),
    }
    return _print_json(payload)


def _project_explain_handler(args: argparse.Namespace) -> int:
    ps = ProjectState(_resolve_project_path(args))
    ps.load()
    print(ps.get_explain())
    return 0


def _project_report_handler(args: argparse.Namespace) -> int:
    project_path = _resolve_project_path(args)
    report = build_report(project_path)
    fmt = args.format if getattr(args, "format", None) else FORMAT_JSON
    output = format_report(report, fmt)
    print(output)
    return 0


def _project_history_handler(args: argparse.Namespace) -> int:
    ps = ProjectState(_resolve_project_path(args))
    limit = args.limit if getattr(args, "limit", None) else 50
    return _print_json(ps.get_history(limit=limit))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kas", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    pipeline = subparsers.add_parser("pipeline", help="Run the circuit-model to KiCad pipeline.")
    pipeline.add_argument("model_path", type=Path)
    pipeline.add_argument("output_dir", type=Path)
    pipeline.set_defaults(handler=_pipeline_handler)

    eda_target = subparsers.add_parser("eda-target", help="Run the EDA target pipeline.")
    eda_target.set_defaults(handler=_eda_target_handler)

    text_to_kicad = subparsers.add_parser("text-to-kicad", help="Run the text-to-KiCad pipeline.")
    text_to_kicad.set_defaults(handler=_text_to_kicad_handler)

    compile_plan = subparsers.add_parser("compile-plan", help="Compile a KiCad execution plan from env inputs.")
    compile_plan.set_defaults(handler=_compile_plan_handler)

    write_project = subparsers.add_parser("write-project", help="Write KiCad project files from the execution plan.")
    write_project.set_defaults(handler=_write_project_handler)

    erc = subparsers.add_parser("erc", help="Run KiCad ERC on the resolved schematic.")
    erc.set_defaults(handler=_erc_handler)

    validate_artifacts = subparsers.add_parser(
        "validate-artifacts",
        help="Validate generated artifacts for consistency.",
    )
    validate_artifacts.add_argument("--summary", type=Path, required=True)
    validate_artifacts.add_argument("--strict", action="store_true")
    validate_artifacts.add_argument("--require-erc", action="store_true")
    validate_artifacts.add_argument("--json", action="store_true")
    validate_artifacts.set_defaults(handler=_validate_artifacts_handler)

    ngspice_doctor = subparsers.add_parser("ngspice-doctor", help="Inspect ngspice availability and configuration.")
    ngspice_doctor.set_defaults(handler=_ngspice_doctor_handler)

    simulation_plan = subparsers.add_parser("simulation-plan", help="Generate a simulation plan from a circuit model.")
    simulation_plan.add_argument("model_path", type=Path)
    simulation_plan.add_argument("--profile-path", type=Path, default=None)
    simulation_plan.set_defaults(handler=_simulation_plan_handler)

    model_api = subparsers.add_parser(
        "model-api",
        help="Apply a DSL API request to a circuit-model JSON file.",
    )
    model_api.add_argument("request_path", type=Path)
    model_api.add_argument("--model", dest="model_path", type=Path, required=True)
    model_api.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    model_api.add_argument("--dry-run", action="store_true")
    model_api.add_argument("--validate-only", action="store_true")
    model_api.add_argument("--no-commit", action="store_true")
    model_api.add_argument("--no-strict", action="store_true")
    model_api.add_argument("--no-diff", action="store_true")
    model_api.add_argument("--no-snapshot", action="store_true")
    model_api.set_defaults(handler=_model_api_handler)

    # kas project
    project_cmd = subparsers.add_parser("project", help="Project state management.")
    project_subs = project_cmd.add_subparsers(dest="project_action")

    p_status = project_subs.add_parser("status", help="Show current project status.")
    p_status.add_argument("--path", type=Path, default=None)
    p_status.set_defaults(handler=_project_status_handler)

    p_inspect = project_subs.add_parser("inspect", help="Structured project summary.")
    p_inspect.add_argument("--path", type=Path, default=None)
    p_inspect.set_defaults(handler=_project_inspect_handler)

    p_explain = project_subs.add_parser("explain", help="Natural-language project description.")
    p_explain.add_argument("--path", type=Path, default=None)
    p_explain.set_defaults(handler=_project_explain_handler)

    p_report = project_subs.add_parser("report", help="Unified project report.")
    p_report.add_argument("--path", type=Path, default=None)
    p_report.add_argument("--format", choices=["json", "markdown", "text"], default="json")
    p_report.set_defaults(handler=_project_report_handler)

    p_history = project_subs.add_parser("history", help="Show operation history.")
    p_history.add_argument("--path", type=Path, default=None)
    p_history.add_argument("-n", "--limit", type=int, default=50)
    p_history.set_defaults(handler=_project_history_handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
