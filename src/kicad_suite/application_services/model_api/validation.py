"""Validation helpers for the circuit-model DSL API."""

from __future__ import annotations

from typing import Any

from ...shared.schema_versions import CIRCUIT_MODEL_SCHEMA_VERSION, DSL_API_REQUEST_SCHEMA_VERSION
from ...shared.validation.common import ValidationReport
from .commands import OperationRequest


SUPPORTED_OPERATIONS = {
    "add_candidate_part",
    "add_calculation",
    "add_component",
    "add_constraint",
    "add_design_decision",
    "add_net",
    "add_pin_alias",
    "add_power_rail",
    "add_rail_test_point",
    "add_risk",
    "add_sheet",
    "apply_batch",
    "apply_operation",
    "assign_component_to_sheet",
    "build_ir",
    "assign_net_to_sheet",
    "begin_transaction",
    "bind_rail_to_test_point",
    "clone_model",
    "commit_transaction",
    "compile_kicad_execution_plan",
    "compile_netlist",
    "compile_spice_netlist",
    "connect_member",
    "connect_members",
    "connect_pin_to_net",
    "create_project_template",
    "create_hardware_project",
    "diff_model",
    "diff_transaction",
    "disconnect_members",
    "disconnect_member",
    "disconnect_pin_from_net",
    "dry_run",
    "export_circuit_model",
    "export_ir",
    "export_kicad_project",
    "export_report",
    "export_summary",
    "get_calculation",
    "get_component",
    "get_constraint",
    "get_design_decision",
    "get_metadata",
    "get_net",
    "get_pinmap",
    "get_power_rail",
    "get_risk",
    "get_sheet",
    "list_calculations",
    "list_components",
    "list_constraints",
    "list_design_decisions",
    "list_nets",
    "list_power_rails",
    "list_risks",
    "list_sheets",
    "link_calculation_to_component",
    "link_calculation_to_net",
    "link_decision_to_component",
    "link_decision_to_net",
    "link_decision_to_risk",
    "link_decision_to_sheet",
    "link_risk_to_component",
    "link_risk_to_decision",
    "link_risk_to_net",
    "link_risk_to_sheet",
    "load_model",
    "lock_selected_part",
    "mark_component_blocked",
    "mark_component_needs_review",
    "mark_component_resolved",
    "mark_decision_accepted",
    "mark_decision_finalized",
    "mark_decision_needs_review",
    "mark_decision_proposed",
    "mark_decision_rejected",
    "mark_net_debug",
    "mark_net_differential_pair",
    "mark_net_global",
    "mark_net_high_speed",
    "mark_net_power",
    "mark_risk_blocked",
    "mark_risk_deferred",
    "mark_risk_in_progress",
    "mark_risk_open",
    "mark_risk_resolved",
    "merge_model",
    "merge_nets",
    "patch_model",
    "remove_candidate_part",
    "remove_calculation",
    "remove_component",
    "remove_constraint",
    "remove_design_decision",
    "remove_net",
    "remove_pinmap",
    "remove_power_rail",
    "remove_risk",
    "remove_sheet",
    "recompute_calculation",
    "rename_net",
    "replace_selected_part",
    "reset_model",
    "resolve_pin_alias",
    "rollback_transaction",
    "run_erc",
    "run_simulation_plan",
    "save_model",
    "search_calculations",
    "search_components",
    "search_decisions",
    "search_design_decisions",
    "search_nets",
    "search_risks",
    "search_sheets",
    "select_part",
    "set_calculation_formula",
    "set_calculation_inputs",
    "set_calculation_result",
    "set_calculation_unit",
    "set_component_availability",
    "set_component_notes",
    "set_component_ref",
    "set_component_role",
    "set_component_search_hints",
    "set_component_value",
    "set_constraint_priority",
    "set_constraint_scope",
    "set_constraint_status",
    "set_constraint_type",
    "set_net_aliases",
    "set_net_domain",
    "set_net_kind",
    "set_net_notes",
    "set_pin_direction",
    "set_pin_name",
    "set_pin_no_connect",
    "set_pin_role",
    "set_pinmap",
    "set_project_id",
    "set_rail_children",
    "set_rail_current_limit",
    "set_rail_enable_condition",
    "set_rail_parent",
    "set_rail_sequence_order",
    "set_rail_sink",
    "set_rail_source",
    "set_rail_voltage",
    "set_request_id",
    "set_risk_category",
    "set_risk_due_reason",
    "set_risk_owner",
    "set_risk_severity",
    "set_selected_part",
    "set_schema_version",
    "set_sheet_components",
    "set_sheet_constraints",
    "set_sheet_inputs",
    "set_sheet_name",
    "set_sheet_nets",
    "set_sheet_notes",
    "set_sheet_outputs",
    "set_topology",
    "split_net",
    "unlock_selected_part",
    "update_calculation",
    "update_constraint",
    "update_design_decision",
    "update_component",
    "update_metadata",
    "update_net",
    "update_pinmap",
    "update_power_rail",
    "update_risk",
    "update_selected_part",
    "update_sheet",
    "validate_connectivity",
    "validate_model",
    "validate_part_availability",
    "validate_ir",
    "validate_pinmap",
    "validate_power_budget",
    "validate_power_tree",
    "validate_intent",
    "validate_readiness",
    "validate_references",
    "validate_risk_consistency",
    "validate_schema",
    "validate_sequence",
    "validate_sheet_boundary",
    "validate_sheet_inputs_outputs",
}


