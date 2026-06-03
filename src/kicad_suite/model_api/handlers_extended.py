"""Handlers for generic collections, transactions, validation, compile, export — mixin for ModelApiService."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..kicad_erc_runner import run as run_erc
from ..kicad_project_writer import write_project
from ..pcb_generator import generate_pcb
from ..example_scaffold import scaffold_example
from ..circuit_model_io import (
    load_dual_circuit_model,
    project_root_from_model_path,
    save_resolved_circuit_model,
    save_source_circuit_model,
)
from ..ir_compiler import build_ir
from ..ir_to_kicad import ir_to_kicad
from ..pipeline_coordinator import build_netlist
from ..simulation_planner import write_simulation_artifacts
from ..project_state import ProjectState
from ..schema_versions import CIRCUIT_MODEL_SCHEMA_VERSION, SPICE_NETLIST_SCHEMA_VERSION
from ..validation.common import ValidationReport, load_json
from .commands import OperationRequest
from .results import OperationResult
from .external_tools import external_tool_env, external_tools_config_from_payload
from .model import empty_model, normalize_model, snapshot


class _ExtendedHandlers:
    """Mixin providing generic collection, transaction, validation, compile, and export handlers."""

    # -- metadata ----------------------------------------------------------

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

    # -- generic collection operations ------------------------------------

    def _generic_collection_operation(
        self, request: OperationRequest, before: dict[str, Any], collection: str, id_key: str,
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
                    request, ValidationReport(),
                    "ALREADY_EXISTS", f"{collection} {item_id} already exists", f"payload.{id_key}", before,
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

    # -- link operations ---------------------------------------------------

    def _link_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        relation = request.operation.removeprefix("link_")
        if "_to_" not in relation:
            return self._payload_error(request, before, "link operation must contain _to_")
        source_token, target_token = relation.split("_to_", 1)
        source = self._link_source_collection(source_token)
        target_field = self._link_target_field(target_token)
        if source is None or not target_field:
            return self._payload_error(request, before, f"unsupported link relation: {relation}")
        collection, id_key = source
        source_id = self._link_payload_value(request.payload, source_token, id_key, "source")
        target_id = self._link_payload_value(request.payload, target_token, target_token, "target")
        if not source_id or not target_id:
            return self._payload_error(request, before, "source and target are required for link operations")
        index = self._find_index_by_key(collection, id_key, source_id)
        if index is None:
            return self._not_found(request, before, f"{collection} {source_id} not found", f"payload.{id_key}")
        after = snapshot(self.model)
        links = after[collection][index].setdefault(target_field, [])
        if not isinstance(links, list):
            return self._payload_error(request, before, f"{collection}[{source_id}].{target_field} must be a list")
        if target_id not in links:
            links.append(target_id)
        return self._apply_success(
            request, {"source": source_id, "target": target_id, "field": target_field},
            before, after, f"{collection}[{source_id}].{target_field}", "replace",
        )

    # -- transaction & batch -----------------------------------------------

    def _transaction_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        if request.operation == "begin_transaction":
            if self.transaction_base is not None:
                return self._failure(
                    request, ValidationReport(), "TX_ALREADY_ACTIVE", "transaction already active", before=before,
                )
            self.transaction_base = before
            return self._read_result(request, before, {"transaction": {"status": "active"}})
        if request.operation == "rollback_transaction":
            if self.transaction_base is None:
                return self._failure(
                    request, ValidationReport(), "TX_NOT_ACTIVE", "transaction is not active", before=before,
                )
            base = snapshot(self.transaction_base)
            self.transaction_base = None
            self._commit(base, request, before, [])
            return self._success(
                request, ValidationReport(checks=["transaction rolled back"]), {}, before, base, [], [],
            )
        if request.operation == "commit_transaction":
            self.transaction_base = None
            if self.repository is not None:
                self.repository.save(self.model)
            return self._read_result(request, before, {"transaction": {"status": "committed"}})
        if self.transaction_base is None:
            return self._failure(
                request, ValidationReport(), "TX_NOT_ACTIVE", "transaction is not active", before=before,
            )
        diff = self._deep_diff(self.transaction_base, self.model)
        return self._read_result(request, before, {"diff": diff})

    def _batch_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        if request.operation == "apply_operation":
            operations = [request.payload]
        else:
            operations = request.payload.get("operations", [])
        if not isinstance(operations, list):
            return self._payload_error(request, before, "operations must be a list", "payload.operations")
        temp = type(self).from_model(snapshot(self.model))
        all_diff: list[dict[str, Any]] = []
        for index, item in enumerate(operations):
            if not isinstance(item, dict):
                return self._payload_error(request, before, f"operations[{index}] must be an object")
            child = OperationRequest(
                request_id=f"{request.request_id}:{index}",
                project_id=request.project_id,
                topology=request.topology,
                operation=str(item.get("operation", "")),
                payload=item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {},
                options=request.options,
            )
            result = temp.handle(child)
            if not result.success:
                return self._failure(
                    request, result.diagnostics, "VALIDATION_FAILED", result.errors[0].message, before=before,
                )
            all_diff.extend(result.diff)
        if request.operation != "dry_run" and not request.options.dry_run and request.options.commit:
            self._commit(temp.model, request, before, all_diff)
        after = snapshot(temp.model)
        return self._success(
            request, self._validate_model_snapshot(after), {"operation_count": len(operations)},
            before, after, all_diff, [str(item.get("path", "")) for item in all_diff],
        )

    # -- validation --------------------------------------------------------

    def _validation_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        report = self._validate_model_snapshot(self.model)
        strict_references = request.operation in {
            "validate_connectivity", "validate_readiness", "validate_references",
        }
        self._validate_references(report, self.model, strict=strict_references)
        if request.operation in {
            "validate_connectivity", "validate_readiness",
            "validate_sheet_boundary", "validate_sheet_inputs_outputs",
        }:
            self._validate_sheet_boundaries(report, self.model)
        if request.operation in {"validate_part_availability", "validate_readiness"}:
            self._validate_parts(report, self.model)
        if request.operation in {
            "validate_power_tree", "validate_power_budget", "validate_sequence", "validate_readiness",
        }:
            self._validate_power(report, self.model, strict=request.operation == "validate_readiness")
        if request.operation in {"validate_pinmap", "validate_readiness"}:
            self._validate_pinmaps(report, self.model)
        if request.operation in {"validate_risk_consistency", "validate_readiness"}:
            self._validate_risks(report, self.model)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        return self._success(request, report, {"valid": True}, before, snapshot(self.model), [], [])

    def _validate_references(
        self, report: ValidationReport, model: dict[str, Any], *, strict: bool = False,
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

    # -- compile -----------------------------------------------------------

    def _scaffold_project_template(
        self, project_dir: Path, title: str, *, overwrite: bool,
    ) -> list[Path]:
        project_name = project_dir.name
        return scaffold_example(
            project_name,
            title=title,
            root_dir=project_dir.parent,
            overwrite=overwrite,
            include_circuit_model=False,
        )

    def _create_project_template(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        project_dir_value = str(request.payload.get("project_dir", ""))
        if not project_dir_value:
            return self._payload_error(request, before, "project_dir is required", "payload.project_dir")
        project_dir = Path(project_dir_value)
        title = str(request.payload.get("title", "") or project_dir.name.replace("-", " ").replace("_", " ").title())
        overwrite = bool(request.payload.get("overwrite", False))

        try:
            created_files = self._scaffold_project_template(project_dir, title, overwrite=overwrite)
            return self._read_result(
                request,
                before,
                {
                    "project_dir": str(project_dir),
                    "created": True,
                    "created_files": [str(path) for path in created_files],
                    "template": {
                        "project_name": project_dir.name,
                        "title": title,
                    },
                },
            )
        except FileExistsError as exc:
            return self._failure(request, ValidationReport(), "ALREADY_EXISTS", str(exc), "payload.project_dir", before)
        except Exception as exc:
            return self._failure(request, ValidationReport(), "IO_ERROR", str(exc), before=before)

    def _create_hardware_project(
        self, request: OperationRequest, before: dict[str, Any],
    ) -> OperationResult:
        project_dir_value = str(request.payload.get("project_dir", ""))
        project_dir = Path(project_dir_value)
        project_id = str(request.payload.get("project_id", request.project_id))
        if not project_id:
            return self._payload_error(request, before, "project_id is required", "payload.project_id")
        title = str(request.payload.get("title", project_id))
        topology = str(request.payload.get("topology", request.topology or project_id.replace("-", "_")))
        overwrite = bool(request.payload.get("overwrite", False))
        should_initialize_state = bool(request.payload.get("initialize_state", True))
        should_validate_ir = bool(request.payload.get("validate_ir", True))
        should_export_ir = bool(request.payload.get("export_ir", False))

        if not project_dir_value:
            return self._payload_error(request, before, "project_dir is required", "payload.project_dir")
        if project_dir.exists() and any(project_dir.iterdir()) and not overwrite:
            return self._failure(
                request,
                ValidationReport(),
                "ALREADY_EXISTS",
                f"project directory is not empty: {project_dir}",
                "payload.project_dir",
                before,
            )

        try:
            self._scaffold_project_template(project_dir, title, overwrite=overwrite)
            model = self._project_model_from_payload(request, project_id=project_id, topology=topology)
            model_path = project_dir / "source" / "circuit-model.source.json"
            save_source_circuit_model(model_path, model)
            save_resolved_circuit_model(model_path, model)

            ir_path = ""
            ir_stats: dict[str, Any] = {}
            validation = ValidationReport()
            if should_validate_ir or should_export_ir:
                from ..ir_validator import validate_ir

                ir = build_ir(model)
                validation = validate_ir(ir)
                ir_stats = dict(validation.stats)
                if should_export_ir:
                    output_path = project_dir / "build" / "ir.json"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    ir_path = str(output_path)

            state_path = ""
            if should_initialize_state:
                state = ProjectState(project_dir)
                state.recompute()
                diagnostics = {"errors": validation.errors, "warnings": validation.warnings}
                if should_validate_ir:
                    if validation.ok:
                        state.mark_valid(diagnostics)
                    else:
                        state.mark_invalid(diagnostics)
                state_path = str(state.state_path)

            report = validation if should_validate_ir else ValidationReport(checks=["project created"])
            if not report.ok:
                return self._failure(
                    request,
                    report,
                    "VALIDATION_FAILED",
                    report.errors[0],
                    before=before,
                    after=snapshot(self.model),
                )
            report.add_check("hardware project created")
            result = {
                "project_dir": str(project_dir),
                "model_path": str(model_path),
                "state_path": state_path,
                "ir_path": ir_path,
                "created": True,
                "valid": report.ok,
                "ir_stats": ir_stats,
            }
            return self._success(request, report, result, before, snapshot(self.model), [], [])
        except Exception as exc:
            return self._failure(request, ValidationReport(), "IO_ERROR", str(exc), before=before)

    def _project_model_from_payload(
        self, request: OperationRequest, *, project_id: str, topology: str,
    ) -> dict[str, Any]:
        payload_model = request.payload.get("model")
        if isinstance(payload_model, dict):
            model = snapshot(payload_model)
        else:
            source_model = str(request.payload.get("source_model", ""))
            if source_model:
                model = load_dual_circuit_model(Path(source_model))
            else:
                model = snapshot(self.model) if self.model else empty_model(request.request_id, project_id, topology)
        model = normalize_model(model)
        model["schema_version"] = CIRCUIT_MODEL_SCHEMA_VERSION
        model["request_id"] = str(request.payload.get("request_id", request.request_id))
        model["project_id"] = project_id
        model["topology"] = topology
        return model

    def _compile_operation(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        try:
            if request.operation == "build_ir":
                ir = build_ir(self.model)
                return self._read_result(request, before, {"ir": ir})
            if request.operation == "export_ir":
                ir = build_ir(self.model)
                return self._export_ir_to_file(request, before, ir)
            netlist = build_netlist(self.model)
            if request.operation == "compile_netlist":
                return self._read_result(request, before, {"netlist": netlist})
            if request.operation == "compile_spice_netlist":
                return self._read_result(request, before, {"spice_netlist": self._build_spice_netlist(netlist)})
            ir = build_ir(self.model)
            plan = ir_to_kicad(ir)
            return self._read_result(request, before, {"execution_plan": plan})
        except Exception as exc:
            return self._failure(request, ValidationReport(), "VALIDATION_FAILED", str(exc), before=before)

    def _export_ir_to_file(
        self, request: OperationRequest, before: dict[str, Any], ir: dict[str, Any],
    ) -> OperationResult:
        import json
        from pathlib import Path
        path_value = request.payload.get("path", "")
        if path_value:
            path = Path(str(path_value))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return self._read_result(request, before, {"path": str(path), "ir": ir})
        if self.repository is not None:
            ir_path = self.repository.model_path.parent / "build" / "ir.json"
            ir_path.parent.mkdir(parents=True, exist_ok=True)
            ir_path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return self._read_result(request, before, {"path": str(ir_path), "ir": ir})
        return self._read_result(request, before, {"ir": ir})

    def _build_spice_netlist(self, netlist: dict[str, Any]) -> dict[str, Any]:
        lines: list[dict[str, str]] = [
            {"kind": "comment", "text": f"* Generated from {netlist.get('request_id', '')}"},
        ]
        for component in netlist.get("components", []):
            if not isinstance(component, dict):
                continue
            pins = component.get("pins", [])
            nodes = [str(pin.get("net", "")) for pin in pins if isinstance(pin, dict) and pin.get("net")]
            ref = str(component.get("ref", ""))
            value = str(component.get("value", ""))
            if len(nodes) >= 2 and ref:
                lines.append({"kind": "component", "text": f"{ref} {nodes[0]} {nodes[1]} {value or '1'}"})
            elif ref:
                lines.append({"kind": "comment", "text": f"* {ref} omitted: fewer than two connected pins"})
        lines.append({"kind": "control", "text": ".end"})
        return {
            "schema_version": SPICE_NETLIST_SCHEMA_VERSION,
            "request_id": str(netlist.get("request_id", "")),
            "project_id": str(netlist.get("project_id", "")),
            "source_netlist": f"{netlist.get('schema_version', '')}::{netlist.get('request_id', '')}",
            "lines": lines,
        }

    # -- external tools & export -------------------------------------------

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
                topology = str(self.model.get("topology", ""))
                source_project = str(project_root_from_model_path(self.repository.model_path)) if self.repository else ""
                import time as _time
                t0 = _time.monotonic()
                with external_tool_env(
                    config,
                    {
                        "KICAD_SOURCE_PROJECT_DIR": source_project,
                        "KICAD_OUTPUT_DIR": str(output_dir),
                        "KICAD_OUTPUT_PROJECT_DIR": str(output_dir / project_name),
                        "KICAD_PROJECT_NAME": project_name,
                        "KICAD_TOPOLOGY": topology,
                    },
                ):
                    ir = build_ir(self.model)
                    plan = ir_to_kicad(ir)
                    result = write_project(asdict(plan), project_path=source_project)
                    project_out = output_dir / project_name
                    if project_out.is_dir():
                        from ..pipeline_postprocess import inject_jlc_symbols, pin_project_libraries
                        try:
                            schematic_file = output_dir / project_name / (project_name + ".kicad_sch")
                            inject_jlc_symbols(schematic_file)
                        except Exception:
                            pass
                        # Generate PCB
                        from ..pcb_generator import generate_pcb
                        pcb_result = generate_pcb(asdict(plan), project_path=source_project)
                        result["pcb"] = pcb_result
                        try:
                            pin_result = pin_project_libraries(project_out)
                            result["library_pins"] = pin_result
                        except Exception:
                            pass
                build_time = round(_time.monotonic() - t0, 2)

                # Auto-run ERC and build report for agent visibility
                erc_result = None
                erc_time = 0.0
                report_data: dict[str, Any] = {}
                try:
                    schematic_file = output_dir / project_name / (project_name + ".kicad_sch")
                    if schematic_file.exists():
                        t1 = _time.monotonic()
                        erc_output = output_dir / project_name / (project_name + ".erc.json")
                        from ..kicad_erc_runner import run as run_erc_file
                        with external_tool_env(config, {
                            "KICAD_SCHEMATIC_FILE": str(schematic_file),
                            "KICAD_ERC_OUTPUT_FILE": str(erc_output),
                        }):
                            erc_result = run_erc_file(emit=False)
                        erc_time = round(_time.monotonic() - t1, 2)
                    # Build agent-friendly report
                    from ..report_system import build_report
                    report_data = build_report(
                        source_project or str(output_dir.parent),
                        model=self.model,
                        erc_result=erc_result,
                    )
                    report_data["timing"] = {"build_sec": build_time, "erc_sec": erc_time}
                    report_path = output_dir / project_name / "agent-report.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    report_data["report_path"] = str(report_path)
                except Exception:
                    pass

                # Extract ERC violation summary for the operation log
                erc_summary: dict[str, Any] = {}
                if erc_result:
                    erc_summary["finding_count"] = erc_result.get("finding_count", 0)
                    try:
                        erc_file = erc_result.get("output_file", "")
                        if erc_file:
                            erc_data = json.loads(Path(erc_file).read_text(encoding="utf-8"))
                            from collections import Counter
                            type_counts: Counter = Counter()
                            for sheet in erc_data.get("sheets", []):
                                for v in sheet.get("violations", []):
                                    type_counts[str(v.get("type", "?"))] += 1
                            erc_summary["violations"] = [
                                {"type": t, "count": c} for t, c in type_counts.most_common()
                            ]
                    except Exception:
                        pass

                return self._read_result(request, before, {
                    "kicad_project": result,
                    "erc": erc_summary,
                    "report": {
                        "overall_status": report_data.get("overall_status", "?"),
                        "component_count": len(report_data.get("sections", [])),
                        "path": report_data.get("report_path", ""),
                    },
                    "timing": {"build_sec": build_time, "erc_sec": erc_time},
                })
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
            return self._read_result(request, before, {"path": str(self.repository.resolved_path)})
        return self._read_result(request, before, {"model": snapshot(self.model)})

    def _export_report(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        report = self._validate_model_snapshot(self.model)
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

    # -- model lifecycle helpers -------------------------------------------

    def _load_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        model = request.payload.get("model")
        if not isinstance(model, dict):
            return self._failure(
                request, ValidationReport(), "INVALID_PAYLOAD", "payload.model must be an object", before=before,
            )
        candidate = normalize_model(model)
        report = self._validate_model_snapshot(candidate)
        if not report.ok:
            return self._failure(request, report, "VALIDATION_FAILED", report.errors[0], before=before)
        should_commit = not request.options.dry_run and not request.options.validate_only and request.options.commit
        if should_commit:
            self._commit(candidate, request, before, [{"path": "$", "op": "replace"}])
        after_model = snapshot(self.model if should_commit else candidate)
        return self._success(
            request, report, {"loaded": True}, before, after_model, [{"path": "$", "op": "replace"}], ["$"],
        )

    def _replace_model(
        self, request: OperationRequest, before: dict[str, Any], model: dict[str, Any],
    ) -> OperationResult:
        after = normalize_model(model)
        return self._apply_success(request, {"replaced": True}, before, after, "$", "replace")

    def _diff_model(self, request: OperationRequest, before: dict[str, Any]) -> OperationResult:
        other = request.payload.get("other", request.payload.get("model", {}))
        if not isinstance(other, dict):
            return self._payload_error(request, before, "other model must be an object", "payload.other")
        return self._read_result(request, before, {"diff": self._deep_diff(self.model, normalize_model(other))})

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
