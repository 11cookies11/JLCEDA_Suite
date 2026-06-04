#!/usr/bin/env python3
"""Unified command-line entrypoint for KiCad Agent Suite."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline_coordinator import run_pipeline
from .server_text_to_kicad import run as run_text_to_kicad
from .artifact_validator import main as validate_artifacts_main
from .compile_kicad_execution_plan import run as run_compile_plan
from .circuit_pipeline import diagnose_ngspice_environment
from .circuit_model_io import resolve_model_paths
from .ir_compiler import build_ir
from .ir_validator import validate_ir
from .pin_manager import PinManager
from . import jlc_api
from .jlc_api import search as jlc_search
from .jlc_installer import install_by_lcsc_id, search_and_install, resolve_missing_symbols
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
from .env_utils import repo_root


def _print_json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _agent_request_id(operation: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"agent-{operation}-{stamp}"


def _load_payload_args(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if getattr(args, "payload_file", None) is not None:
        payload_from_file = load_json(args.payload_file)
        if not isinstance(payload_from_file, dict):
            raise ValueError("agent payload file must contain a JSON object.")
        payload.update(payload_from_file)
    if getattr(args, "payload_json", None):
        payload_from_json = json.loads(args.payload_json)
        if not isinstance(payload_from_json, dict):
            raise ValueError("agent payload JSON must be an object.")
        payload.update(payload_from_json)
    if getattr(args, "config_path", None) is not None:
        payload.setdefault("config", str(args.config_path))
    return payload


def _agent_project_path(args: argparse.Namespace) -> Path:
    return Path(args.project_path).resolve()


def _agent_model_path(args: argparse.Namespace) -> Path:
    model = getattr(args, "model_path", None)
    if model is not None:
        return Path(model).resolve()
    return _agent_project_path(args) / "source" / "circuit-model.source.json"


def _agent_model_metadata(model_path: Path, project_path: Path) -> tuple[str, str]:
    source_path, resolved_path = resolve_model_paths(model_path)
    if source_path.exists() or resolved_path.exists() or model_path.exists():
        model = load_circuit_model(model_path)
        if isinstance(model, dict):
            project_id = str(model.get("project_id", "") or project_path.name)
            topology = str(model.get("topology", "") or project_id.replace("-", "_"))
            return project_id, topology
    project_id = project_path.name
    return project_id, project_id.replace("-", "_")


def _agent_options_from_args(args: argparse.Namespace) -> dict[str, bool]:
    options: dict[str, bool] = {}
    if getattr(args, "dry_run", False):
        options["dry_run"] = True
    if getattr(args, "validate_only", False):
        options["validate_only"] = True
    if getattr(args, "no_commit", False):
        options["commit"] = False
    if getattr(args, "no_strict", False):
        options["strict"] = False
    if getattr(args, "no_diff", False):
        options["return_diff"] = False
    if getattr(args, "no_snapshot", False):
        options["return_snapshot"] = False
    return options


def _agent_request(
    *,
    operation: str,
    project_id: str,
    topology: str,
    payload: dict[str, Any],
    request_id: str = "",
    options: dict[str, bool] | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": "dsl-api-request.v1",
        "request_id": request_id or _agent_request_id(operation),
        "project_id": project_id,
        "topology": topology,
        "operation": operation,
        "payload": payload,
    }
    if options:
        request["options"] = options
    return request


def _update_project_state_from_request(request: dict[str, Any], result: dict[str, Any], project_path: Path) -> None:
    if not result.get("success") or not _should_update_project_state(request):
        return
    operation = request.get("operation", "")
    ps = ProjectState(project_path)
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
        build_result = result.get("result", {})
        kicad_project = build_result.get("kicad_project")
        op_data: dict[str, Any] = {"operation": operation}
        if isinstance(kicad_project, dict):
            op_data["symbols"] = kicad_project.get("symbol_count", 0)
            op_data["nets"] = kicad_project.get("net_count", 0)
            op_data["sheets"] = kicad_project.get("hierarchical_sheets", {}).get("sheet_count", 0)
            op_data["outputs"] = {
                "project": kicad_project.get("project_file", ""),
                "schematic": kicad_project.get("schematic_file", ""),
            }
            # Footprint + symbol warnings from build diagnostics
            diags = kicad_project.get("diagnostics", {})
            unsupported = diags.get("unsupported", []) if isinstance(diags, dict) else []
            if unsupported:
                op_data["build_warnings"] = unsupported
        erc = build_result.get("erc")
        if erc:
            op_data["erc_findings"] = erc.get("finding_count", 0)
            op_data["erc_violations"] = erc.get("violations", [])
        timing = build_result.get("timing")
        if timing:
            op_data["build_sec"] = timing.get("build_sec", 0)
            op_data["erc_sec"] = timing.get("erc_sec", 0)
        report = build_result.get("report")
        if report:
            op_data["report_status"] = report.get("overall_status", "?")
            op_data["report_path"] = report.get("path", "")
        ps.mark_built({"output_dir": str(project_path / "output")}, op_data=op_data)


def _pipeline_handler(args: argparse.Namespace) -> int:
    return _print_json(run_pipeline(str(args.model_path), str(args.output_dir)))


def _text_to_kicad_handler(args: argparse.Namespace) -> int:
    run_text_to_kicad()
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

    _update_project_state_from_request(request, result, args.model_path.parent)
    return 0 if result.get("success") else 1


def _agent_manifest_handler(args: argparse.Namespace) -> int:
    payload = {
        "schema_version": "kas-agent-entry.v1",
        "commands": {
            "status": "Return machine-readable lifecycle state.",
            "inspect": "Return project, model, build, and summary details.",
            "explain": "Return a compact project explanation for an agent.",
            "build-ir": "Compile source/circuit-model.source.json into build/ir.v1.json.",
            "validate-ir": "Compile and validate Hardware IR.",
            "rule-check": "Run project readiness checks.",
            "build-kicad-plan": "Compile the KiCad execution plan from the validated IR.",
            "build-kicad": "Generate KiCad project files from the execution plan.",
            "report": "Write build/report.json and optionally build/report.md.",
            "doctor": "Check toolchain environment and project layout.",
            "history": "Return recent project operations.",
            "run": "Apply one DSL Model API operation to a project source model.",
            "create": "Create a hardware project from an optional source model.",
            "export-kicad": "Export the current project model to a KiCad project.",
            "patch": "Apply a JSON patch to the circuit model.",
            "pins": "Pin resource management (free, assign, check).",
            "self-test": "Run the test suite and return structured results.",
            "jlc": "LCSC component search, preview (info), and download (download).",
            "resolve-symbols": "Auto-resolve missing symbols via JLC search (--timeout 120).",
            "manifest": "Describe this agent-facing command surface.",
        },
        "project_files": {
            "model_source": "source/circuit-model.source.json",
            "model_resolved": "build/circuit-model.resolved.json",
            "state": "project.state.json",
            "operation_log": "logs/operations.jsonl",
            "ir": "build/ir.v1.json",
            "ir_validation": "build/ir-validation.json",
            "rule_check": "build/rule-check.json",
            "agent_report": "build/report.json",
            "human_report": "build/report.md",
            "default_output": "output/",
        },
        "request_schema": "dsl-api-request.v1",
        "result_schema": "dsl-api-result.v1",
    }
    return _print_json(payload)


def _agent_status_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    ps = ProjectState(project_path)
    ps.load()
    return _print_json({
        "ok": True,
        "stage": "status",
        "status": ps.get_status(),
        "stale": ps.is_stale(),
        "project": ps.state.get("project", {}),
        "summary": ps.get_summary(),
    })


def _agent_inspect_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    ps = ProjectState(project_path)
    ps.load()
    model_path = _agent_model_path(args)
    source_path, resolved_path = resolve_model_paths(model_path)
    model = load_circuit_model(model_path) if source_path.exists() or resolved_path.exists() or model_path.exists() else {}
    return _print_json({
        "ok": True,
        "stage": "inspect",
        "project": ps.state.get("project", {}),
        "status": ps.get_status(),
        "stale": ps.is_stale(),
        "summary": ps.get_summary(),
        "dsl": ps.state.get("dsl", {}),
        "build": ps.state.get("build", {}),
        "source": {
            "model": str(model_path),
            "component_count": len(model.get("components", [])) if isinstance(model, dict) else 0,
            "net_count": len(model.get("nets", [])) if isinstance(model, dict) else 0,
        },
    })


def _agent_explain_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    ps = ProjectState(project_path)
    ps.load()
    return _print_json({
        "ok": True,
        "stage": "explain",
        "explanation": ps.get_explain(),
        "suggested_next": _agent_suggest_next(ps),
    })


def _agent_suggest_next(ps: ProjectState) -> list[str]:
    status = ps.get_status()
    if status in {"INIT", "DIRTY", "STALE"}:
        return ["build-ir", "validate-ir"]
    if status == "INVALID":
        return ["report", "fix diagnostics", "validate-ir"]
    if status == "VALID":
        return ["build-kicad", "report"]
    if status == "BUILD_FAILED":
        return ["report", "fix diagnostics", "build-kicad"]
    return ["report"]


def _agent_build_ir_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    model = load_circuit_model(model_path)
    ir = build_ir(model)
    output = Path(args.output).resolve() if args.output else project_path / "build" / "ir.v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ps = ProjectState(project_path)
    ps.load()
    ps.mark_dirty(reason="agent:build-ir")
    return _print_json({
        "ok": True,
        "stage": "build_ir",
        "output": str(output),
        "summary": {
            "components": len(ir.get("components", [])),
            "nets": len(ir.get("nets", [])),
        },
    })


def _agent_validate_ir_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    model = load_circuit_model(model_path)
    ir = build_ir(model)
    report = validate_ir(ir)
    output = Path(args.output).resolve() if args.output else project_path / "build" / "ir-validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _agent_validation_payload("ir_validation", report.ok, report.errors, report.warnings, report.stats)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ps = ProjectState(project_path)
    ps.load()
    if report.ok:
        ps.mark_valid({"errors": report.errors, "warnings": report.warnings})
    else:
        ps.mark_invalid({"errors": report.errors, "warnings": report.warnings})
    return _print_json(payload | {"output": str(output)})


# -- diagnostic message parser -------------------------------------------------
# Converts free-text validator errors into structured diagnostics with specific
# error codes, locations, and actionable suggestions so AI agents can
# programmatically fix issues without guessing.

import re as _re

# Patterns: (regex, error_code, location_extractor_fn, suggestion_builder_fn)
_DIAGNOSTIC_PATTERNS: list[tuple[Any, str, Any, Any]] = []


def _pat(regex: str, code: str, loc_fn: Any = None, sug_fn: Any = None) -> None:
    _DIAGNOSTIC_PATTERNS.append((_re.compile(regex), code, loc_fn, sug_fn))


def _loc_group(n: int | str = 1):
    """Extract location from regex group *n*."""
    return lambda m: m.group(n)

def _sug_cmd(action: str, **defaults):
    """Build a suggestion with an agent CLI command."""
    def _build(m: _re.Match) -> dict[str, Any]:
        cmd_parts = [action]
        payload: dict[str, Any] = {}
        for k, v in defaults.items():
            val = str(v).format(**m.groupdict()) if isinstance(v, str) else v
            payload[k] = val
        return {"action": "agent run", "operation": action, "payload": payload}
    return _build


# --- schema / structural ---
_pat(r"IR[.\s]schema_version must be '([^']+)', got '([^']+)'",
     "SCHEMA_VERSION_MISMATCH",
     _loc_group(1),
     lambda m: {"action": "agent run", "operation": "set_schema_version",
                 "payload": {"schema_version": m.group(1)}})
_pat(r"IR\.(?P<key>\w+) is missing or empty",
     "MISSING_REQUIRED_FIELD",
     _loc_group("key"),
     lambda m: {"action": "agent run", "operation": "set_metadata",
                 "payload": {"key": m.group("key")}})
_pat(r"IR\.(?P<key>\w+) must be a list",
     "INVALID_FIELD_TYPE",
     _loc_group("key"))

# --- components ---
_pat(r"IR\.components\[(?P<idx>\d+)\] missing ref",
     "MISSING_COMPONENT_REF",
     _loc_group("idx"))
_pat(r"IR\.components: duplicate ref '(?P<ref>[^']+)'",
     "DUPLICATE_COMPONENT_REF",
     _loc_group("ref"),
     lambda m: {"action": "agent run", "operation": "update_component",
                 "payload": {"ref": m.group("ref")},
                 "hint": "Rename or remove one of the duplicate component refs."})
_pat(r"IR\.components\[(?P<ref>[^]]+)\] has no pins",
     "COMPONENT_NO_PINS",
     _loc_group("ref"),
     lambda m: {"action": "agent run", "operation": "update_component",
                 "payload": {"ref": m.group("ref"), "patch": {"pins": []}},
                 "hint": "Add pin definitions or select a part with pin data."})

# --- pins ---
_pat(r"IR\.components\[(?P<ref>[^]]+)\]\.pins\[(?P<idx>\d+)\] missing number",
     "MISSING_PIN_NUMBER",
     _loc_group("ref"))
_pat(r"IR\.components\[(?P<ref>[^]]+)\]\.pins: duplicate pin number '(?P<pin>[^']+)'",
     "DUPLICATE_PIN_NUMBER",
     _loc_group("ref"),
     lambda m: {"action": "agent run", "operation": "update_pinmap",
                 "payload": {"ref": m.group("ref"), "pin": m.group("pin")},
                 "hint": f"Remove duplicate pin {m.group('pin')} on {m.group('ref')}."})
_pat(r"IR\.components\[(?P<ref>[^]]+)\]\.pins\[(?P<pin>[^]]+)\] unknown source '(?P<source>[^']+)'",
     "UNKNOWN_PIN_SOURCE",
     _loc_group("ref"))

# --- nets ---
_pat(r"IR\.nets\[(?P<idx>\d+)\] missing name",
     "MISSING_NET_NAME",
     _loc_group("idx"))
_pat(r"IR\.nets: duplicate net name '(?P<name>[^']+)'",
     "DUPLICATE_NET_NAME",
     _loc_group("name"),
     lambda m: {"action": "agent run", "operation": "merge_nets",
                 "payload": {"source": m.group("name")},
                 "hint": f"Merge duplicate net '{m.group('name')}' with the original."})
_pat(r"IR\.nets\[(?P<name>[^]]+)\] has no members \(floating\)",
     "FLOATING_NET",
     _loc_group("name"),
     lambda m: {"action": "agent run", "operation": "connect_member",
                 "payload": {"net": m.group("name")},
                 "hint": f"Connect net '{m.group('name')}' to component pins."})
_pat(r"IR\.nets\[(?P<name>[^]]+)\]\.members\[(?P<idx>\d+)\] '(?P<member>[^']+)' must be ref\.pin format",
     "INVALID_NET_MEMBER_FORMAT",
     _loc_group("name"),
     lambda m: {"action": "agent run", "operation": "disconnect_member",
                 "payload": {"net": m.group("name"), "member": m.group("member")},
                 "hint": f"Fix format: use 'REF.PIN' (e.g. 'U1.3') instead of '{m.group('member')}'."})
_pat(r"IR\.nets\[(?P<name>[^]]+)\] unknown kind '(?P<kind>[^']+)'",
     "UNKNOWN_NET_KIND",
     _loc_group("name"),
     lambda m: {"action": "agent run", "operation": "set_net_kind",
                 "payload": {"name": m.group("name"), "value": "signal"},
                 "hint": f"Change net kind from '{m.group('kind')}' to 'signal', 'power', or 'ground'."})

# --- reference integrity ---
_pat(r"IR\.nets\[(?P<net>[^]]+)\] member '(?P<member>[^']+)' references missing component '(?P<ref>[^']+)'",
     "MISSING_COMPONENT_REFERENCE",
     _loc_group("net"),
     lambda m: {"action": "agent run", "operation": "add_component",
                 "payload": {"ref": m.group("ref")},
                 "hint": f"Add component '{m.group('ref')}' or fix the reference in net '{m.group('net')}'."})
_pat(r"IR\.sheets\[(?P<sheet>[^]]+)\]\.components references missing '(?P<ref>[^']+)'",
     "MISSING_SHEET_COMPONENT",
     _loc_group("sheet"),
     lambda m: {"action": "agent run", "operation": "add_component",
                 "payload": {"ref": m.group("ref")},
                 "hint": f"Add component '{m.group('ref')}' or remove it from sheet '{m.group('sheet')}'."})
_pat(r"IR\.sheets\[(?P<sheet>[^]]+)\]\.(?P<direction>inputs|outputs|nets) references missing net '(?P<net>[^']+)'",
     "MISSING_SHEET_NET",
     _loc_group("sheet"),
     lambda m: {"action": "agent run", "operation": "add_net",
                 "payload": {"name": m.group("net")},
                 "hint": f"Add net '{m.group('net')}' or remove it from sheet '{m.group('sheet')}' {m.group('direction')}."})
_pat(r"IR\.pinmap references missing component '(?P<ref>[^']+)'",
     "MISSING_PINMAP_COMPONENT",
     _loc_group("ref"),
     lambda m: {"action": "agent run", "operation": "add_component",
                 "payload": {"ref": m.group("ref")},
                 "hint": f"Add component '{m.group('ref')}' or remove it from pinmap."})
_pat(r"IR\.pinmap\[(?P<ref>[^]]+)\]\[(?P<pin>[^]]+)\]\.net '(?P<net>[^']+)' not found in nets",
     "PINMAP_NET_NOT_FOUND",
     _loc_group("ref"),
     lambda m: {"action": "agent run", "operation": "add_net",
                 "payload": {"name": m.group("net")},
                 "hint": f"Add net '{m.group('net')}' or fix pinmap[{m.group('ref')}][{m.group('pin')}]."})
_pat(r"IR\.interfaces\[(?P<name>[^]]+)\]\.connector_ref '(?P<ref>[^']+)' not found",
     "MISSING_INTERFACE_CONNECTOR",
     _loc_group("name"),
     lambda m: {"action": "agent run", "operation": "add_component",
                 "payload": {"ref": m.group("ref")},
                 "hint": f"Add connector component '{m.group('ref')}' for interface '{m.group('name')}'."})
_pat(r"IR\.interfaces\[(?P<name>[^]]+)\]\.nets references missing net '(?P<net>[^']+)'",
     "MISSING_INTERFACE_NET",
     _loc_group("name"),
     lambda m: {"action": "agent run", "operation": "add_net",
                 "payload": {"name": m.group("net")},
                 "hint": f"Add net '{m.group('net')}' or remove it from interface '{m.group('name')}'."})

# --- sheets ---
_pat(r"IR\.sheets entry missing name",
     "MISSING_SHEET_NAME")
_pat(r"IR\.sheets duplicate name '(?P<name>[^']+)'",
     "DUPLICATE_SHEET_NAME",
     _loc_group("name"))

# --- power tree ---
_pat(r"IR\.power_tree\[(?P<rail>[^]]+)\]\.parent '(?P<parent>[^']+)' not found",
     "MISSING_POWER_PARENT",
     _loc_group("rail"),
     lambda m: {"action": "agent run", "operation": "add_net",
                 "payload": {"name": m.group("parent"), "kind": "power"},
                 "hint": f"Add power rail '{m.group('parent')}' that '{m.group('rail')}' depends on."})
_pat(r"IR\.power_tree\[(?P<rail>[^]]+)\]\.children '(?P<child>[^']+)' not found",
     "MISSING_POWER_CHILD",
     _loc_group("rail"))
_pat(r"IR\.power_tree circular reference involving '(?P<node>[^']+)' -> '(?P<child>[^']+)'",
     "CIRCULAR_POWER_REFERENCE",
     _loc_group("node"),
     lambda m: {"action": "agent run", "operation": "update_net",
                 "payload": {"name": m.group("node")},
                 "hint": f"Break circular power dependency: {m.group('node')} -> {m.group('child')}."})

# --- constraints ---
_pat(r"IR\.constraints\[(?P<name>[^]]+)\]\.targets '(?P<target>[^']+)' not found in nets",
     "CONSTRAINT_TARGET_NET_NOT_FOUND",
     _loc_group("name"))
_pat(r"IR\.constraints\[(?P<name>[^]]+)\]\.targets '(?P<target>[^']+)' not found in components",
     "CONSTRAINT_TARGET_COMPONENT_NOT_FOUND",
     _loc_group("name"))

# --- KiCad leakage ---
_pat(r"IR(?P<path>\$\S+): forbidden KiCad field '(?P<field>[^']+)' leaked into IR",
     "KICAD_FIELD_LEAKAGE",
     _loc_group("path"),
     lambda m: {"action": "agent run", "operation": "remove_component",
                 "payload": {},
                 "hint": f"Remove KiCad field '{m.group('field')}' at path {m.group('path')}."})
_pat(r"IR(?P<path>\$\S+): value '[^']+' starts with KiCad-specific prefix '(?P<prefix>[^']+)'",
     "KICAD_PREFIX_LEAKAGE",
     _loc_group("path"))


def _parse_diagnostic(message: str, level: str) -> dict[str, Any]:
    """Convert a validator error/warning string into a structured diagnostic.

    Returns a dict with ``code``, ``message``, ``location`` (optional),
    and ``suggestion`` (optional) so AI agents can act programmatically.
    """
    for regex, code, loc_fn, sug_fn in _DIAGNOSTIC_PATTERNS:
        m = regex.search(str(message))
        if m:
            diag: dict[str, Any] = {"level": level, "code": code, "message": str(message)}
            if loc_fn is not None:
                try:
                    diag["location"] = loc_fn(m)
                except Exception:
                    pass
            if sug_fn is not None:
                try:
                    diag["suggestion"] = sug_fn(m)
                except Exception:
                    pass
            return diag

    # Fallback: classify by keywords in the message
    msg_lower = str(message).lower()
    if "missing" in msg_lower:
        code = "MISSING_FIELD"
    elif "duplicate" in msg_lower:
        code = "DUPLICATE_ENTRY"
    elif "must be" in msg_lower:
        code = "TYPE_ERROR"
    elif "unknown" in msg_lower:
        code = "UNKNOWN_VALUE"
    elif "circular" in msg_lower:
        code = "CIRCULAR_REFERENCE"
    else:
        code = "VALIDATION_ERROR"
    return {"level": level, "code": code, "message": str(message)}


def _agent_validation_payload(
    stage: str,
    ok: bool,
    errors: list[Any],
    warnings: list[Any],
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "stage": stage,
        "errors": len(errors),
        "warnings": len(warnings),
        "diagnostics": [_parse_diagnostic(str(item), "error") for item in errors]
        + [_parse_diagnostic(str(item), "warning") for item in warnings],
        "stats": stats or {},
    }


def _agent_rule_check_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    project_id, topology = _agent_model_metadata(model_path, project_path)
    request = _agent_request(
        operation="validate_readiness",
        project_id=args.project_id or project_id,
        topology=args.topology or topology,
        payload=_load_payload_args(args),
        request_id=args.request_id,
        options=_agent_options_from_args(args),
    )
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    result = service.handle_dict(request)
    diag = result.get("diagnostics", {})
    payload = _agent_validation_payload(
        "rule_check",
        bool(result.get("success")),
        list(diag.get("errors", [])),
        list(diag.get("warnings", [])),
        dict(diag.get("stats", {})),
    )
    output = project_path / "build" / "rule-check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _update_project_state_from_request(request, result, project_path)
    return _print_json(payload | {"output": str(output)})


def _agent_run_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    project_id, topology = _agent_model_metadata(model_path, project_path)
    payload = _load_payload_args(args)
    request = _agent_request(
        operation=args.operation,
        project_id=getattr(args, "project_id", None) or project_id,
        topology=getattr(args, "topology", None) or topology,
        payload=payload,
        request_id=getattr(args, "request_id", ""),
        options=_agent_options_from_args(args),
    )
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    result = service.handle_dict(request)
    _print_json(result)
    _update_project_state_from_request(request, result, project_path)
    return 0 if result.get("success") else 1


def _agent_create_handler(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    project_id = args.project_id or project_dir.name
    topology = args.topology or project_id.replace("-", "_")
    payload: dict[str, Any] = {
        "project_dir": str(project_dir),
        "project_id": project_id,
        "topology": topology,
        "title": args.title or project_id,
        "overwrite": bool(args.overwrite),
        "export_ir": bool(args.export_ir),
    }
    if args.source_model is not None:
        payload["source_model"] = str(Path(args.source_model).resolve())
    payload.update(_load_payload_args(args))
    request = _agent_request(
        operation="create_hardware_project",
        project_id=project_id,
        topology=topology,
        payload=payload,
        request_id=args.request_id,
        options=_agent_options_from_args(args),
    )
    result = ModelApiService().handle_dict(request)
    _print_json(result)
    _update_project_state_from_request(request, result, project_dir)
    return 0 if result.get("success") else 1


def _agent_export_kicad_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    project_id, topology = _agent_model_metadata(model_path, project_path)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else project_path / "output"
    payload = {
        "output_dir": str(output_dir),
        "project_name": args.project_name or project_path.name.replace("-", "_"),
    }
    payload.update(_load_payload_args(args))
    request = _agent_request(
        operation="export_kicad_project",
        project_id=args.project_id or project_id,
        topology=args.topology or topology,
        payload=payload,
        request_id=args.request_id,
        options=_agent_options_from_args(args),
    )
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    result = service.handle_dict(request)
    _print_json(result)
    _update_project_state_from_request(request, result, project_path)
    return 0 if result.get("success") else 1


def _agent_report_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    report = build_report(project_path)
    output_json = Path(args.output_json).resolve() if args.output_json else project_path / "build" / "report.json"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(format_report(report, FORMAT_JSON) + "\n", encoding="utf-8")
    outputs = {"json": str(output_json)}
    if args.markdown:
        output_md = Path(args.output_md).resolve() if args.output_md else project_path / "build" / "report.md"
        output_md.write_text(format_report(report, FORMAT_MARKDOWN) + "\n", encoding="utf-8")
        outputs["markdown"] = str(output_md)
    return _print_json({
        "ok": report.get("overall_status") != "error",
        "stage": "report",
        "overall_status": report.get("overall_status"),
        "outputs": outputs,
        "project": report.get("project", {}),
    })


def _agent_history_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    ps = ProjectState(project_path)
    history = ps.get_history(limit=args.limit)
    return _print_json({"ok": True, "stage": "history", "count": len(history), "entries": history})


def _agent_doctor_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    source_path, resolved_path = resolve_model_paths(model_path)
    checks: list[dict[str, Any]] = []
    checks.append({
        "name": "python",
        "ok": True,
        "message": sys.version.split()[0],
    })
    checks.append({
        "name": "project_dir",
        "ok": project_path.exists(),
        "message": str(project_path),
        "suggestion": "Run agent create before building." if not project_path.exists() else "",
    })
    checks.append({
        "name": "circuit_model",
        "ok": source_path.exists() or resolved_path.exists() or model_path.exists(),
        "message": f"{source_path} | {resolved_path}",
        "suggestion": "Create or provide source/circuit-model.source.json and/or build/circuit-model.resolved.json." if not (source_path.exists() or resolved_path.exists() or model_path.exists()) else "",
    })
    for rel in ('schemas', 'resources/kicad/symbols', 'resources/kicad/footprints'):
        path = repo_root() / rel
        checks.append({
            "name": rel.replace("/", "_"),
            "ok": path.exists(),
            "message": str(path),
            "suggestion": f"Restore missing repository path: {rel}" if not path.exists() else "",
        })
    ngspice = diagnose_ngspice_environment()
    checks.append({
        "name": "ngspice",
        "ok": bool(ngspice.get("available", ngspice.get("found", False))),
        "message": str(ngspice.get("executable", "")) or "ngspice not found",
        "suggestion": "Install ngspice or configure NGSPICE_BIN." if not ngspice.get("available", ngspice.get("found", False)) else "",
    })
    ok = all(bool(item.get("ok")) for item in checks if item["name"] not in {"ngspice"})
    return _print_json({"ok": ok, "stage": "doctor", "checks": checks})


def _agent_pins_free_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    model = load_circuit_model(model_path)
    ir = build_ir(model)
    pm = PinManager(ir, mcu_family=args.mcu_family or "")
    free = pm.list_free(mcu_ref=args.ref or "")
    return _print_json({
        "ok": True,
        "stage": "pins_free",
        "mcu_ref": args.ref,
        "count": len(free),
        "pins": free,
    })


def _agent_pins_assign_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    project_id, topology = _agent_model_metadata(model_path, project_path)
    payload = {"ref": args.ref, "pin": args.pin, "net": args.net}
    if args.role:
        payload["role"] = args.role
    request = _agent_request(
        operation="connect_pin_to_net",
        project_id=args.project_id or project_id,
        topology=args.topology or topology,
        payload=payload,
        request_id=args.request_id,
        options=_agent_options_from_args(args),
    )
    if args.dry_run:
        return _print_json({"ok": True, "stage": "pins_assign", "dry_run": True, "request": request})
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    result = service.handle_dict(request)
    _print_json(result)
    _update_project_state_from_request(request, result, project_path)
    return 0 if result.get("success") else 1


def _agent_pins_check_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    model = load_circuit_model(model_path)
    ir = build_ir(model)
    pm = PinManager(ir, mcu_family=args.mcu_family or "")
    conflicts: list[dict[str, Any]] = []
    all_pins = pm.list_all()
    for entry in all_pins:
        err = pm.check_conflict(entry["pin"], entry["component_ref"], entry["signal"])
        if err:
            conflicts.append({"pin": entry["pin"], "component_ref": entry["component_ref"],
                              "signal": entry["signal"], "conflict": err})
    return _print_json({
        "ok": len(conflicts) == 0,
        "stage": "pins_check",
        "total_assigned": len(all_pins),
        "conflicts": conflicts,
    })


def _agent_self_test_handler(args: argparse.Namespace) -> int:
    import subprocess
    test_dir = repo_root()
    test_args = ["python", "-m", "pytest", str(test_dir / "tests"), "-v", "--tb=short"]
    if args.filter_expr:
        test_args.extend(["-k", args.filter_expr])
    proc = subprocess.run(test_args, capture_output=True, text=True, cwd=str(test_dir))
    return _print_json({
        "ok": proc.returncode == 0,
        "stage": "self_test",
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-8000:] if len(proc.stdout) > 8000 else proc.stdout,
        "stderr": proc.stderr[-4000:] if len(proc.stderr) > 4000 else proc.stderr,
    })


def _agent_build_kicad_plan_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    project_id, topology = _agent_model_metadata(model_path, project_path)
    payload: dict[str, Any] = {"output_dir": str(project_path / "build")}
    payload.update(_load_payload_args(args))
    request = _agent_request(
        operation="compile_kicad_execution_plan",
        project_id=args.project_id or project_id,
        topology=args.topology or topology,
        payload=payload,
        request_id=args.request_id,
        options=_agent_options_from_args(args),
    )
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    result = service.handle_dict(request)
    _print_json(result)
    _update_project_state_from_request(request, result, project_path)
    return 0 if result.get("success") else 1


def _agent_patch_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    project_id, topology = _agent_model_metadata(model_path, project_path)
    patch_data = _load_payload_args(args)
    if "patch" not in patch_data:
        all_other = {k: v for k, v in patch_data.items() if k != "config"}
        patch_data = {"patch": all_other}
    request = _agent_request(
        operation="patch_model",
        project_id=args.project_id or project_id,
        topology=args.topology or topology,
        payload=patch_data,
        request_id=args.request_id,
        options=_agent_options_from_args(args),
    )
    if args.dry_run:
        return _print_json({"ok": True, "stage": "patch", "dry_run": True, "request": request})
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    result = service.handle_dict(request)
    _print_json(result)
    _update_project_state_from_request(request, result, project_path)
    return 0 if result.get("success") else 1


def _agent_jlc_search_handler(args: argparse.Namespace) -> int:
    results = jlc_search(args.query, limit=args.limit or 10)
    return _print_json({
        "ok": len(results) > 0,
        "stage": "jlc_search",
        "query": args.query,
        "count": len(results),
        "results": results,
    })


def _agent_jlc_info_handler(args: argparse.Namespace) -> int:
    """Preview component data from EasyEDA without installing files."""
    comp = jlc_api.get_component(args.lcsc_id, retries=3, delay=0.3)
    if comp is None:
        return _print_json({"ok": False, "stage": "jlc_info", "lcsc_id": args.lcsc_id, "error": "Component not found on EasyEDA"})
    ds = comp.get("data_str", {}) if isinstance(comp, dict) else {}
    shapes = ds.get("shape", []) if isinstance(ds, dict) else []
    pins = [s for s in shapes if isinstance(s, str) and s.startswith("P~")]
    return _print_json({
        "ok": True, "stage": "jlc_info",
        "lcsc_id": args.lcsc_id,
        "title": comp.get("title", ""),
        "package": comp.get("package_title", ""),
        "pin_count": len(pins),
        "shape_count": len(shapes),
        "has_data": len(shapes) > 0,
    })


def _agent_jlc_download_handler(args: argparse.Namespace) -> int:
    project_path = _agent_project_path(args)
    if args.lcsc_id:
        result = install_by_lcsc_id(args.lcsc_id, project_path)
    else:
        result = search_and_install(args.query, project_path, limit=args.limit or 5, auto_select=args.auto)
    return _print_json(result)


def _agent_resolve_symbols_handler(args: argparse.Namespace) -> int:
    import time as _time
    project_path = _agent_project_path(args)
    model_path = _agent_model_path(args)
    model = load_circuit_model(model_path)
    timeout = getattr(args, "timeout", 120) or 120
    delay = getattr(args, "delay", 0) or 0
    t0 = _time.monotonic()
    result = resolve_missing_symbols(project_path, model, timeout=timeout, delay=delay, model_path=model_path)
    elapsed = round(_time.monotonic() - t0, 2)
    result["elapsed_sec"] = elapsed

    # Log to operations.jsonl
    ps = ProjectState(project_path)
    ps.load()
    easyeda = sum(1 for x in result.get("details", []) if x.get("source") == "easyeda")
    search_hint = sum(1 for x in result.get("details", []) if x.get("source") == "search_hint")
    placeholder = sum(1 for x in result.get("details", []) if "placeholder" in x.get("source", ""))
    ps.mark_dirty(reason="resolve-symbols")
    ps._append_operation({
        "op": "resolve_symbols",
        "ok": result.get("ok", False),
        "elapsed_sec": elapsed,
        "total": result.get("resolved", 0),
        "easyeda": easyeda,
        "search_hint": search_hint,
        "placeholder": placeholder,
        "failed": result.get("failed", 0),
        "model_updated": result.get("model_updated", False),
    })
    ps.save()

    return _print_json(result)


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

    # kas agent
    agent_cmd = subparsers.add_parser("agent", help="AI-agent friendly project and DSL API entrypoint.")
    agent_subs = agent_cmd.add_subparsers(dest="agent_action")

    agent_manifest = agent_subs.add_parser("manifest", help="Describe the agent-facing command surface.")
    agent_manifest.set_defaults(handler=_agent_manifest_handler)

    agent_status = agent_subs.add_parser("status", help="Show machine-readable project status.")
    agent_status.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_status.set_defaults(handler=_agent_status_handler)

    agent_inspect = agent_subs.add_parser("inspect", help="Inspect project model and build state.")
    agent_inspect.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_inspect.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_inspect.set_defaults(handler=_agent_inspect_handler)

    agent_explain = agent_subs.add_parser("explain", help="Explain current project state for an agent.")
    agent_explain.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_explain.set_defaults(handler=_agent_explain_handler)

    agent_build_ir = agent_subs.add_parser("build-ir", help="Compile source/circuit-model.source.json to build/ir.v1.json.")
    agent_build_ir.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_build_ir.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_build_ir.add_argument("--output", type=Path, default=None)
    agent_build_ir.set_defaults(handler=_agent_build_ir_handler)

    agent_validate_ir = agent_subs.add_parser("validate-ir", help="Compile and validate Hardware IR.")
    agent_validate_ir.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_validate_ir.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_validate_ir.add_argument("--output", type=Path, default=None)
    agent_validate_ir.set_defaults(handler=_agent_validate_ir_handler)

    agent_rule_check = agent_subs.add_parser("rule-check", help="Run project readiness checks.")
    agent_rule_check.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_rule_check.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_rule_check.add_argument("--payload-json", default="")
    agent_rule_check.add_argument("--payload-file", type=Path, default=None)
    agent_rule_check.add_argument("--project-id", default="")
    agent_rule_check.add_argument("--topology", default="")
    agent_rule_check.add_argument("--request-id", default="")
    agent_rule_check.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_rule_check.add_argument("--dry-run", action="store_true")
    agent_rule_check.add_argument("--validate-only", action="store_true")
    agent_rule_check.add_argument("--no-commit", action="store_true")
    agent_rule_check.add_argument("--no-strict", action="store_true")
    agent_rule_check.add_argument("--no-diff", action="store_true")
    agent_rule_check.add_argument("--no-snapshot", action="store_true")
    agent_rule_check.set_defaults(handler=_agent_rule_check_handler)

    agent_run = agent_subs.add_parser("run", help="Apply one DSL Model API operation to a project source model.")
    agent_run.add_argument("operation")
    agent_run.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_run.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_run.add_argument("--payload-json", default="")
    agent_run.add_argument("--payload-file", type=Path, default=None)
    agent_run.add_argument("--project-id", default="")
    agent_run.add_argument("--topology", default="")
    agent_run.add_argument("--request-id", default="")
    agent_run.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_run.add_argument("--dry-run", action="store_true")
    agent_run.add_argument("--validate-only", action="store_true")
    agent_run.add_argument("--no-commit", action="store_true")
    agent_run.add_argument("--no-strict", action="store_true")
    agent_run.add_argument("--no-diff", action="store_true")
    agent_run.add_argument("--no-snapshot", action="store_true")
    agent_run.set_defaults(handler=_agent_run_handler)

    agent_create = agent_subs.add_parser("create", help="Create a hardware project for agent-managed work.")
    agent_create.add_argument("project_dir", type=Path)
    agent_create.add_argument("--project-id", default="")
    agent_create.add_argument("--topology", default="")
    agent_create.add_argument("--title", default="")
    agent_create.add_argument("--source-model", type=Path, default=None)
    agent_create.add_argument("--request-id", default="")
    agent_create.add_argument("--payload-json", default="")
    agent_create.add_argument("--payload-file", type=Path, default=None)
    agent_create.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_create.add_argument("--overwrite", action="store_true")
    agent_create.add_argument("--export-ir", action="store_true")
    agent_create.add_argument("--dry-run", action="store_true")
    agent_create.add_argument("--validate-only", action="store_true")
    agent_create.add_argument("--no-commit", action="store_true")
    agent_create.add_argument("--no-strict", action="store_true")
    agent_create.add_argument("--no-diff", action="store_true")
    agent_create.add_argument("--no-snapshot", action="store_true")
    agent_create.set_defaults(handler=_agent_create_handler)

    agent_export = agent_subs.add_parser("export-kicad", help="Export a project model to KiCad.")
    agent_export.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_export.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_export.add_argument("--output-dir", type=Path, default=None)
    agent_export.add_argument("--project-name", default="")
    agent_export.add_argument("--project-id", default="")
    agent_export.add_argument("--topology", default="")
    agent_export.add_argument("--request-id", default="")
    agent_export.add_argument("--payload-json", default="")
    agent_export.add_argument("--payload-file", type=Path, default=None)
    agent_export.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_export.add_argument("--dry-run", action="store_true")
    agent_export.add_argument("--validate-only", action="store_true")
    agent_export.add_argument("--no-commit", action="store_true")
    agent_export.add_argument("--no-strict", action="store_true")
    agent_export.add_argument("--no-diff", action="store_true")
    agent_export.add_argument("--no-snapshot", action="store_true")
    agent_export.set_defaults(handler=_agent_export_kicad_handler)

    agent_build_kicad = agent_subs.add_parser("build-kicad", help="Alias for export-kicad.")
    agent_build_kicad.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_build_kicad.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_build_kicad.add_argument("--output-dir", type=Path, default=None)
    agent_build_kicad.add_argument("--project-name", default="")
    agent_build_kicad.add_argument("--project-id", default="")
    agent_build_kicad.add_argument("--topology", default="")
    agent_build_kicad.add_argument("--request-id", default="")
    agent_build_kicad.add_argument("--payload-json", default="")
    agent_build_kicad.add_argument("--payload-file", type=Path, default=None)
    agent_build_kicad.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_build_kicad.add_argument("--dry-run", action="store_true")
    agent_build_kicad.add_argument("--validate-only", action="store_true")
    agent_build_kicad.add_argument("--no-commit", action="store_true")
    agent_build_kicad.add_argument("--no-strict", action="store_true")
    agent_build_kicad.add_argument("--no-diff", action="store_true")
    agent_build_kicad.add_argument("--no-snapshot", action="store_true")
    agent_build_kicad.set_defaults(handler=_agent_export_kicad_handler)

    agent_report = agent_subs.add_parser("report", help="Write build/report.json for agents.")
    agent_report.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_report.add_argument("--output-json", type=Path, default=None)
    agent_report.add_argument("--output-md", type=Path, default=None)
    agent_report.add_argument("--markdown", action="store_true")
    agent_report.set_defaults(handler=_agent_report_handler)

    agent_history = agent_subs.add_parser("history", help="Show recent project operations.")
    agent_history.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_history.add_argument("-n", "--limit", type=int, default=50)
    agent_history.set_defaults(handler=_agent_history_handler)

    agent_doctor = agent_subs.add_parser("doctor", help="Check toolchain environment and project layout.")
    agent_doctor.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_doctor.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_doctor.set_defaults(handler=_agent_doctor_handler)

    agent_pins = agent_subs.add_parser("pins", help="Pin resource management.")
    agent_pins_subs = agent_pins.add_subparsers(dest="pins_action")

    pins_free = agent_pins_subs.add_parser("free", help="List free GPIO pins for an MCU.")
    pins_free.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    pins_free.add_argument("--model", dest="model_path", type=Path, default=None)
    pins_free.add_argument("--ref", default="", help="MCU component reference (e.g. U1).")
    pins_free.add_argument("--mcu-family", default="", help="MCU family for capability lookup.")
    pins_free.set_defaults(handler=_agent_pins_free_handler)

    pins_assign = agent_pins_subs.add_parser("assign", help="Connect a pin to a net.")
    pins_assign.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    pins_assign.add_argument("--model", dest="model_path", type=Path, default=None)
    pins_assign.add_argument("--ref", required=True, help="Component reference (e.g. U1).")
    pins_assign.add_argument("--pin", required=True, help="Pin number or GPIO name.")
    pins_assign.add_argument("--net", required=True, help="Net name to connect the pin to.")
    pins_assign.add_argument("--role", default="", help="Optional pin role.")
    pins_assign.add_argument("--project-id", default="")
    pins_assign.add_argument("--topology", default="")
    pins_assign.add_argument("--request-id", default="")
    pins_assign.add_argument("--dry-run", action="store_true")
    pins_assign.add_argument("--validate-only", action="store_true")
    pins_assign.add_argument("--no-commit", action="store_true")
    pins_assign.set_defaults(handler=_agent_pins_assign_handler)

    pins_check = agent_pins_subs.add_parser("check", help="Check for pin conflicts.")
    pins_check.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    pins_check.add_argument("--model", dest="model_path", type=Path, default=None)
    pins_check.add_argument("--mcu-family", default="", help="MCU family for capability lookup.")
    pins_check.set_defaults(handler=_agent_pins_check_handler)

    agent_self_test = agent_subs.add_parser("self-test", help="Run the test suite and report results.")
    agent_self_test.add_argument("-k", "--filter", dest="filter_expr", default="", help="Pytest filter expression.")
    agent_self_test.set_defaults(handler=_agent_self_test_handler)

    agent_build_plan = agent_subs.add_parser("build-kicad-plan", help="Compile the KiCad execution plan.")
    agent_build_plan.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_build_plan.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_build_plan.add_argument("--payload-json", default="")
    agent_build_plan.add_argument("--payload-file", type=Path, default=None)
    agent_build_plan.add_argument("--project-id", default="")
    agent_build_plan.add_argument("--topology", default="")
    agent_build_plan.add_argument("--request-id", default="")
    agent_build_plan.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_build_plan.add_argument("--dry-run", action="store_true")
    agent_build_plan.add_argument("--validate-only", action="store_true")
    agent_build_plan.add_argument("--no-commit", action="store_true")
    agent_build_plan.add_argument("--no-strict", action="store_true")
    agent_build_plan.add_argument("--no-diff", action="store_true")
    agent_build_plan.add_argument("--no-snapshot", action="store_true")
    agent_build_plan.set_defaults(handler=_agent_build_kicad_plan_handler)

    agent_patch = agent_subs.add_parser("patch", help="Apply a model patch to the source circuit model.")
    agent_patch.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_patch.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_patch.add_argument("--payload-json", default="")
    agent_patch.add_argument("--payload-file", type=Path, default=None)
    agent_patch.add_argument("--project-id", default="")
    agent_patch.add_argument("--topology", default="")
    agent_patch.add_argument("--request-id", default="")
    agent_patch.add_argument("--config", "--config-path", dest="config_path", type=Path, default=None)
    agent_patch.add_argument("--dry-run", action="store_true")
    agent_patch.add_argument("--validate-only", action="store_true")
    agent_patch.add_argument("--no-commit", action="store_true")
    agent_patch.add_argument("--no-strict", action="store_true")
    agent_patch.add_argument("--no-diff", action="store_true")
    agent_patch.add_argument("--no-snapshot", action="store_true")
    agent_patch.set_defaults(handler=_agent_patch_handler)

    # kas agent jlc
    agent_jlc = agent_subs.add_parser("jlc", help="JLC/LCSC component search, preview, and download.")
    agent_jlc_subs = agent_jlc.add_subparsers(dest="jlc_action")

    jlc_search_cmd = agent_jlc_subs.add_parser("search", help="Search LCSC for components.")
    jlc_search_cmd.add_argument("query")
    jlc_search_cmd.add_argument("-n", "--limit", type=int, default=10)
    jlc_search_cmd.set_defaults(handler=_agent_jlc_search_handler)

    jlc_info_cmd = agent_jlc_subs.add_parser("info", help="Preview component data from EasyEDA (no files written).")
    jlc_info_cmd.add_argument("lcsc_id")
    jlc_info_cmd.set_defaults(handler=_agent_jlc_info_handler)

    jlc_download_cmd = agent_jlc_subs.add_parser("download", help="Download a component from LCSC into project libraries.")
    jlc_download_cmd.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    jlc_download_cmd.add_argument("--lcsc-id", dest="lcsc_id", default="")
    jlc_download_cmd.add_argument("--query", default="")
    jlc_download_cmd.add_argument("--auto", action="store_true", help="Auto-select first search result.")
    jlc_download_cmd.add_argument("-n", "--limit", type=int, default=5)
    jlc_download_cmd.set_defaults(handler=_agent_jlc_download_handler)

    agent_resolve = agent_subs.add_parser("resolve-symbols", help="Auto-resolve all missing symbols via JLC search.")
    agent_resolve.add_argument("--project", dest="project_path", type=Path, default=Path.cwd())
    agent_resolve.add_argument("--model", dest="model_path", type=Path, default=None)
    agent_resolve.add_argument("--timeout", type=int, default=120, help="Max total seconds (default 120).")
    agent_resolve.add_argument("--delay", type=float, default=0.8, help="Delay between API calls in seconds (default 0.8).")
    agent_resolve.set_defaults(handler=_agent_resolve_symbols_handler)

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
