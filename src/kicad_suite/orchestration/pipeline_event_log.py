#!/usr/bin/env python3
"""Time-ordered event logging for pipeline runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_LOG_FILENAME = "pipeline-events.jsonl"


def pipeline_event_log_path(output_dir: Path) -> Path:
    return output_dir / EVENT_LOG_FILENAME


def _timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_pipeline_event(log_path: Path, stage: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "timestamp": _timestamp(),
        "stage": stage,
        "message": message,
    }
    if data:
        entry["data"] = data
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
