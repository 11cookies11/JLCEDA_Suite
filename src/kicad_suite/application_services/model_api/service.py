"""Service entry point for controlled circuit-model DSL operations."""

from __future__ import annotations

from dataclasses import is_dataclass, asdict
from typing import Any

from ...shared.validation.common import ValidationReport
from .commands import OperationRequest, operation_request_from_dict
from .model import empty_model, normalize_model, snapshot
from .payloads import validate_operation_payload
from .repository import CircuitModelRepository
from .results import ApiError, OperationResult
from .validation import validate_model_snapshot, validate_request
from .handlers_crud import _CrudHandlers
from .handlers_extended import _ExtendedHandlers


class ModelApiService(_CrudHandlers, _ExtendedHandlers):
    """Apply typed DSL API requests to an in-memory circuit model."""

    _SIMPLE_OPERATION_DISPATCH: dict[str, str] = {
        "load_model": "_load_model",
        "validate_model": "_validate_model",
        "add_component": "_add_component",
        "update_component": "_update_component",
        "remove_component": "_remove_component",
        "set_selected_part": "_set_selected_part",
        "add_candidate_part": "_add_candidate_part",
        "remove_candidate_part": "_remove_candidate_part",
        "add_net": "_add_net",
        "update_net": "_update_net",
        "remove_net": "_remove_net",
        "connect_member": "_connect_member",
        "disconnect_member": "_disconnect_member",
        "get_component": "_get_component",
        "get_net": "_get_net",
        "list_components": "_list_components",
        "list_nets": "_list_nets",
    }

    _EXTENDED_OPERATION_DISPATCH: dict[str, str] = {
        "create_project_template": "_create_project_template",
        "create_hardware_project": "_create_hardware_project",
        "save_model": "_export_circuit_model",
        "export_circuit_model": "_export_circuit_model",
        "validate_ir": "_validate_ir_operation",
        "export_summary": "_export_report",
        "export_report": "_export_report",
        "build_ir": "_compile_operation",
        "export_ir": "_compile_operation",
        "compile_netlist": "_compile_operation",
        "compile_spice_netlist": "_compile_operation",
        "compile_kicad_execution_plan": "_compile_operation",
        "export_kicad_project": "_external_tool_operation",
        "run_erc": "_external_tool_operation",
        "run_simulation_plan": "_external_tool_operation",
    }

    _EXTENDED_OPERATION_GROUPS: tuple[tuple[frozenset[str], str], ...] = (
        (frozenset({"get_metadata", "set_schema_version", "set_request_id", "set_project_id", "set_topology", "update_metadata"}), "_metadata_operation"),
        (frozenset({"connect_members", "disconnect_members", "rename_net", "merge_nets", "split_net"}), "_net_collection_operation"),
        (frozenset({"set_selected_part", "update_selected_part", "replace_selected_part"}), "_set_selected_part"),
        (frozenset({"lock_selected_part", "unlock_selected_part"}), "_selected_part_lock_operation"),
        (frozenset({
            "set_pinmap", "update_pinmap", "remove_pinmap", "get_pinmap",
            "connect_pin_to_net", "disconnect_pin_from_net",
            "set_pin_name", "set_pin_role", "set_pin_direction",
            "set_pin_no_connect", "add_pin_alias", "resolve_pin_alias",
        }), "_pinmap_operation"),
        (frozenset({"begin_transaction", "commit_transaction", "rollback_transaction", "diff_transaction"}), "_transaction_operation"),
        (frozenset({"apply_operation", "apply_batch", "dry_run"}), "_batch_operation"),
        (frozenset({"export_summary", "export_report"}), "_export_report"),
    )

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

    _IDENTITY_KEYS: dict[str, str] = {
        "components": "ref",
        "nets": "name",
        "risks": "key",
        "design_decisions": "title",
        "sheets": "name",
        "calculations": "name",
        "constraints": "name",
        "power_rails": "name",
    }

    @classmethod
    def from_model(cls, model: dict[str, Any]) -> "ModelApiService":
        return cls(model)

    @classmethod
    def from_repository(cls, repository: CircuitModelRepository) -> "ModelApiService":
        return cls(repository=repository)

    # -- entry points -----------------------------------------------------

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
        simple_handler_name = self._SIMPLE_OPERATION_DISPATCH.get(operation)
        if simple_handler_name is not None:
            return getattr(self, simple_handler_name)(request, before)
        extended = self._handle_extended_operation(request, before)
        if extended is not None:
            return extended

        return self._failure(
            request, request_report, "UNSUPPORTED_OPERATION", f"unsupported operation: {operation}", before=before,
        )

    def _validate_ir_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        from ...domain.core.ir_compiler import build_ir
        from ...domain.core.ir_validator import validate_ir
        try:
            ir = build_ir(self.model)
        except (ValueError, KeyError, TypeError) as exc:
            return self._failure(request, ValidationReport(), "VALIDATION_FAILED", str(exc), before=before)
        report = validate_ir(ir)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        return self._success(request, report, {"valid": True, "ir_stats": report.stats}, before, snapshot(self.model), [], [])

    def _validate_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        report = validate_model_snapshot(self.model)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        return self._success(request, report, {"valid": True}, before, snapshot(self.model), [], [])

    def _list_items(self, request: OperationRequest, before: dict[str, Any], key: str) -> OperationResult:
        report = ValidationReport(
            checks=[f"{key} listed"],
            stats={f"{key}_count": len(self.model.get(key, []))},
        )
        return self._success(request, report, {key: snapshot(self.model.get(key, []))}, before, snapshot(self.model), [], [])

    def _list_components(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        return self._list_items(request, before, "components")

    def _list_nets(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        return self._list_items(request, before, "nets")

    def _handle_extended_operation(
        self, request: OperationRequest, before: dict[str, Any],
    ) -> OperationResult | None:
        operation = request.operation
        dispatch_name = self._EXTENDED_OPERATION_DISPATCH.get(operation)
        if dispatch_name is not None:
            return getattr(self, dispatch_name)(request, before)

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

        for operations, handler_name in self._EXTENDED_OPERATION_GROUPS:
            if operation in operations:
                return getattr(self, handler_name)(request, before)

        if operation.startswith("set_net_") or operation.startswith("mark_net_"):
            return self._net_field_operation(request, before)
        if operation in {
            "set_component_ref", "set_component_role", "set_component_value",
            "set_component_notes", "set_component_availability",
            "mark_component_resolved", "mark_component_needs_review", "mark_component_blocked",
            "assign_component_to_sheet",
        }:
            return self._component_field_operation(request, before)
        if operation.startswith("validate_"):
            return self._validation_operation(request, before)
        if operation.startswith("link_"):
            return self._link_operation(request, before)

        collection = self._collection_for_operation(operation)
        if collection is not None:
            return self._generic_collection_operation(request, before, collection[0], collection[1])
        return None

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

    # -- result builders --------------------------------------------------

    def _apply_success(
        self, request: OperationRequest, result: dict[str, Any],
        before: dict[str, Any], after: dict[str, Any], path: str, op: str,
    ) -> OperationResult:
        report = validate_model_snapshot(after)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before, after=after)
        visible_after = snapshot(after if request.options.return_snapshot else {})
        visible_before = before if request.options.return_snapshot else {}
        diff = self._deep_diff(before, after) if request.options.return_diff else []
        changed_paths = [str(item.get("path", "")) for item in diff] if request.options.return_diff else []
        if not request.options.dry_run and not request.options.validate_only and request.options.commit:
            self._commit(after, request, before, diff)
        return self._success(request, report, result, visible_before, visible_after, diff, changed_paths)

    def _success(
        self, request: OperationRequest, report: ValidationReport, result: dict[str, Any],
        before: dict[str, Any], after: dict[str, Any],
        diff: list[dict[str, Any]], changed_paths: list[str],
    ) -> OperationResult:
        return OperationResult(
            success=True, request_id=request.request_id, project_id=request.project_id,
            operation=request.operation, result=result, diagnostics=report,
            warnings=list(report.warnings), before=before, after=after,
            diff=diff, changed_paths=changed_paths,
        )

    def _commit(
        self, model: dict[str, Any],
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
                self.repository.append_operation_log({
                    "revision_id": revision_id,
                    "request_id": request.request_id,
                    "project_id": request.project_id,
                    "operation": request.operation,
                    "success": True,
                    "changed_paths": [str(item.get("path", "")) for item in diff or []],
                    "before_schema": (before or {}).get("schema_version", ""),
                    "after_schema": self.model.get("schema_version", ""),
                    "revision_file": str(revision_path),
                })
            return revision_id
        return ""

    def _failure(
        self, request: OperationRequest, report: ValidationReport,
        code: str, message: str, path: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> OperationResult:
        if report.ok:
            report.add_error(message)
        return OperationResult(
            success=False, request_id=request.request_id, project_id=request.project_id,
            operation=request.operation, diagnostics=report, warnings=list(report.warnings),
            errors=[ApiError(code=code, message=message, path=path)],
            before=before or {}, after=after or {}, diff=[], changed_paths=[],
        )

    def _payload_error(
        self, request: OperationRequest, before: dict[str, Any], message: str, path: str = "",
    ) -> OperationResult:
        return self._failure(request, ValidationReport(), "INVALID_PAYLOAD", message, path, before)

    def _not_found(
        self, request: OperationRequest, before: dict[str, Any], message: str, path: str = "",
    ) -> OperationResult:
        return self._failure(request, ValidationReport(), "NOT_FOUND", message, path, before)

    def _read_result(
        self, request: OperationRequest, before: dict[str, Any], result: dict[str, Any],
    ) -> OperationResult:
        report = validate_model_snapshot(self.model)
        return self._success(request, report, self._jsonable(result), before, snapshot(self.model), [], [])

    def _validate_model_snapshot(self, model: dict[str, Any]) -> ValidationReport:
        """Thin wrapper so mixins can call the validation routine via self."""
        return validate_model_snapshot(model)

    # -- deep diff --------------------------------------------------------

    def _deep_diff(
        self, before: Any, after: Any, base_path: str = "", container: str = "",
    ) -> list[dict[str, Any]]:
        """Recursively diff two values, producing nested paths like ``components[U1].value``."""
        diff: list[dict[str, Any]] = []

        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after)):
                seg = f".{key}" if base_path else key
                child_path = f"{base_path}{seg}"
                if key not in before:
                    diff.append({"path": child_path, "op": "add", "after": after[key]})
                elif key not in after:
                    diff.append({"path": child_path, "op": "remove", "before": before[key]})
                elif before[key] != after[key]:
                    diff.extend(self._deep_diff(before[key], after[key], child_path, container=key))

        elif isinstance(before, list) and isinstance(after, list):
            id_key = self._IDENTITY_KEYS.get(container, "")
            for i in range(max(len(before), len(after))):
                id_val = ""
                if i < len(before) and isinstance(before[i], dict) and id_key:
                    id_val = str(before[i].get(id_key, ""))
                if not id_val and i < len(after) and isinstance(after[i], dict) and id_key:
                    id_val = str(after[i].get(id_key, ""))
                seg = f"[{id_val}]" if id_val else f"[{i}]"
                child_path = f"{base_path}{seg}"
                if i >= len(before):
                    diff.append({"path": child_path, "op": "add", "after": after[i]})
                elif i >= len(after):
                    diff.append({"path": child_path, "op": "remove", "before": before[i]})
                elif before[i] != after[i]:
                    diff.extend(self._deep_diff(before[i], after[i], child_path, container=container))

        elif before != after:
            op = "add" if (before in (None, "", [], {}) and base_path == "") else "replace"
            entry: dict[str, Any] = {"path": base_path or "$", "op": op}
            if before not in (None, "", [], {}):
                entry["before"] = before
            if after not in (None, "", [], {}):
                entry["after"] = after
            diff.append(entry)

        return diff

    # -- shared utilities -------------------------------------------------

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
        for prefix in ("set_calculation_", "set_constraint_", "set_rail_", "set_risk_", "set_sheet_"):
            if operation.startswith(prefix):
                return operation.removeprefix(prefix)
        return operation.removeprefix("set_").rsplit("_", 1)[-1]

    def _link_source_collection(self, token: str) -> tuple[str, str] | None:
        return {
            "calculation": ("calculations", "name"),
            "decision": ("design_decisions", "title"),
            "design_decision": ("design_decisions", "title"),
            "risk": ("risks", "key"),
        }.get(token)

    def _link_target_field(self, token: str) -> str:
        return {"component": "components", "decision": "decisions",
                "design_decision": "decisions", "net": "nets",
                "risk": "risks", "sheet": "sheets"}.get(token, "")

    def _link_payload_value(
        self, payload: dict[str, Any], token: str, id_key: str, generic_key: str,
    ) -> str:
        for key in (generic_key, token, id_key, f"{token}_{id_key}"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""

    def _rename_member_prefix(self, model: dict[str, Any], old_ref: str, new_ref: str) -> None:
        old_prefix, new_prefix = f"{old_ref}.", f"{new_ref}."
        for net in model.get("nets", []):
            if isinstance(net, dict) and isinstance(net.get("members"), list):
                net["members"] = [
                    new_prefix + member[len(old_prefix):] if str(member).startswith(old_prefix) else member
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
