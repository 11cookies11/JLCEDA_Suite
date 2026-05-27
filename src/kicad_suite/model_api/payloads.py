"""Operation payload checks for the circuit-model DSL API."""

from __future__ import annotations

from typing import Any

from ..validation.common import ValidationReport
from .commands import OperationRequest


REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    # -- component --
    "add_component": ("ref",),
    "update_component": ("ref", "patch"),
    "remove_component": ("ref",),
    "get_component": ("ref",),
    "set_selected_part": ("ref", "part"),
    "add_candidate_part": ("ref", "part"),
    "remove_candidate_part": ("ref", "part_id"),
    "set_component_ref": ("ref", "value"),
    "set_component_role": ("ref", "value"),
    "set_component_value": ("ref", "value"),
    "set_component_availability": ("ref", "value"),
    "set_component_notes": ("ref",),
    "mark_component_resolved": ("ref",),
    "mark_component_needs_review": ("ref",),
    "mark_component_blocked": ("ref",),
    "assign_component_to_sheet": ("ref", "sheet_name"),
    # -- net --
    "add_net": ("name",),
    "update_net": ("name", "patch"),
    "remove_net": ("name",),
    "get_net": ("name",),
    "connect_member": ("net", "member"),
    "disconnect_member": ("net", "member"),
    "connect_members": ("net", "members"),
    "disconnect_members": ("net", "members"),
    "rename_net": ("old_name", "new_name"),
    "merge_nets": ("source", "target"),
    "split_net": ("name", "new_nets"),
    "set_net_kind": ("name", "value"),
    "set_net_domain": ("name", "value"),
    "set_net_notes": ("name",),
    "set_net_aliases": ("name",),
    "mark_net_global": ("name",),
    "mark_net_power": ("name",),
    "mark_net_high_speed": ("name",),
    "mark_net_debug": ("name",),
    "mark_net_differential_pair": ("name",),
    "assign_net_to_sheet": ("net_name", "sheet_name"),
    # -- pinmap --
    "set_pinmap": ("ref", "pinmap"),
    "update_pinmap": ("ref", "pinmap"),
    "remove_pinmap": ("ref",),
    "get_pinmap": ("ref",),
    "connect_pin_to_net": ("ref", "pin", "net"),
    "disconnect_pin_from_net": ("ref", "pin"),
    "set_pin_name": ("ref", "pin"),
    "set_pin_role": ("ref", "pin"),
    "set_pin_direction": ("ref", "pin"),
    "set_pin_no_connect": ("ref", "pin"),
    "add_pin_alias": ("ref", "pin", "alias"),
    "resolve_pin_alias": ("ref", "pin"),
    # -- procurement --
    "select_part": ("ref", "part"),
    "update_selected_part": ("ref", "part"),
    "replace_selected_part": ("ref", "part"),
    "lock_selected_part": ("ref",),
    "unlock_selected_part": ("ref",),
    # -- batch --
    "apply_batch": ("operations",),
    # -- model lifecycle --
    "diff_model": ("other",),
    "merge_model": ("other",),
    "patch_model": ("patch",),
    "create_project_template": ("project_dir",),
    "create_hardware_project": ("project_dir", "project_id"),
    # -- metadata --
    "set_schema_version": ("value",),
    "set_request_id": ("value",),
    "set_project_id": ("value",),
    "set_topology": ("value",),
    # -- export --
    "run_erc": ("project_dir",),
}

# Collection-to-identity-key mapping for generic collection operations.
_COLLECTION_KEY: dict[str, str] = {
    "components": "ref",
    "nets": "name",
    "calculations": "name",
    "constraints": "name",
    "design_decisions": "title",
    "risks": "key",
    "sheets": "name",
    "power_rails": "name",
}

# Operation prefixes that imply an identifier is required.
_GENERIC_REQUIRE_ID: tuple[str, ...] = (
    "add_", "remove_", "get_", "update_",
    "set_", "mark_", "link_",
)

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

