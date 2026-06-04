"""Helpers for loading and saving dual-file circuit models.

The supported layout is:

* ``source/<name>.source.json`` = human-authored source model
* ``build/<name>.resolved.json`` = toolchain-derived resolution overlay

Consumers should load the merged view and write the resolved overlay beside
the source file in the project workspace.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ...shared.validation.common import load_json


_IDENTITY_KEYS: dict[str, str] = {
    "components": "ref",
    "nets": "name",
    "sheets": "name",
    "calculations": "name",
    "design_decisions": "title",
    "risks": "key",
    "constraints": "name",
    "power_rails": "name",
}


def _is_effective_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _merge_dicts(source: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(resolved)
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(value, merged[key])
        elif _is_effective_value(value):
            merged[key] = deepcopy(value)
        elif key not in merged:
            merged[key] = deepcopy(value)
    return merged


def resolve_model_paths(model_path: Path) -> tuple[Path, Path]:
    """Return ``(source_path, resolved_path)`` for *model_path*."""
    project_root = project_root_from_model_path(model_path)
    base_name = _model_base_name(model_path)
    source_path = project_root / "source" / f"{base_name}.source.json"
    resolved_path = project_root / "build" / f"{base_name}.resolved.json"

    if model_path.name.endswith(".source.json") and model_path.parent.name == "source":
        source_path = model_path
    if model_path.name.endswith(".resolved.json") and model_path.parent.name == "build":
        resolved_path = model_path
    return source_path, resolved_path


def project_root_from_model_path(model_path: Path) -> Path:
    """Return the project root containing ``source/`` and ``build/``."""
    if model_path.parent.name in {"source", "build"} and model_path.parent.parent != model_path.parent:
        return model_path.parent.parent
    return model_path.parent


def _model_base_name(model_path: Path) -> str:
    name = model_path.name
    for suffix in (".resolved.json", ".source.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _merge_object_lists(
    source_items: list[Any],
    resolved_items: list[Any],
    *,
    identity_key: str,
) -> list[Any]:
    merged: list[Any] = []
    scalar_seen: set[str] = set()

    def _append_scalar_once(item: Any) -> None:
        marker = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else repr(item)
        if marker in scalar_seen:
            return
        scalar_seen.add(marker)
        merged.append(deepcopy(item))

    source_by_id: dict[str, dict[str, Any]] = {}
    source_order: list[str] = []
    for item in source_items:
        if not isinstance(item, dict):
            _append_scalar_once(item)
            continue
        item_id = str(item.get(identity_key, "")).strip()
        if item_id:
            source_by_id[item_id] = deepcopy(item)
            source_order.append(item_id)
        else:
            _append_scalar_once(item)

    resolved_by_id: dict[str, dict[str, Any]] = {}
    resolved_order: list[str] = []
    for item in resolved_items:
        if not isinstance(item, dict):
            _append_scalar_once(item)
            continue
        item_id = str(item.get(identity_key, "")).strip()
        if item_id:
            resolved_by_id[item_id] = deepcopy(item)
            resolved_order.append(item_id)
        else:
            _append_scalar_once(item)

    seen: set[str] = set()
    for item_id in source_order:
        source_item = source_by_id.get(item_id, {})
        resolved_item = resolved_by_id.get(item_id, {})
        if not resolved_item:
            merged.append(deepcopy(source_item))
            continue
        merged.append(_merge_dicts(source_item, resolved_item))
        seen.add(item_id)

    for item_id in resolved_order:
        if item_id in seen:
            continue
        merged.append(deepcopy(resolved_by_id[item_id]))

    return merged


def merge_circuit_models(source_model: dict[str, Any], resolved_model: dict[str, Any]) -> dict[str, Any]:
    """Merge a human-authored source model with a toolchain-resolved model."""
    merged = deepcopy(source_model if isinstance(source_model, dict) else {})
    if not isinstance(resolved_model, dict):
        return merged

    for key, identity_key in _IDENTITY_KEYS.items():
        source_items = merged.get(key, [])
        resolved_items = resolved_model.get(key, [])
        if isinstance(source_items, list) or isinstance(resolved_items, list):
            if key == "risks":
                resolved_items = _filter_resolved_risks(
                    source_items if isinstance(source_items, list) else [],
                    resolved_items if isinstance(resolved_items, list) else [],
                )
            merged[key] = _merge_object_lists(
                source_items if isinstance(source_items, list) else [],
                resolved_items if isinstance(resolved_items, list) else [],
                identity_key=identity_key,
            )

    for key, value in resolved_model.items():
        if key in _IDENTITY_KEYS:
            continue
        if key in {"schema_version", "request_id", "project_id", "topology"}:
            if not str(merged.get(key, "")).strip() and value not in (None, ""):
                merged[key] = deepcopy(value)
            continue
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = deepcopy(value)

    return merged


def _filter_resolved_risks(source_items: list[Any], resolved_items: list[Any]) -> list[Any]:
    """Keep source-authored keyless risks authoritative over stale overlays."""
    source_has_keyless = any(not (isinstance(item, dict) and str(item.get("key", "")).strip()) for item in source_items)
    if not source_has_keyless:
        return resolved_items
    return [
        item
        for item in resolved_items
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    ]


def load_dual_circuit_model(model_path: Path) -> dict[str, Any]:
    """Load the merged source+resolved circuit model for *model_path*."""
    source_path, resolved_path = resolve_model_paths(model_path)
    if not source_path.exists() and not resolved_path.exists():
        raise FileNotFoundError(source_path)

    source_model = load_json(source_path) if source_path.exists() else {}
    resolved_model = load_json(resolved_path) if resolved_path.exists() else {}
    if not source_model:
        return resolved_model
    if not resolved_model:
        return source_model
    return merge_circuit_models(source_model, resolved_model)


def save_resolved_circuit_model(model_path: Path, model: dict[str, Any]) -> Path:
    """Write the toolchain-derived resolved model beside the source file."""
    _, resolved_path = resolve_model_paths(model_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(model)
    resolved_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resolved_path


def save_source_circuit_model(model_path: Path, model: dict[str, Any]) -> Path:
    """Write the human-authored source model into ``source/``."""
    source_path, _ = resolve_model_paths(model_path)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(model)
    source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return source_path
