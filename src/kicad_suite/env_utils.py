"""Environment variable and type conversion utilities for JLCEDA Suite server scripts."""

from __future__ import annotations

import json
import math
import os
from typing import Any


def env(name: str, fallback: str = '') -> str:
    value = os.environ.get(name)
    return value if isinstance(value, str) and value else fallback


def parse_json_env(name: str, fallback: Any) -> Any:
    raw = env(name)
    if not raw:
        return fallback
    return json.loads(raw)


def is_truthy_env(name: str, fallback: str = 'false') -> bool:
    return normalize_text(env(name, fallback)) in ('1', 'true', 'yes', 'on')


def to_int_env(name: str, fallback: int) -> int:
    raw = env(name)
    if not raw:
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def normalize_text(value: str) -> str:
    return value.strip().lower()


def to_float(value: Any, fallback: float) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return number
        return None
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except ValueError:
            return None
    return None


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes')
    return False


def get_schematic_layout_config() -> dict[str, int]:
    return {
        'origin_x': to_int_env('BRIDGE_SCH_PLACE_ORIGIN_X', 420),
        'origin_y': to_int_env('BRIDGE_SCH_PLACE_ORIGIN_Y', 220),
        'columns': max(1, to_int_env('BRIDGE_SCH_PLACE_COLUMNS', 4)),
        'pitch_x': max(20, to_int_env('BRIDGE_SCH_PLACE_PITCH_X', 120)),
        'pitch_y': max(20, to_int_env('BRIDGE_SCH_PLACE_PITCH_Y', 100)),
        'label_x_offset': to_int_env('BRIDGE_SCH_LABEL_X_OFFSET', 420),
        'label_y_start_offset': to_int_env('BRIDGE_SCH_LABEL_Y_START_OFFSET', -120),
        'label_y_step': max(8, to_int_env('BRIDGE_SCH_LABEL_Y_STEP', 28)),
        'flag_x_offset': to_int_env('BRIDGE_SCH_FLAG_X_OFFSET', 500),
    }