# Payload fields that must be a dict when present.
# NOTE: net, risk, decision, sheet, calculation, constraint, rail are intentionally
# excluded — they serve as string identifiers in some operations (e.g. connect_member)
# and nested objects in others (e.g. add_net).
_DICT_FIELDS = {
    "component", "design_decision",
    "part", "selected_part", "candidate_part",
    "pinmap", "patch", "metadata", "model", "other",
}

# Fields that must be a non-empty list when present.
_NONEMPTY_LIST_FIELDS = {"members", "operations", "new_nets", "new_names"}


def validate_operation_payload(request: OperationRequest) -> ValidationReport:
    """Validate the payload of an operation request.

    Checks required fields, field types, and deep structure constraints.
    """
    report = ValidationReport()

    # 1. Required field presence.
    for field in REQUIRED_FIELDS.get(request.operation, ()):
        if _payload_value(request.payload, field) in (None, ""):
            report.add_error(f"payload.{field} is required for {request.operation}")

    # 2. Generic collection operation checks (covers ~100 operations not in REQUIRED_FIELDS).
    _validate_generic_payload(request, report)

    # 3. Type checks for known object/list fields.
    for field in OBJECT_FIELDS:
        if field in request.payload and not isinstance(request.payload[field], dict):
            report.add_error(f"payload.{field} must be an object")
    for field in LIST_FIELDS:
        if field in request.payload and not isinstance(request.payload[field], list):
            report.add_error(f"payload.{field} must be a list")

    # 4. Ad-hoc checks.
    if request.operation in {"add_component", "update_component"}:
        component = request.payload.get("component")
        if component is not None and not isinstance(component, dict):
            report.add_error("payload.component must be an object")
    if request.operation == "apply_operation":
        if not request.payload.get("operation"):
            report.add_error("payload.operation is required for apply_operation")

    # 5. Deep structural validation.
    validate_payload_structure(request, report)

    if report.ok:
        report.add_check("operation payload ok")
    return report


def _validate_generic_payload(request: OperationRequest, report: ValidationReport) -> None:
    """Validate payloads for operations routed through _generic_collection_operation."""
    collection, id_key = _resolve_collection(request.operation)
    if collection is None:
        return

    op_kind = _generic_operation_kind(request.operation)
    if op_kind is None:
        return

    payload = request.payload

    if op_kind in ("add", "remove", "get", "update"):
        if _payload_identifier(payload, id_key) in (None, ""):
            alias_hint = _id_alias_hint(id_key)
            report.add_error(
                f"payload.{id_key}{alias_hint} is required for {request.operation}"
            )

    if op_kind in ("set",):
        if _payload_identifier(payload, id_key) in (None, ""):
            alias_hint = _id_alias_hint(id_key)
            report.add_error(
                f"payload.{id_key}{alias_hint} is required for {request.operation}"
            )
        if payload.get("value") is None and _field_from_set_operation(request.operation) not in payload:
            report.add_warning(
                f"payload.value is recommended for {request.operation}"
            )

    if op_kind == "update":
        if not isinstance(payload.get("patch"), dict) and not isinstance(payload, dict):
            report.add_error(f"payload.patch must be an object for {request.operation}")

    if op_kind == "search":
        if not payload.get("query"):
            report.add_error(f"payload.query is required for {request.operation}")

    if op_kind == "link":
        if not payload.get("target"):
            report.add_error(f"payload.target is required for {request.operation}")


