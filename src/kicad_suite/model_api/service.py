"""Service entry point for controlled circuit-model DSL operations."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..compile_kicad_execution_plan import compile_plan
from ..kicad_erc_runner import run as run_erc
from ..kicad_project_writer import write_project
from ..pipeline_coordinator import build_netlist
from ..simulation_planner import write_simulation_artifacts
from ..validation.common import ValidationReport
from .commands import OperationRequest, operation_request_from_dict
from .external_tools import external_tool_env, external_tools_config_from_payload
from .model import empty_model, normalize_model, snapshot
from .payloads import validate_operation_payload
from .repository import CircuitModelRepository
from .results import ApiError, OperationResult
from .validation import validate_model_snapshot, validate_request


class ModelApiService:
    """Apply typed DSL API requests to an in-memory circuit model."""

    def __init__(
        self,
        model: dict[str, Any] | None = None,
        repository: CircuitModelRepository | None = None,
    ) -> None:
        self.repository = repository
        if model is not None:
            self.model = normalize_model(model)
        elif repository is not None:
            self.model = repository.load()
        else:
            self.model = empty_model("", "")
        self.transaction_base: dict[str, Any] | None = None

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "ModelApiService":
        return cls(model)

    @classmethod
    def from_repository(cls, repository: CircuitModelRepository) -> "ModelApiService":
        return cls(repository=repository)

    def handle_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.handle(operation_request_from_dict(payload)).to_dict()

    def handle(self, request: OperationRequest) -> OperationResult:
        request_report = validate_request(request)
        before = snapshot(self.model)
        if not request_report.ok:
            return self._failure(request, request_report, "INVALID_PAYLOAD", request_report.errors[0], before=before)
        payload_report = validate_operation_payload(request)
        if not payload_report.ok:
            return self._failure(request, payload_report, "INVALID_PAYLOAD", payload_report.errors[0], before=before)

        operation = request.operation
        if operation == "load_model":
            return self._load_model(request, before)
        if operation == "validate_model":
            return self._validate_model(request, before)
        if operation == "add_component":
            return self._add_component(request, before)
        if operation == "update_component":
            return self._update_component(request, before)
        if operation == "remove_component":
            return self._remove_component(request, before)
        if operation == "set_selected_part":
            return self._set_selected_part(request, before)
        if operation == "add_candidate_part":
            return self._add_candidate_part(request, before)
        if operation == "remove_candidate_part":
            return self._remove_candidate_part(request, before)
        if operation == "add_net":
            return self._add_net(request, before)
        if operation == "update_net":
            return self._update_net(request, before)
        if operation == "remove_net":
            return self._remove_net(request, before)
        if operation == "connect_member":
            return self._connect_member(request, before)
        if operation == "disconnect_member":
            return self._disconnect_member(request, before)
        if operation == "get_component":
            return self._get_component(request, before)
        if operation == "get_net":
            return self._get_net(request, before)
        if operation == "list_components":
            return self._list_items(request, before, "components")
        if operation == "list_nets":
            return self._list_items(request, before, "nets")
        extended = self._handle_extended_operation(request, before)
        if extended is not None:
            return extended

        return self._failure(
            request,
            request_report,
            "UNSUPPORTED_OPERATION",
            f"unsupported operation: {operation}",
            before=before,
        )

    def _load_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        model = request.payload.get("model")
        if not isinstance(model, dict):
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "payload.model must be an object",
                before=before,
            )
        candidate = normalize_model(model)
        report = validate_model_snapshot(candidate)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        should_commit = not request.options.dry_run and not request.options.validate_only and request.options.commit
        if should_commit:
            self._commit(candidate, request, before, [{"path": "$", "op": "replace"}])
        after = snapshot(self.model if should_commit else candidate)
        return self._success(
            request,
            report,
            {"loaded": True},
            before,
            after,
            [{"path": "$", "op": "replace"}],
            ["$"],
        )

    def _validate_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        report = validate_model_snapshot(self.model)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        return self._success(request, report, {"valid": True}, before, snapshot(self.model), [], [])

    def _add_component(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        component = request.payload.get("component", request.payload)
        if not isinstance(component, dict):
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "component payload must be an object",
                before=before,
            )
        ref = str(component.get("ref", ""))
        if not ref:
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "component.ref is required",
                "payload.ref",
                before,
            )
        if self._find_by_key("components", "ref", ref) is not None:
            return self._failure(
                request,
                ValidationReport(),
                "ALREADY_EXISTS",
                f"component {ref} already exists",
                "payload.ref",
                before,
            )

        after = snapshot(self.model)
        after["components"].append(dict(component))
        return self._apply_success(request, {"ref": ref}, before, after, f"components[{ref}]", "add")

    def _update_component(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        patch = request.payload.get("patch", request.payload.get("component", {}))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        if not isinstance(patch, dict):
            return self._payload_error(request, before, "component patch must be an object", "payload.patch")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")

        after = snapshot(self.model)
        updated = {**after["components"][component_index], **patch, "ref": ref}
        after["components"][component_index] = updated
        return self._apply_success(request, {"ref": ref}, before, after, f"components[{ref}]", "replace")

    def _remove_component(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")

        after = snapshot(self.model)
        after["components"].pop(component_index)
        removed_prefix = f"{ref}."
        for net in after.get("nets", []):
            if isinstance(net, dict) and isinstance(net.get("members"), list):
                net["members"] = [member for member in net["members"] if not str(member).startswith(removed_prefix)]
        return self._apply_success(request, {"ref": ref}, before, after, f"components[{ref}]", "remove")

    def _set_selected_part(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        part = request.payload.get("part", request.payload.get("selected_part"))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        if not isinstance(part, dict):
            return self._payload_error(request, before, "selected part must be an object", "payload.part")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")

        after = snapshot(self.model)
        after["components"][component_index]["selected_part"] = dict(part)
        return self._apply_success(
            request,
            {"ref": ref, "selected_part": part},
            before,
            after,
            f"components[{ref}].selected_part",
            "replace",
        )

    def _add_candidate_part(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        part = request.payload.get("part", request.payload.get("candidate_part"))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        if not isinstance(part, dict):
            return self._payload_error(request, before, "candidate part must be an object", "payload.part")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")

        after = snapshot(self.model)
        candidates = after["components"][component_index].setdefault("candidate_parts", [])
        if not isinstance(candidates, list):
            return self._payload_error(request, before, f"component {ref} candidate_parts must be a list")
        part_id = str(part.get("part_id", ""))
        part_exists = any(
            isinstance(candidate, dict) and candidate.get("part_id") == part_id for candidate in candidates
        )
        if part_id and part_exists:
            return self._failure(
                request,
                ValidationReport(),
                "ALREADY_EXISTS",
                f"candidate part {part_id} already exists on {ref}",
                "payload.part.part_id",
                before,
            )
        candidates.append(dict(part))
        return self._apply_success(
            request,
            {"ref": ref, "part": part},
            before,
            after,
            f"components[{ref}].candidate_parts",
            "add",
        )

    def _remove_candidate_part(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        part_id = str(request.payload.get("part_id", ""))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        if not part_id:
            return self._payload_error(request, before, "candidate part_id is required", "payload.part_id")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")

        after = snapshot(self.model)
        candidates = after["components"][component_index].get("candidate_parts", [])
        if not isinstance(candidates, list):
            return self._payload_error(request, before, f"component {ref} candidate_parts must be a list")
        next_candidates = [
            candidate
            for candidate in candidates
            if not (isinstance(candidate, dict) and str(candidate.get("part_id", "")) == part_id)
        ]
        if len(next_candidates) == len(candidates):
            return self._not_found(request, before, f"candidate part {part_id} not found", "payload.part_id")
        after["components"][component_index]["candidate_parts"] = next_candidates
        return self._apply_success(
            request,
            {"ref": ref, "part_id": part_id},
            before,
            after,
            f"components[{ref}].candidate_parts[{part_id}]",
            "remove",
        )

    def _add_net(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        net = request.payload.get("net")
        net_payload = net if isinstance(net, dict) else request.payload
        if not isinstance(net_payload, dict):
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "net payload must be an object",
                before=before,
            )
        name = str(net_payload.get("name", ""))
        if not name:
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "net.name is required",
                "payload.name",
                before,
            )
        if self._find_by_key("nets", "name", name) is not None:
            return self._failure(
                request,
                ValidationReport(),
                "ALREADY_EXISTS",
                f"net {name} already exists",
                "payload.name",
                before,
            )

        after = snapshot(self.model)
        after["nets"].append(dict(net_payload))
        return self._apply_success(request, {"name": name}, before, after, f"nets[{name}]", "add")

    def _update_net(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        name = str(request.payload.get("name", request.payload.get("net", "")))
        patch = request.payload.get("patch", request.payload.get("net_patch", {}))
        if not name:
            return self._payload_error(request, before, "net name is required", "payload.name")
        if not isinstance(patch, dict):
            return self._payload_error(request, before, "net patch must be an object", "payload.patch")
        net_index = self._find_index_by_key("nets", "name", name)
        if net_index is None:
            return self._not_found(request, before, f"net {name} not found", "payload.name")

        after = snapshot(self.model)
        updated = {**after["nets"][net_index], **patch, "name": name}
        after["nets"][net_index] = updated
        return self._apply_success(request, {"name": name}, before, after, f"nets[{name}]", "replace")

    def _remove_net(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        name = str(request.payload.get("name", request.payload.get("net", "")))
        if not name:
            return self._payload_error(request, before, "net name is required", "payload.name")
        net_index = self._find_index_by_key("nets", "name", name)
        if net_index is None:
            return self._not_found(request, before, f"net {name} not found", "payload.name")

        after = snapshot(self.model)
        after["nets"].pop(net_index)
        return self._apply_success(request, {"name": name}, before, after, f"nets[{name}]", "remove")

    def _connect_member(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        net_name = str(request.payload.get("net", ""))
        member = str(request.payload.get("member", ""))
        if not net_name:
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "payload.net is required",
                "payload.net",
                before,
            )
        if not member:
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                "payload.member is required",
                "payload.member",
                before,
            )
        net_index = self._find_index_by_key("nets", "name", net_name)
        if net_index is None:
            return self._failure(
                request,
                ValidationReport(),
                "NOT_FOUND",
                f"net {net_name} not found",
                "payload.net",
                before,
            )

        after = snapshot(self.model)
        members = after["nets"][net_index].setdefault("members", [])
        if not isinstance(members, list):
            return self._failure(
                request,
                ValidationReport(),
                "INVALID_PAYLOAD",
                f"net {net_name} members must be a list",
                before=before,
            )
        if member not in members:
            members.append(member)
        path = f"nets[{net_name}].members[{member}]"
        return self._apply_success(request, {"net": net_name, "member": member}, before, after, path, "add")

    def _disconnect_member(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        net_name = str(request.payload.get("net", ""))
        member = str(request.payload.get("member", ""))
        if not net_name:
            return self._payload_error(request, before, "payload.net is required", "payload.net")
        if not member:
            return self._payload_error(request, before, "payload.member is required", "payload.member")
        net_index = self._find_index_by_key("nets", "name", net_name)
        if net_index is None:
            return self._not_found(request, before, f"net {net_name} not found", "payload.net")

        after = snapshot(self.model)
        members = after["nets"][net_index].get("members", [])
        if not isinstance(members, list):
            return self._payload_error(request, before, f"net {net_name} members must be a list")
        if member not in members:
            return self._not_found(request, before, f"member {member} not found in {net_name}", "payload.member")
        after["nets"][net_index]["members"] = [item for item in members if item != member]
        path = f"nets[{net_name}].members[{member}]"
        return self._apply_success(request, {"net": net_name, "member": member}, before, after, path, "remove")

    def _get_component(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        component = self._find_by_key("components", "ref", ref)
        if component is None:
            return self._failure(
                request,
                ValidationReport(),
                "NOT_FOUND",
                f"component {ref} not found",
                "payload.ref",
                before,
            )
        return self._success(
            request,
            ValidationReport(checks=["component found"]),
            {"component": component},
            before,
            snapshot(self.model),
            [],
            [],
        )

    def _get_net(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        name = str(request.payload.get("name", request.payload.get("net", "")))
        net = self._find_by_key("nets", "name", name)
        if net is None:
            return self._failure(
                request,
                ValidationReport(),
                "NOT_FOUND",
                f"net {name} not found",
                "payload.name",
                before,
            )
        return self._success(
            request,
            ValidationReport(checks=["net found"]),
            {"net": net},
            before,
            snapshot(self.model),
            [],
            [],
        )

    def _list_items(self, request: OperationRequest, before: dict[str, Any], key: str) -> OperationResult:
        report = ValidationReport(
            checks=[f"{key} listed"],
            stats={f"{key}_count": len(self.model.get(key, []))},
        )
        return self._success(
            request,
            report,
            {key: snapshot(self.model.get(key, []))},
            before,
            snapshot(self.model),
            [],
            [],
        )

    def _handle_extended_operation(
        self,
        request: OperationRequest,
        before: dict[str, Any],
    ) -> OperationResult | None:
        operation = request.operation
        if operation in {"save_model", "export_circuit_model"}:
            return self._export_circuit_model(request, before)
        if operation == "clone_model":
            return self._read_result(request, before, {"model": snapshot(self.model)})
        if operation == "reset_model":
            return self._replace_model(
                request,
                before,
                empty_model(request.request_id, request.project_id, request.topology),
            )
        if operation == "diff_model":
            return self._diff_model(request, before)
        if operation == "patch_model":
            return self._patch_model(request, before)
        if operation == "merge_model":
            return self._merge_model(request, before)
        if operation in {
            "get_metadata",
            "set_schema_version",
            "set_request_id",
            "set_project_id",
            "set_topology",
            "update_metadata",
        }:
            return self._metadata_operation(request, before)
        if operation in {"connect_members", "disconnect_members", "rename_net", "merge_nets", "split_net"}:
            return self._net_collection_operation(request, before)
        if operation.startswith("set_net_") or operation.startswith("mark_net_"):
            return self._net_field_operation(request, before)
        if operation in {
            "set_component_ref",
            "set_component_role",
            "set_component_value",
            "set_component_notes",
            "set_component_availability",
            "mark_component_resolved",
            "mark_component_needs_review",
            "mark_component_blocked",
            "assign_component_to_sheet",
        }:
            return self._component_field_operation(request, before)
        if operation in {"select_part", "update_selected_part", "replace_selected_part"}:
            return self._set_selected_part(request, before)
        if operation in {
            "set_pinmap",
            "update_pinmap",
            "remove_pinmap",
            "get_pinmap",
            "connect_pin_to_net",
            "disconnect_pin_from_net",
            "set_pin_name",
            "set_pin_role",
            "set_pin_direction",
            "set_pin_no_connect",
            "add_pin_alias",
            "resolve_pin_alias",
        }:
            return self._pinmap_operation(request, before)
        if operation in {"begin_transaction", "commit_transaction", "rollback_transaction", "diff_transaction"}:
            return self._transaction_operation(request, before)
        if operation in {"apply_operation", "apply_batch", "dry_run"}:
            return self._batch_operation(request, before)
        if operation.startswith("validate_"):
            return self._validation_operation(request, before)
        if operation in {"compile_netlist", "compile_kicad_execution_plan"}:
            return self._compile_operation(request, before)
        if operation in {"export_kicad_project", "run_erc", "run_simulation_plan"}:
            return self._external_tool_operation(request, before)
        if operation in {"export_summary", "export_report"}:
            return self._export_report(request, before)

        collection = self._collection_for_operation(operation)
        if collection is not None:
            return self._generic_collection_operation(request, before, collection[0], collection[1])
        return None

    def _metadata_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        operation = request.operation
        if operation == "get_metadata":
            keys = ("schema_version", "request_id", "project_id", "topology")
            return self._read_result(request, before, {"metadata": {key: self.model.get(key, "") for key in keys}})
        field_by_operation = {
            "set_schema_version": "schema_version",
            "set_request_id": "request_id",
            "set_project_id": "project_id",
            "set_topology": "topology",
        }
        after = snapshot(self.model)
        if operation == "update_metadata":
            metadata = request.payload.get("metadata", request.payload)
            if not isinstance(metadata, dict):
                return self._payload_error(request, before, "metadata must be an object", "payload.metadata")
            for key in ("schema_version", "request_id", "project_id", "topology"):
                if key in metadata:
                    after[key] = str(metadata[key])
            return self._apply_success(request, {"metadata": metadata}, before, after, "$.metadata", "replace")
        field = field_by_operation[operation]
        value = request.payload.get("value", request.payload.get(field, ""))
        if not value:
            return self._payload_error(request, before, f"{field} value is required", f"payload.{field}")
        after[field] = str(value)
        return self._apply_success(request, {field: str(value)}, before, after, field, "replace")

    def _component_field_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")
        after = snapshot(self.model)
        component = after["components"][component_index]
        operation = request.operation
        if operation == "set_component_ref":
            next_ref = str(request.payload.get("value", request.payload.get("new_ref", "")))
            if not next_ref:
                return self._payload_error(request, before, "new ref is required", "payload.new_ref")
            if self._find_by_key("components", "ref", next_ref) is not None:
                return self._failure(
                    request,
                    ValidationReport(),
                    "ALREADY_EXISTS",
                    f"component {next_ref} already exists",
                    "payload.new_ref",
                    before,
                )
            component["ref"] = next_ref
            self._rename_member_prefix(after, ref, next_ref)
            return self._apply_success(request, {"ref": next_ref}, before, after, f"components[{ref}].ref", "replace")
        field_map = {
            "set_component_role": "role",
            "set_component_value": "value",
            "set_component_notes": "notes",
            "set_component_availability": "availability_status",
        }
        status_map = {
            "mark_component_resolved": "resolved",
            "mark_component_needs_review": "needs_review",
            "mark_component_blocked": "blocked",
        }
        if operation in field_map:
            field = field_map[operation]
            component[field] = request.payload.get("value", request.payload.get(field, [] if field == "notes" else ""))
        elif operation in status_map:
            component["status"] = status_map[operation]
            if operation == "mark_component_blocked":
                component["blocked_reason"] = str(request.payload.get("reason", ""))
        elif operation == "assign_component_to_sheet":
            component["sheet"] = str(request.payload.get("sheet", request.payload.get("sheet_name", "")))
        return self._apply_success(request, {"ref": component["ref"]}, before, after, f"components[{ref}]", "replace")

    def _net_field_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        name = str(request.payload.get("name", request.payload.get("net", "")))
        if not name:
            return self._payload_error(request, before, "net name is required", "payload.name")
        net_index = self._find_index_by_key("nets", "name", name)
        if net_index is None:
            return self._not_found(request, before, f"net {name} not found", "payload.name")
        after = snapshot(self.model)
        net = after["nets"][net_index]
        field_map = {
            "set_net_kind": "kind",
            "set_net_notes": "notes",
            "set_net_aliases": "aliases",
            "set_net_domain": "domain",
        }
        mark_map = {
            "mark_net_global": ("global", True),
            "mark_net_power": ("power", True),
            "mark_net_high_speed": ("high_speed", True),
            "mark_net_debug": ("debug", True),
            "mark_net_differential_pair": ("differential_pair", True),
        }
        if request.operation in field_map:
            field = field_map[request.operation]
            default = [] if field in {"notes", "aliases"} else ""
            net[field] = request.payload.get("value", request.payload.get(field, default))
        elif request.operation in mark_map:
            key, value = mark_map[request.operation]
            net.setdefault("flags", {})[key] = value
        return self._apply_success(request, {"name": name}, before, after, f"nets[{name}]", "replace")

    def _net_collection_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        operation = request.operation
        if operation in {"connect_members", "disconnect_members"}:
            net_name = str(request.payload.get("net", ""))
            members = request.payload.get("members", [])
            if not isinstance(members, list):
                return self._payload_error(request, before, "members must be a list", "payload.members")
            after = snapshot(self.model)
            net_index = self._find_index_in(after, "nets", "name", net_name)
            if net_index is None:
                return self._not_found(request, before, f"net {net_name} not found", "payload.net")
            net_members = after["nets"][net_index].setdefault("members", [])
            if not isinstance(net_members, list):
                return self._payload_error(request, before, f"net {net_name} members must be a list")
            if operation == "connect_members":
                for member in members:
                    member_str = str(member)
                    if member_str not in net_members:
                        net_members.append(member_str)
            else:
                remove = {str(member) for member in members}
                net_members[:] = [member for member in net_members if member not in remove]
            return self._apply_success(
                request,
                {"net": net_name, "members": members},
                before,
                after,
                f"nets[{net_name}]",
                "replace",
            )
        if operation == "rename_net":
            old_name = str(request.payload.get("old_name", request.payload.get("name", "")))
            new_name = str(request.payload.get("new_name", ""))
            if not old_name or not new_name:
                return self._payload_error(request, before, "old_name and new_name are required")
            after = snapshot(self.model)
            net_index = self._find_index_in(after, "nets", "name", old_name)
            if net_index is None:
                return self._not_found(request, before, f"net {old_name} not found", "payload.old_name")
            after["nets"][net_index]["name"] = new_name
            return self._apply_success(request, {"name": new_name}, before, after, f"nets[{old_name}].name", "replace")
        if operation == "merge_nets":
            source = str(request.payload.get("source", ""))
            target = str(request.payload.get("target", ""))
            return self._merge_nets(request, before, source, target)
        if operation == "split_net":
            return self._split_net(request, before)
        return None  # type: ignore[return-value]

    def _collection_for_operation(self, operation: str) -> tuple[str, str] | None:
        mapping = {
            "component": ("components", "ref"),
            "calculation": ("calculations", "name"),
            "constraint": ("constraints", "name"),
            "design_decision": ("design_decisions", "title"),
            "net": ("nets", "name"),
            "risk": ("risks", "key"),
            "sheet": ("sheets", "name"),
            "power_rail": ("power_rails", "name"),
        }
        aliases = {
            "components": ("components", "ref"),
            "decisions": ("design_decisions", "title"),
            "design_decisions": ("design_decisions", "title"),
            "nets": ("nets", "name"),
            "power_rails": ("power_rails", "name"),
        }
        for singular, collection in mapping.items():
            if operation.endswith(f"_{singular}") or f"_{singular}_" in operation:
                return collection
        for token, collection in aliases.items():
            if operation.endswith(f"_{token}") or f"_{token}_" in operation:
                return collection
        return None

    def _generic_collection_operation(
        self,
        request: OperationRequest,
        before: dict[str, Any],
        collection: str,
        id_key: str,
    ) -> OperationResult:
        operation = request.operation
        self.model.setdefault(collection, [])
        if operation.startswith("list_"):
            return self._list_items(request, before, collection)
        if operation.startswith("search_"):
            query = str(request.payload.get("query", "")).lower()
            items = [
                item
                for item in self.model.get(collection, [])
                if isinstance(item, dict) and query in json.dumps(item, ensure_ascii=False).lower()
            ]
            return self._read_result(request, before, {collection: snapshot(items)})
        item_id = self._payload_identifier(request, id_key)
        if operation.startswith("get_"):
            item = self._find_by_key(collection, id_key, item_id)
            if item is None:
                return self._not_found(request, before, f"{collection} {item_id} not found", f"payload.{id_key}")
            return self._read_result(request, before, {collection.rstrip("s"): item})
        if operation.startswith("add_"):
            item = request.payload.get(collection.rstrip("s"), request.payload)
            if not isinstance(item, dict):
                return self._payload_error(request, before, f"{collection} payload must be an object")
            item_id = str(item.get(id_key, item_id))
            if not item_id:
                return self._payload_error(request, before, f"{id_key} is required", f"payload.{id_key}")
            if self._find_by_key(collection, id_key, item_id) is not None:
                return self._failure(
                    request,
                    ValidationReport(),
                    "ALREADY_EXISTS",
                    f"{collection} {item_id} already exists",
                    f"payload.{id_key}",
                    before,
                )
            after = snapshot(self.model)
            after.setdefault(collection, []).append(dict(item, **{id_key: item_id}))
            return self._apply_success(request, {id_key: item_id}, before, after, f"{collection}[{item_id}]", "add")
        index = self._find_index_by_key(collection, id_key, item_id)
        if index is None:
            return self._not_found(request, before, f"{collection} {item_id} not found", f"payload.{id_key}")
        after = snapshot(self.model)
        if operation.startswith("remove_"):
            after[collection].pop(index)
            return self._apply_success(request, {id_key: item_id}, before, after, f"{collection}[{item_id}]", "remove")
        patch = request.payload.get("patch", request.payload)
        if not isinstance(patch, dict):
            return self._payload_error(request, before, "patch must be an object", "payload.patch")
        if operation.startswith("mark_risk_"):
            patch = {**patch, "status": operation.removeprefix("mark_risk_")}
        elif operation.startswith("mark_decision_"):
            patch = {**patch, "status": operation.removeprefix("mark_decision_")}
        elif operation.startswith("set_"):
            field = self._field_from_set_operation(operation)
            patch = {field: request.payload.get("value", request.payload.get(field, ""))}
        elif operation.startswith("link_"):
            field = operation.rsplit("_to_", 1)[-1] + "s"
            values = after[collection][index].setdefault(field, [])
            if isinstance(values, list):
                values.append(str(request.payload.get("target", request.payload.get(field.rstrip("s"), ""))))
                patch = {}
        after[collection][index] = {**after[collection][index], **patch, id_key: item_id}
        return self._apply_success(request, {id_key: item_id}, before, after, f"{collection}[{item_id}]", "replace")

    def _pinmap_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        index = self._find_index_by_key("components", "ref", ref)
        if index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")
        if request.operation == "get_pinmap":
            component = self.model["components"][index]
            return self._read_result(request, before, {"pinmap": snapshot(component.get("pinmap", {}))})
        after = snapshot(self.model)
        component = after["components"][index]
        if request.operation == "remove_pinmap":
            component.pop("pinmap", None)
            return self._apply_success(request, {"ref": ref}, before, after, f"components[{ref}].pinmap", "remove")
        pinmap = component.setdefault("pinmap", {})
        if not isinstance(pinmap, dict):
            return self._payload_error(request, before, f"component {ref} pinmap must be an object")
        if request.operation in {"set_pinmap", "update_pinmap"}:
            payload_pinmap = request.payload.get("pinmap", {})
            if not isinstance(payload_pinmap, dict):
                return self._payload_error(request, before, "pinmap must be an object", "payload.pinmap")
            component["pinmap"] = payload_pinmap if request.operation == "set_pinmap" else {**pinmap, **payload_pinmap}
            return self._apply_success(request, {"ref": ref}, before, after, f"components[{ref}].pinmap", "replace")
        pin = str(request.payload.get("pin", ""))
        if not pin:
            return self._payload_error(request, before, "pin is required", "payload.pin")
        pin_entry = pinmap.setdefault(pin, {})
        if not isinstance(pin_entry, dict):
            return self._payload_error(request, before, f"pinmap entry {pin} must be an object")
        if request.operation == "connect_pin_to_net":
            net = str(request.payload.get("net", ""))
            pin_entry["net"] = net
            self._connect_member_in_model(after, net, f"{ref}.{pin}")
        elif request.operation == "disconnect_pin_from_net":
            net = str(pin_entry.pop("net", request.payload.get("net", "")))
            self._disconnect_member_in_model(after, net, f"{ref}.{pin}")
        elif request.operation == "set_pin_no_connect":
            pin_entry["no_connect"] = bool(request.payload.get("enabled", True))
        elif request.operation == "add_pin_alias":
            pin_entry.setdefault("aliases", []).append(str(request.payload.get("alias", "")))
        elif request.operation == "resolve_pin_alias":
            pin_entry["resolved_alias"] = str(request.payload.get("alias", ""))
        else:
            field = self._field_from_set_operation(request.operation)
            pin_entry[field] = request.payload.get("value", request.payload.get(field, ""))
        return self._apply_success(
            request,
            {"ref": ref, "pin": pin},
            before,
            after,
            f"components[{ref}].pinmap[{pin}]",
            "replace",
        )

    def _transaction_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        if request.operation == "begin_transaction":
            if self.transaction_base is not None:
                return self._failure(
                    request,
                    ValidationReport(),
                    "TX_ALREADY_ACTIVE",
                    "transaction already active",
                    before=before,
                )
            self.transaction_base = before
            return self._read_result(request, before, {"transaction": {"status": "active"}})
        if request.operation == "rollback_transaction":
            if self.transaction_base is None:
                return self._failure(
                    request,
                    ValidationReport(),
                    "TX_NOT_ACTIVE",
                    "transaction is not active",
                    before=before,
                )
            base = snapshot(self.transaction_base)
            self.transaction_base = None
            self._commit(base, request, before, [])
            return self._success(
                request,
                ValidationReport(checks=["transaction rolled back"]),
                {},
                before,
                base,
                [],
                [],
            )
        if request.operation == "commit_transaction":
            self.transaction_base = None
            if self.repository is not None:
                self.repository.save(self.model)
            return self._read_result(request, before, {"transaction": {"status": "committed"}})
        if self.transaction_base is None:
            return self._failure(
                request,
                ValidationReport(),
                "TX_NOT_ACTIVE",
                "transaction is not active",
                before=before,
            )
        diff = self._simple_diff(self.transaction_base, self.model)
        return self._read_result(request, before, {"diff": diff})

    def _batch_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        if request.operation == "apply_operation":
            operations = [request.payload]
        else:
            operations = request.payload.get("operations", [])
        if not isinstance(operations, list):
            return self._payload_error(request, before, "operations must be a list", "payload.operations")
        temp = ModelApiService.from_model(snapshot(self.model))
        all_diff: list[dict[str, Any]] = []
        for index, item in enumerate(operations):
            if not isinstance(item, dict):
                return self._payload_error(request, before, f"operations[{index}] must be an object")
            child = OperationRequest(
                request_id=f"{request.request_id}:{index}",
                project_id=request.project_id,
                topology=request.topology,
                operation=str(item.get("operation", "")),
                payload=item.get("payload", {})
                if isinstance(item.get("payload", {}), dict)
                else {},
                options=request.options,
            )
            result = temp.handle(child)
            if not result.success:
                return self._failure(
                    request,
                    result.diagnostics,
                    "VALIDATION_FAILED",
                    result.errors[0].message,
                    before=before,
                )
            all_diff.extend(result.diff)
        if request.operation != "dry_run" and not request.options.dry_run and request.options.commit:
            self._commit(temp.model, request, before, all_diff)
        after = snapshot(temp.model)
        return self._success(
            request,
            validate_model_snapshot(after),
            {"operation_count": len(operations)},
            before,
            after,
            all_diff,
            [str(item.get("path", "")) for item in all_diff],
        )

    def _validation_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        report = validate_model_snapshot(self.model)
        strict_references = request.operation in {
            "validate_connectivity",
            "validate_readiness",
            "validate_references",
        }
        self._validate_references(report, self.model, strict=strict_references)
        if request.operation in {
            "validate_connectivity",
            "validate_readiness",
            "validate_sheet_boundary",
            "validate_sheet_inputs_outputs",
        }:
            self._validate_sheet_boundaries(report, self.model)
        if request.operation in {"validate_part_availability", "validate_readiness"}:
            self._validate_parts(report, self.model)
        if request.operation in {
            "validate_power_tree",
            "validate_power_budget",
            "validate_sequence",
            "validate_readiness",
        }:
            self._validate_power(report, self.model, strict=request.operation == "validate_readiness")
        if request.operation in {"validate_pinmap", "validate_readiness"}:
            self._validate_pinmaps(report, self.model)
        if request.operation in {"validate_risk_consistency", "validate_readiness"}:
            self._validate_risks(report, self.model)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        return self._success(request, report, {"valid": True}, before, snapshot(self.model), [], [])

    def _compile_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        try:
            netlist = build_netlist(self.model)
            if request.operation == "compile_netlist":
                return self._read_result(request, before, {"netlist": netlist})
            plan = compile_plan(self.model, netlist)
            return self._read_result(request, before, {"execution_plan": plan})
        except Exception as exc:
            return self._failure(request, ValidationReport(), "VALIDATION_FAILED", str(exc), before=before)

    def _external_tool_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        try:
            config = external_tools_config_from_payload(request.payload)
            if request.operation == "run_simulation_plan":
                simulation = config.get("simulation", {}) if isinstance(config.get("simulation"), dict) else {}
                output_dir = Path(str(request.payload.get("output_dir", simulation.get("output_dir", ""))))
                with external_tool_env(config):
                    result = write_simulation_artifacts(self.model, output_dir)
                return self._read_result(request, before, {"simulation": result})
            if request.operation == "export_kicad_project":
                kicad = config.get("kicad", {}) if isinstance(config.get("kicad"), dict) else {}
                output_dir = Path(str(request.payload.get("output_dir", kicad.get("output_dir", ""))))
                project_name = str(request.payload.get("project_name", kicad.get("project_name", "")))
                with external_tool_env(
                    config,
                    {
                        "KICAD_OUTPUT_DIR": str(output_dir),
                        "KICAD_PROJECT_NAME": project_name,
                    },
                ):
                    netlist = build_netlist(self.model)
                    plan = compile_plan(self.model, netlist)
                    result = write_project(asdict(plan))
                return self._read_result(request, before, {"kicad_project": result})
            project_dir = Path(str(request.payload.get("project_dir", "")))
            schematic_file = request.payload.get("schematic_file", "")
            with external_tool_env(
                config,
                {
                    "KICAD_OUTPUT_DIR": str(project_dir.parent),
                    "KICAD_PROJECT_NAME": project_dir.name,
                    "KICAD_SCHEMATIC_FILE": str(schematic_file),
                },
            ):
                result = run_erc(emit=False)
            if result.get("attempted") and result.get("success") is False:
                report = ValidationReport()
                for warning in result.get("warnings", []):
                    report.add_warning(str(warning))
                return self._failure(request, report, "VALIDATION_FAILED", "ERC failed", before=before)
            return self._read_result(request, before, {"erc": result})
        except Exception as exc:
            report = ValidationReport()
            report.add_error(str(exc))
            return self._failure(request, report, "IO_ERROR", str(exc), before=before)

    def _export_circuit_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        path_value = request.payload.get("path", "")
        if path_value:
            path = Path(str(path_value))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return self._read_result(request, before, {"path": str(path)})
        if self.repository is not None:
            self.repository.save(self.model)
            return self._read_result(request, before, {"path": str(self.repository.model_path)})
        return self._read_result(request, before, {"model": snapshot(self.model)})

    def _export_report(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        report = validate_model_snapshot(self.model)
        payload = {
            "summary": {
                "component_count": report.stats.get("component_count", 0),
                "net_count": report.stats.get("net_count", 0),
            },
            "diagnostics": {
                "ok": report.ok,
                "errors": report.errors,
                "warnings": report.warnings,
                "checks": report.checks,
                "stats": report.stats,
            },
        }
        return self._read_result(request, before, payload)

    def _apply_success(
        self,
        request: OperationRequest,
        result: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        path: str,
        op: str,
    ) -> OperationResult:
        report = validate_model_snapshot(after)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before, after=after)
        visible_after = snapshot(after if request.options.return_snapshot else {})
        visible_before = before if request.options.return_snapshot else {}
        diff = [{"path": path, "op": op}] if request.options.return_diff else []
        changed_paths = [path] if request.options.return_diff else []
        if not request.options.dry_run and not request.options.validate_only and request.options.commit:
            self._commit(after, request, before, diff)
        return self._success(request, report, result, visible_before, visible_after, diff, changed_paths)

    def _success(
        self,
        request: OperationRequest,
        report: ValidationReport,
        result: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        diff: list[dict[str, Any]],
        changed_paths: list[str],
    ) -> OperationResult:
        return OperationResult(
            success=True,
            request_id=request.request_id,
            project_id=request.project_id,
            operation=request.operation,
            result=result,
            diagnostics=report,
            warnings=list(report.warnings),
            before=before,
            after=after,
            diff=diff,
            changed_paths=changed_paths,
        )

    def _commit(
        self,
        model: dict[str, Any],
        request: OperationRequest | None = None,
        before: dict[str, Any] | None = None,
        diff: list[dict[str, Any]] | None = None,
    ) -> str:
        self.model = normalize_model(model)
        if self.repository is not None:
            revision_id = self.repository.next_revision_id()
            self.repository.save(self.model)
            revision_path = self.repository.save_revision(revision_id, self.model)
            if request is not None:
                self.repository.append_operation_log(
                    {
                        "revision_id": revision_id,
                        "request_id": request.request_id,
                        "project_id": request.project_id,
                        "operation": request.operation,
                        "success": True,
                        "changed_paths": [str(item.get("path", "")) for item in diff or []],
                        "before_schema": (before or {}).get("schema_version", ""),
                        "after_schema": self.model.get("schema_version", ""),
                        "revision_file": str(revision_path),
                    }
                )
            return revision_id
        return ""

    def _failure(
        self,
        request: OperationRequest,
        report: ValidationReport,
        code: str,
        message: str,
        path: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> OperationResult:
        if report.ok:
            report.add_error(message)
        return OperationResult(
            success=False,
            request_id=request.request_id,
            project_id=request.project_id,
            operation=request.operation,
            diagnostics=report,
            warnings=list(report.warnings),
            errors=[ApiError(code=code, message=message, path=path)],
            before=before or {},
            after=after or {},
            diff=[],
            changed_paths=[],
        )

    def _payload_error(
        self,
        request: OperationRequest,
        before: dict[str, Any],
        message: str,
        path: str = "",
    ) -> OperationResult:
        return self._failure(request, ValidationReport(), "INVALID_PAYLOAD", message, path, before)

    def _not_found(
        self,
        request: OperationRequest,
        before: dict[str, Any],
        message: str,
        path: str = "",
    ) -> OperationResult:
        return self._failure(request, ValidationReport(), "NOT_FOUND", message, path, before)

    def _read_result(
        self,
        request: OperationRequest,
        before: dict[str, Any],
        result: dict[str, Any],
    ) -> OperationResult:
        report = validate_model_snapshot(self.model)
        return self._success(request, report, self._jsonable(result), before, snapshot(self.model), [], [])

    def _replace_model(
        self,
        request: OperationRequest,
        before: dict[str, Any],
        model: dict[str, Any],
    ) -> OperationResult:
        after = normalize_model(model)
        return self._apply_success(request, {"replaced": True}, before, after, "$", "replace")

    def _diff_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        other = request.payload.get("other", request.payload.get("model", {}))
        if not isinstance(other, dict):
            return self._payload_error(request, before, "other model must be an object", "payload.other")
        return self._read_result(request, before, {"diff": self._simple_diff(self.model, normalize_model(other))})

    def _patch_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        patch = request.payload.get("patch", {})
        if not isinstance(patch, dict):
            return self._payload_error(request, before, "patch must be an object", "payload.patch")
        after = {**snapshot(self.model), **patch}
        return self._apply_success(request, {"patched": True}, before, after, "$", "replace")

    def _merge_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        other = request.payload.get("other", request.payload.get("model", {}))
        if not isinstance(other, dict):
            return self._payload_error(request, before, "other model must be an object", "payload.other")
        after = snapshot(self.model)
        for key, value in other.items():
            if isinstance(value, list) and isinstance(after.get(key), list):
                after[key].extend(snapshot(value))
            elif key not in {"schema_version", "request_id", "project_id", "topology"}:
                after[key] = snapshot(value)
        return self._apply_success(request, {"merged": True}, before, normalize_model(after), "$", "replace")

    def _merge_nets(
        self,
        request: OperationRequest,
        before: dict[str, Any],
        source: str,
        target: str,
    ) -> OperationResult:
        if not source or not target:
            return self._payload_error(request, before, "source and target are required")
        source_index = self._find_index_by_key("nets", "name", source)
        target_index = self._find_index_by_key("nets", "name", target)
        if source_index is None or target_index is None:
            return self._not_found(request, before, "source or target net not found")
        after = snapshot(self.model)
        source_members = after["nets"][source_index].get("members", [])
        target_members = after["nets"][target_index].setdefault("members", [])
        if isinstance(source_members, list) and isinstance(target_members, list):
            for member in source_members:
                if member not in target_members:
                    target_members.append(member)
        after["nets"].pop(source_index)
        return self._apply_success(
            request,
            {"source": source, "target": target},
            before,
            after,
            f"nets[{target}]",
            "replace",
        )

    def _split_net(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        name = str(request.payload.get("name", request.payload.get("net", "")))
        new_nets = request.payload.get("new_nets", request.payload.get("new_names", []))
        if not isinstance(new_nets, list) or not name:
            return self._payload_error(request, before, "name and new_nets are required")
        index = self._find_index_by_key("nets", "name", name)
        if index is None:
            return self._not_found(request, before, f"net {name} not found", "payload.name")
        after = snapshot(self.model)
        original = after["nets"].pop(index)
        for new_net in new_nets:
            if isinstance(new_net, dict):
                after["nets"].append(new_net)
            else:
                after["nets"].append({"name": str(new_net), "members": []})
        return self._apply_success(
            request,
            {"name": name, "removed": original},
            before,
            after,
            f"nets[{name}]",
            "replace",
        )

    def _payload_identifier(self, request: OperationRequest, id_key: str) -> str:
        aliases = {
            "key": ("key", "risk", "risk_key"),
            "name": ("name", "rail", "sheet", "constraint", "calculation"),
            "title": ("title", "decision", "design_decision"),
        }
        for key in aliases.get(id_key, (id_key,)):
            value = request.payload.get(key)
            if value:
                return str(value)
        return ""

    def _field_from_set_operation(self, operation: str) -> str:
        return operation.removeprefix("set_").rsplit("_", 1)[-1]

    def _rename_member_prefix(self, model: dict[str, Any], old_ref: str, new_ref: str) -> None:
        old_prefix = f"{old_ref}."
        new_prefix = f"{new_ref}."
        for net in model.get("nets", []):
            if isinstance(net, dict) and isinstance(net.get("members"), list):
                net["members"] = [
                    new_prefix + member[len(old_prefix) :] if str(member).startswith(old_prefix) else member
                    for member in net["members"]
                ]

    def _connect_member_in_model(self, model: dict[str, Any], net_name: str, member: str) -> None:
        index = self._find_index_in(model, "nets", "name", net_name)
        if index is None:
            model.setdefault("nets", []).append({"name": net_name, "members": [member]})
            return
        members = model["nets"][index].setdefault("members", [])
        if isinstance(members, list) and member not in members:
            members.append(member)

    def _disconnect_member_in_model(self, model: dict[str, Any], net_name: str, member: str) -> None:
        index = self._find_index_in(model, "nets", "name", net_name)
        if index is None:
            return
        members = model["nets"][index].get("members", [])
        if isinstance(members, list):
            model["nets"][index]["members"] = [item for item in members if item != member]

    def _simple_diff(self, before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
        diff: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                op = "add" if key not in before else "remove" if key not in after else "replace"
                diff.append({"path": key, "op": op, "before": before.get(key), "after": after.get(key)})
        return diff

    def _validate_references(
        self,
        report: ValidationReport,
        model: dict[str, Any],
        *,
        strict: bool = False,
    ) -> None:
        refs = {str(item.get("ref", "")) for item in model.get("components", []) if isinstance(item, dict)}
        for net in model.get("nets", []):
            if not isinstance(net, dict):
                continue
            for member in net.get("members", []):
                ref = str(member).split(".", 1)[0]
                if ref and ref not in refs:
                    message = f"net {net.get('name', '')} references missing component {ref}"
                    if strict:
                        report.add_error(message)
                    else:
                        report.add_warning(message)
        report.add_check("references checked")

    def _validate_sheet_boundaries(self, report: ValidationReport, model: dict[str, Any]) -> None:
        refs = {str(item.get("ref", "")) for item in model.get("components", []) if isinstance(item, dict)}
        nets = {str(item.get("name", "")) for item in model.get("nets", []) if isinstance(item, dict)}
        for sheet in model.get("sheets", []):
            if not isinstance(sheet, dict):
                continue
            for ref in sheet.get("components", []):
                if str(ref) not in refs:
                    report.add_warning(f"sheet {sheet.get('name', '')} references missing component {ref}")
            for net in sheet.get("nets", []):
                if str(net) not in nets:
                    report.add_warning(f"sheet {sheet.get('name', '')} references missing net {net}")
        report.add_check("sheet boundaries checked")

    def _validate_parts(self, report: ValidationReport, model: dict[str, Any]) -> None:
        for component in model.get("components", []):
            if isinstance(component, dict) and not isinstance(component.get("selected_part", {}), dict):
                report.add_error(f"component {component.get('ref', '')} selected_part must be an object")
        report.add_check("part availability checked")

    def _validate_power(self, report: ValidationReport, model: dict[str, Any], *, strict: bool = False) -> None:
        names = {str(item.get("name", "")) for item in model.get("power_rails", []) if isinstance(item, dict)}
        for rail in model.get("power_rails", []):
            if isinstance(rail, dict):
                parent = str(rail.get("parent", ""))
                if parent and parent not in names:
                    message = f"power rail {rail.get('name', '')} has missing parent {parent}"
                    if strict:
                        report.add_error(message)
                    else:
                        report.add_warning(message)
        report.add_check("power tree checked")

    def _validate_pinmaps(self, report: ValidationReport, model: dict[str, Any]) -> None:
        nets = {str(item.get("name", "")) for item in model.get("nets", []) if isinstance(item, dict)}
        for component in model.get("components", []):
            if not isinstance(component, dict) or "pinmap" not in component:
                continue
            if not isinstance(component["pinmap"], dict):
                report.add_error(f"component {component.get('ref', '')} pinmap must be an object")
                continue
            for pin, pin_entry in component["pinmap"].items():
                if not isinstance(pin_entry, dict):
                    report.add_error(f"component {component.get('ref', '')} pinmap.{pin} must be an object")
                    continue
                net = str(pin_entry.get("net", ""))
                if net and net not in nets:
                    report.add_error(f"component {component.get('ref', '')} pinmap.{pin} references missing net {net}")
        report.add_check("pinmaps checked")

    def _validate_risks(self, report: ValidationReport, model: dict[str, Any]) -> None:
        for risk in model.get("risks", []):
            if isinstance(risk, dict) and not risk.get("status"):
                report.add_warning(f"risk {risk.get('key', risk.get('title', ''))} has no status")
        report.add_check("risks checked")

    def _find_index_in(self, model: dict[str, Any], container: str, key: str, value: str) -> int | None:
        items = model.get(container, [])
        if not isinstance(items, list):
            return None
        for index, item in enumerate(items):
            if isinstance(item, dict) and str(item.get(key, "")) == value:
                return index
        return None

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._jsonable(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value

    def _find_by_key(self, container: str, key: str, value: str) -> dict[str, Any] | None:
        index = self._find_index_by_key(container, key, value)
        if index is None:
            return None
        item = self.model.get(container, [])[index]
        return snapshot(item) if isinstance(item, dict) else None

    def _find_index_by_key(self, container: str, key: str, value: str) -> int | None:
        items = self.model.get(container, [])
        if not isinstance(items, list):
            return None
        for index, item in enumerate(items):
            if isinstance(item, dict) and str(item.get(key, "")) == value:
                return index
        return None
