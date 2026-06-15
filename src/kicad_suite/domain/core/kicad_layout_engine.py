"""KiCad schematic layout and placement helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...shared.env_utils import env
from .kicad_layout_config import (
    configured_block_order,
    configured_role_rotation,
    layout_numeric_setting,
    load_layout_profiles,
)
from ...adapters.kicad_symbol_library import parse_symbol_pin_map
from .schematic_layout_rules import build_default_layout_rules, _resolve_wiring_block


@dataclass
class KiCadPoint:
    x: float
    y: float
    rotation: float = 0.0


_GRID = 2.54
_BLOCK_GAP = 30.48
_VSLOT_PITCH = 17.78
_LAYOUT_ORIGIN_X = 35.56
_LAYOUT_ORIGIN_Y = 38.1


def _resolve_block(role: str) -> str:
    topology = env("KICAD_TOPOLOGY", "")
    return _resolve_wiring_block(role, build_default_layout_rules(topology).block_layout)


def to_float_env(name: str, fallback: float) -> float:
    raw = env(name, "")
    if not raw:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _estimate_symbol_size_from_pins(lib_id: str) -> tuple[float, float] | None:
    pins = parse_symbol_pin_map(lib_id)
    if not pins:
        return None
    xs = [p["x"] for p in pins.values()]
    ys = [p["y"] for p in pins.values()]
    if not xs:
        return None

    label_extension = 12.0
    body_pad = 3.81
    has_left_labels = any(p["rotation"] == 0 for p in pins.values())
    has_right_labels = any(p["rotation"] == 180 for p in pins.values())
    has_top_labels = any(p["rotation"] == 270 for p in pins.values())
    has_bottom_labels = any(p["rotation"] == 90 for p in pins.values())
    left_margin = label_extension if has_left_labels else body_pad
    right_margin = label_extension if has_right_labels else body_pad
    top_margin = label_extension if has_top_labels else body_pad
    bottom_margin = label_extension if has_bottom_labels else body_pad
    width = (max(xs) - min(xs)) + left_margin + right_margin
    height = (max(ys) - min(ys)) + top_margin + bottom_margin
    return max(width, 10.0), max(height, 8.0)


def _configured_symbol_size(lib_id: str) -> tuple[float, float] | None:
    return None


def _estimate_symbol_size(lib_id: str) -> tuple[float, float]:
    configured_size = _configured_symbol_size(lib_id)
    pin_size = _estimate_symbol_size_from_pins(lib_id)
    if configured_size and pin_size:
        return max(configured_size[0], pin_size[0]), max(configured_size[1], pin_size[1])
    if configured_size:
        return configured_size
    if pin_size:
        return pin_size
    return 12.7, 10.16


def _snap(value: float) -> float:
    return round(value / _GRID) * _GRID


def _compute_block_layout(components: list[tuple[str, str, str]]) -> dict[str, tuple[float, float]]:
    blocks: dict[str, list[tuple[str, str]]] = {}
    for ref, role, lib_id in components:
        block = _resolve_block(role)
        blocks.setdefault(block, []).append((ref, lib_id))

    block_widths: dict[str, float] = {}
    for block, items in blocks.items():
        max_w = 0.0
        for _ref, lib_id in items:
            w, _h = _estimate_symbol_size(lib_id)
            if w > max_w:
                max_w = w
        block_widths[block] = max_w

    block_order = [b for b in configured_block_order() if b in blocks]
    for b in blocks:
        if b not in block_order:
            block_order.append(b)

    layout: dict[str, tuple[float, float]] = {}
    origin_x = layout_numeric_setting("origin_x", _LAYOUT_ORIGIN_X)
    origin_y = layout_numeric_setting("origin_y", _LAYOUT_ORIGIN_Y)
    block_gap = layout_numeric_setting("block_gap", _BLOCK_GAP)
    cursor = origin_x
    row_y = origin_y
    row_height = 0.0
    max_x = to_float_env("KICAD_SCH_MAX_X_MM", layout_numeric_setting("max_x", 260.0))
    row_gap = to_float_env("KICAD_SCH_ROW_GAP_MM", layout_numeric_setting("row_gap", 63.5))
    for block in block_order:
        half_w = block_widths[block] / 2.0
        block_height = max((_estimate_symbol_size(lib_id)[1] for _ref, lib_id in blocks[block]), default=20.0)
        if cursor > origin_x and cursor + block_widths[block] > max_x:
            cursor = origin_x
            row_y = _snap(row_y + max(row_height + 17.78, row_gap))
            row_height = 0.0
        center_x = _snap(cursor + half_w)
        layout[block] = (center_x, row_y)
        cursor = _snap(cursor + block_widths[block] + block_gap)
        row_height = max(row_height, block_height)
    return layout


def _configured_profile_position(topology: str, ref: str, key: str) -> KiCadPoint | None:
    profiles = load_layout_profiles().get("profiles", {})
    if not isinstance(profiles, dict):
        return None
    profile = profiles.get(topology, {})
    if not isinstance(profile, dict):
        return None
    positions = profile.get(key, {})
    if not isinstance(positions, dict):
        return None
    item = positions.get(ref)
    if not isinstance(item, dict):
        return None
    try:
        return KiCadPoint(
            x=float(item.get("x", 0.0)),
            y=float(item.get("y", 0.0)),
            rotation=float(item.get("rotation", 0.0)),
        )
    except (TypeError, ValueError):
        return None


def configured_topology_position(topology: str, ref: str) -> KiCadPoint | None:
    return _configured_profile_position(topology, ref, "positions")


def configured_schematic_position(topology: str, ref: str) -> KiCadPoint | None:
    return _configured_profile_position(topology, ref, "schematic_positions") or configured_topology_position(topology, ref)


def _auto_position(
    ref: str,
    role: str,
    lib_id: str,
    block_x: dict[str, float],
    block_y: dict[str, float],
    block_slot: dict[str, int],
    block_cursor_y: dict[str, float] | None = None,
) -> KiCadPoint:
    block = _resolve_block(role)
    x = block_x.get(block, layout_numeric_setting("origin_x", _LAYOUT_ORIGIN_X))
    base_y = block_y.get(block, layout_numeric_setting("origin_y", _LAYOUT_ORIGIN_Y))
    slot = block_slot.get(block, 0)
    block_slot[block] = slot + 1
    min_pitch = layout_numeric_setting("slot_pitch", _VSLOT_PITCH)
    _, h = _estimate_symbol_size(lib_id)
    gap = 1.27
    if block_cursor_y is not None:
        y = _snap(block_cursor_y.get(block, base_y))
        block_cursor_y[block] = y + max(min_pitch, h + gap)
    else:
        y = _snap(base_y + slot * max(min_pitch, h + gap))
    return KiCadPoint(x=x, y=y, rotation=configured_role_rotation(role))


def role_aware_position(
    model: dict[str, Any],
    component: dict[str, Any],
    index: int,
    origin_x: float,
    origin_y: float,
    pitch_x: float,
    pitch_y: float,
    columns: int,
    block_x: dict[str, float] | None = None,
    block_y: dict[str, float] | None = None,
    block_slot: dict[str, int] | None = None,
    block_cursor_y: dict[str, float] | None = None,
) -> KiCadPoint:
    ref = str(component.get("ref", "")).strip().upper()
    role = str(component.get("role", "")).strip().lower()
    lib_id = str(component.get("_lib_id", ""))
    topology = str(model.get("topology", "")).strip()

    configured = configured_topology_position(topology, ref)
    if configured is not None:
        return configured

    if block_x is not None and block_y is not None and block_slot is not None:
        return _auto_position(ref, role, lib_id, block_x, block_y, block_slot, block_cursor_y)

    col = index % columns
    row = index // columns
    return KiCadPoint(x=origin_x + col * pitch_x, y=origin_y + row * pitch_y, rotation=0.0)
