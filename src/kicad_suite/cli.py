#!/usr/bin/env python3
"""Unified command-line entrypoint for KiCad Agent Suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from .artifact_validator import main as validate_artifacts_main
from .compile_kicad_execution_plan import run as run_compile_plan
from .kicad_erc_runner import run as run_erc
from .kicad_project_writer import run as run_write_project
from .run_pipeline import run_pipeline
from .server_eda_target import run as run_eda_target
from .server_text_to_kicad import run as run_text_to_kicad


Handler = Callable[[list[str]], int]


def _print_json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _pipeline_handler(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kas pipeline")
    parser.add_argument("model_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    return _print_json(run_pipeline(str(args.model_path), str(args.output_dir)))


def _text_to_kicad_handler(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kas text-to-kicad")
    parser.parse_args(argv)
    run_text_to_kicad()
    return 0


def _eda_target_handler(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kas pipeline")
    parser.parse_args(argv)
    run_eda_target()
    return 0


def _compile_plan_handler(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kas compile-plan")
    parser.parse_args(argv)
    run_compile_plan()
    return 0


def _write_project_handler(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kas write-project")
    parser.parse_args(argv)
    run_write_project()
    return 0


def _erc_handler(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kas erc")
    parser.parse_args(argv)
    run_erc()
    return 0


def _validate_artifacts_handler(argv: list[str]) -> int:
    return validate_artifacts_main(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kas", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("pipeline", help="Run the circuit-model to KiCad pipeline.")
    subparsers.add_parser("eda-target", help="Run the EDA target pipeline.")
    subparsers.add_parser("text-to-kicad", help="Run the text-to-KiCad pipeline.")
    subparsers.add_parser("compile-plan", help="Compile a KiCad execution plan from env inputs.")
    subparsers.add_parser("write-project", help="Write KiCad project files from the execution plan.")
    subparsers.add_parser("erc", help="Run KiCad ERC on the resolved schematic.")
    subparsers.add_parser("validate-artifacts", help="Validate generated artifacts for consistency.")
    return parser


def dispatch(command: str, argv: list[str]) -> int:
    handlers: dict[str, Handler] = {
        "pipeline": _pipeline_handler,
        "eda-target": _eda_target_handler,
        "text-to-kicad": _text_to_kicad_handler,
        "compile-plan": _compile_plan_handler,
        "write-project": _write_project_handler,
        "erc": _erc_handler,
        "validate-artifacts": _validate_artifacts_handler,
    }
    handler = handlers.get(command)
    if handler is None:
        raise KeyError(command)
    return handler(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args, remainder = parser.parse_known_args(argv[:1])
    if args.command is None:
        parser.print_help()
        return 1
    return dispatch(args.command, argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
