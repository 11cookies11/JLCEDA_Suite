"""Handlers for component, net, and pinmap CRUD operations — mixin for ModelApiService."""

from __future__ import annotations

from typing import Any

from ...shared.validation.common import ValidationReport
from .commands import OperationRequest
from .results import OperationResult
from .model import snapshot


class _CrudHandlers:
    """Mixin providing component, net, and pinmap operation handlers."""

    # -- component CRUD ---------------------------------------------------

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

    def _selected_part_lock_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        ref = str(request.payload.get("ref", ""))
        if not ref:
            return self._payload_error(request, before, "component ref is required", "payload.ref")
        component_index = self._find_index_by_key("components", "ref", ref)
        if component_index is None:
            return self._not_found(request, before, f"component {ref} not found", "payload.ref")
        after = snapshot(self.model)
        locked = request.operation == "lock_selected_part"
        after["components"][component_index]["selected_part_locked"] = locked
        return self._apply_success(
            request,
            {"ref": ref, "selected_part_locked": locked},
            before,
            after,
            f"components[{ref}].selected_part_locked",
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

    # -- net CRUD ---------------------------------------------------------

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
                request, ValidationReport(),
                "INVALID_PAYLOAD", "payload.net is required", "payload.net", before,
            )
        if not member:
            return self._failure(
                request, ValidationReport(),
                "INVALID_PAYLOAD", "payload.member is required", "payload.member", before,
            )
        net_index = self._find_index_by_key("nets", "name", net_name)
        if net_index is None:
            return self._failure(
                request, ValidationReport(),
                "NOT_FOUND", f"net {net_name} not found", "payload.net", before,
            )

        after = snapshot(self.model)
        members = after["nets"][net_index].setdefault("members", [])
        if not isinstance(members, list):
            return self._failure(
                request, ValidationReport(),
                "INVALID_PAYLOAD", f"net {net_name} members must be a list", before=before,
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

    def _get_net(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        name = str(request.payload.get("name", request.payload.get("net", "")))
        net = self._find_by_key("nets", "name", name)
        if net is None:
            return self._failure(
                request, ValidationReport(),
                "NOT_FOUND", f"net {name} not found", "payload.name", before,
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

    # -- component field operations ---------------------------------------

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
                    request, ValidationReport(),
                    "ALREADY_EXISTS", f"component {next_ref} already exists", "payload.new_ref", before,
                )
            component["ref"] = next_ref
            self._rename_member_prefix(after, ref, next_ref)
            return self._apply_success(request, {"ref": next_ref}, before, after, f"components[{ref}].ref", "replace")
        field_map = {
            "set_component_role": "role",
            "set_component_value": "value",
            "set_component_notes": "notes",
            "set_component_availability": "availability_status",
            "set_component_search_hints": "search_hints",
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

    # -- net field / collection operations ---------------------------------

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
                request, {"net": net_name, "members": members}, before, after, f"nets[{net_name}]", "replace",
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

    def _merge_nets(
        self, request: OperationRequest, before: dict[str, Any], source: str, target: str,
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
        return self._apply_success(request, {"source": source, "target": target}, before, after, f"nets[{target}]", "replace")

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
        return self._apply_success(request, {"name": name, "removed": original}, before, after, f"nets[{name}]", "replace")

    # -- pinmap operations -------------------------------------------------

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
            request, {"ref": ref, "pin": pin}, before, after, f"components[{ref}].pinmap[{pin}]", "replace",
        )
