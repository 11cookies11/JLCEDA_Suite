"""Shared KiCad layout configuration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...shared.env_utils import env, repo_root

REPO_ROOT = repo_root()
LAYOUT_PROFILES_CACHE: dict[str, Any] | None = None


def load_layout_profiles() -> dict[str, Any]:
    global LAYOUT_PROFILES_CACHE
    if LAYOUT_PROFILES_CACHE is not None:
        return LAYOUT_PROFILES_CACHE
    path = Path(env("KICAD_LAYOUT_PROFILES_FILE", str(REPO_ROOT / "config" / "kicad-layout-profiles.json")))
    LAYOUT_PROFILES_CACHE = load_json_file(path) if path.exists() else {"profiles": {}}
    return LAYOUT_PROFILES_CACHE


def load_json_file(path: Path) -> dict[str, Any]:
    import json

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        return {}
    return payload


def layout_defaults() -> dict[str, Any]:
    defaults = load_layout_profiles().get("default", {})
    return defaults if isinstance(defaults, dict) else {}


def layout_numeric_setting(name: str, fallback: float) -> float:
    settings = layout_defaults().get("layout", {})
    if not isinstance(settings, dict):
        settings = {}
    try:
        return float(settings.get(name, fallback))
    except (TypeError, ValueError):
        return fallback


def configured_block_order() -> list[str]:
    topology = env("KICAD_TOPOLOGY", "")
    if topology:
        from .schematic_layout_rules import build_default_layout_rules

        order = build_default_layout_rules(topology).block_layout.block_order
        if order:
            return [str(item) for item in order if str(item)]
    order = layout_defaults().get("block_order", [])
    if isinstance(order, list):
        return [str(item) for item in order if str(item)]
    return ["input", "power", "reset", "mcu", "memory", "crystal", "boot", "io", "indicator"]


def configured_role_rotation(role: str) -> float:
    rotations = layout_defaults().get("role_rotations", {})
    if not isinstance(rotations, dict):
        return 0.0
    try:
        return float(rotations.get(role, 0.0))
    except (TypeError, ValueError):
        return 0.0
