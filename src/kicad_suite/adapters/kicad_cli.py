#!/usr/bin/env python3
"""Adapter helpers for invoking KiCad CLI tools."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..env_utils import env


def resolve_kicad_cli() -> str:
    explicit = env("KICAD_CLI_BIN")
    if explicit:
        return explicit
    located = shutil.which("kicad-cli") or shutil.which("kicad-cli.exe")
    if located:
        return located
    windows_roots = [
        Path("D:/Program Files/KiCad"),
        Path("C:/Program Files/KiCad"),
    ]
    candidates: list[Path] = []
    for root in windows_roots:
        if root.exists():
            candidates.extend(root.glob("*/bin/kicad-cli.exe"))
    if candidates:
        return str(sorted(candidates)[-1])
    return ""


def load_schematic_from_plan() -> str:
    plan_file = env("KICAD_EXECUTION_PLAN_FILE")
    if not plan_file:
        return ""
    try:
        with Path(plan_file).open("r", encoding="utf-8") as file:
            plan = json.load(file)
        target = plan.get("target", {})
        if isinstance(target, dict):
            return str(target.get("schematic_file", "") or "")
    except Exception:
        return ""
    return ""


def resolve_schematic_file() -> Path:
    schematic_file = env("KICAD_SCHEMATIC_FILE") or load_schematic_from_plan()
    if not schematic_file:
        raise ValueError("KICAD_SCHEMATIC_FILE or KICAD_EXECUTION_PLAN_FILE is required.")
    path = Path(schematic_file)
    if not path.exists():
        raise ValueError(f"KiCad schematic file does not exist: {path}")
    return path


def count_findings(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("sheets"), list):
        return sum(
            len(sheet.get("violations", []))
            for sheet in payload["sheets"]
            if isinstance(sheet, dict) and isinstance(sheet.get("violations", []), list)
        )
    if isinstance(payload, dict):
        total = 0
        for key, value in payload.items():
            key_text = str(key).lower()
            if key_text in {"violations", "errors", "warnings", "items"} and isinstance(value, list):
                total += len(value)
            total += count_findings(value)
        return total
    if isinstance(payload, list):
        return sum(count_findings(item) for item in payload)
    return 0

