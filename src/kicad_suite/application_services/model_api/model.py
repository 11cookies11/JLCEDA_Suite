"""In-memory helpers for circuit-model DSL payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...shared.schema_versions import CIRCUIT_MODEL_SCHEMA_VERSION


MODEL_LIST_FIELDS = (
    "components",
    "nets",
    "calculations",
    "design_decisions",
    "risks",
    "constraints",
    "sheets",
)


def empty_model(request_id: str, project_id: str, topology: str = "") -> dict[str, Any]:
    model: dict[str, Any] = {
        "schema_version": CIRCUIT_MODEL_SCHEMA_VERSION,
        "request_id": request_id,
        "project_id": project_id,
        "topology": topology or project_id,
    }
    for field in MODEL_LIST_FIELDS:
        model[field] = []
    return model


def normalize_model(model: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(model)
    normalized.setdefault("schema_version", CIRCUIT_MODEL_SCHEMA_VERSION)
    normalized.setdefault("request_id", "")
    normalized.setdefault("project_id", normalized.get("request_id", ""))
    normalized.setdefault("topology", normalized.get("project_id", ""))
    for field in MODEL_LIST_FIELDS:
        value = normalized.get(field)
        normalized[field] = value if isinstance(value, list) else []
    return normalized


def snapshot(model: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(model)