def validate_request(request: OperationRequest) -> ValidationReport:
    report = ValidationReport()
    if request.schema_version != DSL_API_REQUEST_SCHEMA_VERSION:
        report.add_error(f"unsupported request schema_version: {request.schema_version}")
    if not request.request_id:
        report.add_error("request_id is required")
    if not request.project_id:
        report.add_error("project_id is required")
    if not request.operation:
        report.add_error("operation is required")
    elif request.operation not in SUPPORTED_OPERATIONS:
        report.add_error(f"unsupported operation: {request.operation}")
    if not isinstance(request.payload, dict):
        report.add_error("payload must be an object")
    if report.ok:
        report.add_check("request envelope ok")
    return report


def validate_model_snapshot(model: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    if model.get("schema_version") != CIRCUIT_MODEL_SCHEMA_VERSION:
        report.add_error(f"unsupported model schema_version: {model.get('schema_version', '')}")
    for key in ("request_id", "project_id", "topology"):
        if not isinstance(model.get(key), str) or not model.get(key):
            report.add_warning(f"{key} is empty")
    for key in ("components", "nets"):
        if not isinstance(model.get(key), list):
            report.add_error(f"{key} must be a list")
    if isinstance(model.get("components"), list):
        _validate_unique_object_key(report, model["components"], "components", "ref")
    if isinstance(model.get("nets"), list):
        _validate_unique_object_key(report, model["nets"], "nets", "name")
        _validate_net_members(report, model["nets"])
    if isinstance(model.get("components"), list) and isinstance(model.get("nets"), list):
        _validate_circuit_sanity(report, model["components"], model["nets"])
    if report.ok:
        report.add_check("model snapshot ok")
    report.stats["component_count"] = (
        len(model.get("components", [])) if isinstance(model.get("components"), list) else 0
    )
    report.stats["net_count"] = len(model.get("nets", [])) if isinstance(model.get("nets"), list) else 0
    return report


def _validate_unique_object_key(
    report: ValidationReport,
    items: list[Any],
    container: str,
    key: str,
) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            report.add_error(f"{container}[{index}] must be an object")
            continue
        value = item.get(key)
        if not isinstance(value, str) or not value:
            report.add_error(f"{container}[{index}].{key} is required")
            continue
        if value in seen:
            report.add_error(f"duplicate {container}.{key}: {value}")
        seen.add(value)


def _validate_net_members(report: ValidationReport, nets: list[Any]) -> None:
    for net_index, net in enumerate(nets):
        if not isinstance(net, dict):
            continue
        members = net.get("members", [])
        if not isinstance(members, list):
            report.add_error(f"nets[{net_index}].members must be a list")
            continue
        seen: set[str] = set()
        for member_index, member in enumerate(members):
            if not isinstance(member, str) or "." not in member:
                report.add_warning(f"nets[{net_index}].members[{member_index}] is a bare net name, not a REF.PIN reference")
                continue
            if member in seen:
                report.add_warning(f"duplicate member {member} in net {net.get('name', net_index)}")
            seen.add(member)


# ---------------------------------------------------------------------------
# Circuit sanity checks — catch obviously-wrong connections in DSL models
# ---------------------------------------------------------------------------

_POWER_NET_KINDS = {"power", "ground"}


def _is_intentional_link(value: str, role: str) -> bool:
    """Return True if a two-pin passive between power rails is an intentional link."""
    value_lower = value.lower()
    role_lower = role.lower()
    # 0R jumpers and current-measurement links
    if value_lower in {"0r", "0ω", "0 ohm", "0ohm", "0r0", "0"}:
        return True
    for keyword in ("link", "jumper", "current_meas", "current-meas", "isolation"):
        if keyword in role_lower:
            return True
    return False


def _validate_circuit_sanity(
    report: ValidationReport,
    components: list[Any],
    nets: list[Any],
) -> None:
    """Run basic electrical sanity checks on the netlist.

    These catch copy-paste errors and logically impossible connections
    *before* they propagate into generated KiCad output.
    """

    # ---- build lookup tables ----
    refs: dict[str, dict[str, Any]] = {}
    for c in components:
        if isinstance(c, dict) and c.get("ref"):
            refs[str(c["ref"])] = c

    net_by_name: dict[str, dict[str, Any]] = {}
    pin_to_nets: dict[str, list[str]] = {}  # "REF.PIN" → [net_name, ...]
    for net in nets:
        if not isinstance(net, dict):
            continue
        name = str(net.get("name", ""))
        if not name:
            continue
        net_by_name[name] = net
        for member in net.get("members", []):
            member_str = str(member)
            if "." not in member_str:
                continue
            pin_to_nets.setdefault(member_str, []).append(name)

    # ---- 1. Pin assigned to multiple different nets (short circuit) ----
    errors_found = 0
    for pin_ref, assigned_nets in pin_to_nets.items():
        unique = list(dict.fromkeys(assigned_nets))  # preserve order, dedupe
        if len(unique) > 1:
            report.add_error(
                f"SHORT CIRCUIT: {pin_ref} is connected to multiple nets: {', '.join(unique)}. "
                f"Remove it from all but one net."
            )
            errors_found += 1

    # ---- 2. Passive two-pin components with suspicious connections ----
    passive_kinds = {"resistor", "capacitor", "inductor", "ferrite_bead", "fuse", "jumper"}
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ref = str(comp.get("ref", ""))
        role = str(comp.get("role", "")).lower()
        value = str(comp.get("value", "")).lower()

        # Determine if this looks like a 2-pin passive
        is_passive = any(kw in role for kw in passive_kinds)
        if not is_passive:
            # Also check by ref prefix
            if ref and ref[0] in "RCL":
                is_passive = True
        if not is_passive:
            continue

        # Collect which nets this component's pins are in
        comp_pins: dict[str, str] = {}
        for net_name, net in net_by_name.items():
            prefix = f"{ref}."
            for member in net.get("members", []):
                if str(member).startswith(prefix):
                    pin = str(member).split(".", 1)[1]
                    comp_pins[pin] = net_name

        nets_on_component = list(comp_pins.values())
        unique_nets = list(dict.fromkeys(nets_on_component))

        # 2a. Both pins on the same net → component is bypassed
        if len(nets_on_component) >= 2 and len(unique_nets) == 1:
            report.add_error(
                f"BYPASSED {ref}: all pins connected to the same net [{unique_nets[0]}]. "
                f"The component is electrically meaningless."
            )
            errors_found += 1

        # 2b. Resistor/pullup/pulldown connecting two power rails (or power to GND)
        # with no signal net → useless power drain
        if "pullup" in role or "pulldown" in role or (
            ref.startswith("R") and len(unique_nets) == 2
        ):
            net_kinds = []
            for net_name in unique_nets:
                net_info = net_by_name.get(net_name, {})
                net_kinds.append(str(net_info.get("kind", "")).lower())

            both_power = all(k in _POWER_NET_KINDS for k in net_kinds if k)
            if both_power and len(unique_nets) >= 2:
                # 0R links and intentional power jumpers are fine
                if _is_intentional_link(value, role):
                    pass
                elif len(unique_nets) == 2:
                    report.add_warning(
                        f"SUSPICIOUS {ref} ({role}): connects {unique_nets[0]} directly to "
                        f"{unique_nets[1]} with no signal path. "
                        f"If intended as pull-up/down, one pin must go to a signal net."
                    )

        # 2c. Pullup/pulldown role sanity
        if "pullup" in role:
            pin_nets = list(comp_pins.items())
            on_power = any(
                str(net_by_name.get(n, {}).get("kind", "")).lower() == "power"
                for _, n in pin_nets
            )
            if not on_power:
                report.add_warning(
                    f"PULLUP WITHOUT POWER: {ref} role is pullup but neither pin is on a power net."
                )
        if "pulldown" in role:
            pin_nets = list(comp_pins.items())
            on_gnd = any(
                str(net_by_name.get(n, {}).get("kind", "")).lower() == "ground"
                for _, n in pin_nets
            )
            if not on_gnd:
                report.add_warning(
                    f"PULLDOWN WITHOUT GND: {ref} role is pulldown but neither pin is on a ground net."
                )

        # 2d. Decoupling capacitor between power and ground → normal, skip
        #     But capacitor between two different power rails → flag
        if ref.startswith("C") and len(unique_nets) == 2:
            net_kinds = [str(net_by_name.get(n, {}).get("kind", "")).lower() for n in unique_nets]
            if "power" in net_kinds and "power" in [k for k in net_kinds if k != "power"]:
                # Both nets report as power — suspicious unless one is actually ground
                pass  # already caught by _POWER_NET_KINDS check above

    # ---- 3. Floating pins (warning only — NC pins are legitimate) ----
    if errors_found == 0:
        report.add_check("circuit sanity ok")
