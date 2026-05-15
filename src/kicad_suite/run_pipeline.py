#!/usr/bin/env python3
"""Compatibility wrapper for the KiCad pipeline runner."""

from __future__ import annotations

import json
import sys

from .pipeline_coordinator import run_pipeline


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_pipeline.py <circuit-model.json> <output-dir>")
        sys.exit(1)
    result = run_pipeline(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
