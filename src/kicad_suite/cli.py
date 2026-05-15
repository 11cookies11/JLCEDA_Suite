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
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import run as run_write_project


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

    validate_artifacts = subparsers.add_parser("validate-artifacts", help="Validate generated artifacts for consistency.")
    validate_artifacts.add_argument("--summary", type=Path, required=True)
    validate_artifacts.add_argument("--strict", action="store_true")
    validate_artifacts.add_argument("--require-erc", action="store_true")
    validate_artifacts.add_argument("--json", action="store_true")
    validate_artifacts.set_defaults(handler=_validate_artifacts_handler)
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
