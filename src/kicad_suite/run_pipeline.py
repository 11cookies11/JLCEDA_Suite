#!/usr/bin/env python3
"""Compatibility wrapper for the KiCad pipeline runner.

Prefer :mod:`kicad_suite.pipeline_coordinator` or the ``kas`` CLI for new work.
This module remains as a stable transition path for older scripts and tests.
"""

from __future__ import annotations

import json
import sys

from .pipeline_coordinator import run_pipeline as _run_pipeline


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("Usage: python run_pipeline.py <source/circuit-model.source.json> <output-dir>")
        return 1
    result = _run_pipeline(args[0], args[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


run_pipeline = _run_pipeline


if __name__ == "__main__":
    raise SystemExit(main())