def validate_payload_structure(request: OperationRequest, report: ValidationReport) -> None:
    """Deep structural checks on nested payload objects."""
    payload = request.payload
    for field in _DICT_FIELDS:
        value = payload.get(field)
        if value is not None and not isinstance(value, dict):
            report.add_error(f"payload.{field} must be an object, got {type(value).__name__}")
    for field in _NONEMPTY_LIST_FIELDS:
        value = payload.get(field)
        if value is not None:
            if not isinstance(value, list):
                report.add_error(f"payload.{field} must be a list, got {type(value).__name__}")
            elif len(value) == 0:
                report.add_warning(f"payload.{field} is an empty list")

    # Validate selected_part / candidate_part shapes.
    for part_field in ("selected_part", "candidate_part", "part"):
        part = payload.get(part_field)
        if isinstance(part, dict):
            if not part.get("part_id") and not part.get("display_name"):
                report.add_warning(f"payload.{part_field} has no part_id or display_name")

    # Validate pinmap shape.
    pinmap = payload.get("pinmap", payload.get("map"))
    if isinstance(pinmap, dict):
        for pin_name, pin_entry in pinmap.items():
            if isinstance(pin_entry, dict):
                net = pin_entry.get("net", "")
                if net and not isinstance(net, str):
                    report.add_error(f"payload.pinmap.{pin_name}.net must be a string")
            elif not isinstance(pin_entry, str):
                report.add_error(f"payload.pinmap.{pin_name} must be a string or object")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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


def _resolve_collection(operation: str) -> tuple[str | None, str | None]:
    """Map an operation name to (collection, identity_key)."""
    for collection, id_key in _COLLECTION_KEY.items():
        singular = collection.rstrip("s")
        if operation.endswith("_" + singular) or operation.endswith("_" + collection):
            return collection, id_key
        if singular in operation or collection in operation:
            for token in operation.split("_"):
                if token == singular or token == collection:
                    return collection, id_key
    # Handle power_rails (underscore in name).
    if "power_rail" in operation:
        return "power_rails", "name"
    if "design_decision" in operation or "_decision" in operation:
        return "design_decisions", "title"
    if "_risk" in operation and operation not in ("run_erc",):
        return "risks", "key"
    return None, None


def _generic_operation_kind(operation: str) -> str | None:
    """Return the sub-operation kind: add, remove, get, update, set, mark, search, list, link."""
    prefixes = [
        ("add_", "add"),
        ("remove_", "remove"),
        ("get_", "get"),
        ("update_", "update"),
        ("set_", "set"),
        ("mark_", "mark"),
        ("search_", "search"),
        ("list_", "list"),
        ("link_", "link"),
    ]
    for prefix, kind in prefixes:
        if operation.startswith(prefix):
            return kind
    return None


def _payload_identifier(payload: dict[str, Any], id_key: str) -> Any:
    """Extract the entity identifier from a payload dict using the expected key and its aliases."""
    if id_key == "ref":
        for key in ("ref", "component"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
            if isinstance(val, dict) and val.get("ref"):
                return val["ref"]
    elif id_key == "name":
        for key in ("name", "rail", "sheet", "constraint", "calculation"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
            if isinstance(val, dict) and val.get("name"):
                return val["name"]
        net = payload.get("net")
        if isinstance(net, str) and net:
            return net
    elif id_key == "title":
        for key in ("title", "decision", "design_decision"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
            if isinstance(val, dict) and val.get("title"):
                return val["title"]
    elif id_key == "key":
        for key in ("key", "risk", "risk_key"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
            if isinstance(val, dict) and val.get("key"):
                return val["key"]
    val = payload.get(id_key)
    if isinstance(val, str) and val:
        return val
    if isinstance(val, dict) and val.get(id_key):
        return val[id_key]
    return None


def _id_alias_hint(id_key: str) -> str:
    hints = {
        "ref": " (or component.ref)",
        "name": " (or net.name / sheet.name / rail.name)",
        "title": " (or decision.title)",
        "key": " (or risk.key)",
    }
    return hints.get(id_key, "")


def _field_from_set_operation(operation: str) -> str:
    """Extract the target field name from set_* / mark_* operations."""
    # Strip known collection prefixes first.
    for prefix in (
        "set_calculation_",
        "set_constraint_",
        "set_rail_",
        "set_risk_",
        "set_sheet_",
        "set_pin_",
        "set_component_",
        "set_net_",
        "set_selected_",
        "set_",
    ):
        if operation.startswith(prefix):
            stripped = operation.removeprefix(prefix)
            return stripped
    # Fallback: take the last underscore-delimited token.
    return operation.rsplit("_", 1)[-1]
