"""Operation payload checks for the circuit-model DSL API."""

from __future__ import annotations

from typing import Any

from ..validation.common import ValidationReport
from .commands import OperationRequest


REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "add_component": ("ref",),
    "update_component": ("ref",),
    "remove_component": ("ref",),
    "get_component": ("ref",),
    "set_selected_part": ("ref",),
    "add_candidate_part": ("ref",),
    "remove_candidate_part": ("ref", "part_id"),
    "add_net": ("name",),
    "update_net": ("name",),
    "remove_net": ("name",),
    "get_net": ("name",),
    "connect_member": ("net", "member"),
    "disconnect_member": ("net", "member"),
    "connect_members": ("net", "members"),
    "disconnect_members": ("net", "members"),
    "rename_net": ("new_name",),
    "merge_nets": ("source", "target"),
    "split_net": ("name",),
    "set_pinmap": ("ref", "pinmap"),
    "update_pinmap": ("ref", "pinmap"),
    "remove_pinmap": ("ref",),
    "get_pinmap": ("ref",),
    "connect_pin_to_net": ("ref", "pin", "net"),
    "disconnect_pin_from_net": ("ref", "pin"),
    "apply_batch": ("operations",),
    "run_erc": ("project_dir",),
}

OBJECT_FIELDS = {
    "component",
    "metadata",
    "model",
    "other",
    "part",
    "patch",
    "pinmap",
    "selected_part",
}

LIST_FIELDS = {"members", "new_nets", "new_names", "operations"}


def validate_operation_payload(request: OperationRequest) -> ValidationReport:
    report = ValidationReport()
    for field in REQUIRED_FIELDS.get(request.operation, ()):
        if _payload_value(request.payload, field) in (None, ""):
            report.add_error(f"payload.{field} is required for {request.operation}")
    for field in OBJECT_FIELDS:
        if field in request.payload and not isinstance(request.payload[field], dict):
            report.add_error(f"payload.{field} must be an object")
    for field in LIST_FIELDS:
        if field in request.payload and not isinstance(request.payload[field], list):
            report.add_error(f"payload.{field} must be a list")
    if request.operation in {"add_component", "update_component"}:
        component = request.payload.get("component")
        if component is not None and not isinstance(component, dict):
            report.add_error("payload.component must be an object")
    if request.operation == "apply_operation":
        if not request.payload.get("operation"):
            report.add_error("payload.operation is required for apply_operation")
    if report.ok:
        report.add_check("operation payload ok")
    return report


def _payload_value(payload: dict[str, Any], field: str) -> Any:
    if field in payload:
        return payload[field]
    aliases = {
        "name": ("net", "sheet", "rail", "constraint", "calculation"),
        "ref": ("component",),
        "pinmap": ("map",),
    }
    for alias in aliases.get(field, ()):
        value = payload.get(alias)
        if isinstance(value, dict) and field in value:
            return value[field]
        if isinstance(value, str):
            return value
    return None
