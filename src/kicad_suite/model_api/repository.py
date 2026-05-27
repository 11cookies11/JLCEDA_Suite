"""File-backed storage for circuit-model DSL API operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..validation.common import load_json
from .model import normalize_model


class CircuitModelRepository:
    """Load and save one circuit-model JSON file."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path

    def load(self) -> dict[str, Any]:
        return normalize_model(load_json(self.model_path))

    def save(self, model: dict[str, Any]) -> None:
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(normalize_model(model), ensure_ascii=False, indent=2) + "\n"
        self.model_path.write_text(payload, encoding="utf-8")

    @property
    def log_path(self) -> Path:
        return self.model_path.with_name("model-api-operations.jsonl")

    @property
    def revisions_dir(self) -> Path:
        return self.model_path.with_name(".model-api-revisions")

    def next_revision_id(self) -> str:
        self.revisions_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(self.revisions_dir.glob("rev-*.json"))
        return f"rev-{len(existing) + 1:06d}"

    def save_revision(self, revision_id: str, model: dict[str, Any]) -> Path:
        self.revisions_dir.mkdir(parents=True, exist_ok=True)
        path = self.revisions_dir / f"{revision_id}.json"
        path.write_text(json.dumps(normalize_model(model), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def append_operation_log(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
