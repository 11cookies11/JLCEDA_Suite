"""Regression tests for the controlled circuit-model DSL API skeleton."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.domain.core.compile_kicad_execution_plan import (
    KiCadDiagnostics,
    KiCadExecutionPlan,
    KiCadTarget,
)
from kicad_suite.cli import main
from kicad_suite.application_services.model_api.external_tools import external_tool_env, load_external_tools_config
from kicad_suite.model_api import CircuitModelRepository, ModelApiService


def _request(operation: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "dsl-api-request.v1",
        "request_id": f"req-{operation}",
        "project_id": "demo-board",
        "topology": "demo_board",
        "operation": operation,
        "payload": payload,
    }


def test_model_api_adds_component_and_returns_diff():
    service = ModelApiService()

    result = service.handle_dict(
        _request(
            "add_component",
            {
                "ref": "U1",
                "role": "mcu",
                "value": "GD32",
                "selected_part": {"part_id": "gd32-demo"},
            },
        )
    )

    assert result["schema_version"] == "dsl-api-result.v1"
    assert result["success"] is True
    assert result["result"] == {"ref": "U1"}
    diff_paths = [d["path"] for d in result["diff"]]
    assert "components[U1]" in diff_paths
    component_diff = next(d for d in result["diff"] if d["path"] == "components[U1]")
    assert component_diff["op"] == "add"
    assert service.model["components"][0]["ref"] == "U1"


def test_model_api_rejects_duplicate_component_without_mutating_model():
    service = ModelApiService()
    payload = {"ref": "U1", "role": "mcu", "value": "GD32"}

    first = service.handle_dict(_request("add_component", payload))
    second = service.handle_dict(_request("add_component", payload))

    assert first["success"] is True
    assert second["success"] is False
    assert second["errors"][0]["code"] == "ALREADY_EXISTS"
    assert len(service.model["components"]) == 1


def test_model_api_rejects_invalid_payload_before_dispatch():
    service = ModelApiService()

    result = service.handle_dict(_request("connect_member", {"net": "+3V3"}))

    assert result["success"] is False
    assert result["errors"][0]["code"] == "INVALID_PAYLOAD"
    assert "payload.member is required" in result["diagnostics"]["errors"][0]


def test_model_api_connects_net_member():
    service = ModelApiService()

    add_net = service.handle_dict(_request("add_net", {"name": "+3V3", "members": []}))
    connect = service.handle_dict(_request("connect_member", {"net": "+3V3", "member": "U1.VDD"}))

    assert add_net["success"] is True
    assert connect["success"] is True
    assert service.model["nets"][0]["members"] == ["U1.VDD"]


def test_model_api_dry_run_returns_snapshot_without_commit():
    service = ModelApiService()
    request = _request("add_net", {"name": "+5V"})
    request["options"] = {"dry_run": True}

    result = service.handle_dict(request)

    assert result["success"] is True
    assert result["after"]["nets"][0]["name"] == "+5V"
    assert service.model["nets"] == []


def test_model_api_repository_commits_to_circuit_model_file(tmp_path):
    model_path = tmp_path / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        json.dumps(
            {
                "schema_version": "circuit-model.v1",
                "request_id": "demo",
                "project_id": "demo-board",
                "topology": "demo_board",
                "components": [],
                "nets": [],
            }
        ),
        encoding="utf-8",
    )
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))

    result = service.handle_dict(_request("add_net", {"name": "+3V3", "members": []}))
    resolved_path = tmp_path / "build" / "circuit-model.resolved.json"
    saved_source = json.loads(model_path.read_text(encoding="utf-8"))
    saved_resolved = json.loads(resolved_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert saved_source["nets"] == []
    assert saved_resolved["nets"] == [{"name": "+3V3", "members": []}]


def test_model_api_repository_writes_operation_log_and_revision(tmp_path):
    model_path = tmp_path / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        json.dumps(
            {
                "schema_version": "circuit-model.v1",
                "request_id": "demo",
                "project_id": "demo-board",
                "topology": "demo_board",
                "components": [],
                "nets": [],
            }
        ),
        encoding="utf-8",
    )
    repository = CircuitModelRepository(model_path)
    service = ModelApiService.from_repository(repository)

    result = service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))
    log_entry = json.loads(repository.log_path.read_text(encoding="utf-8").splitlines()[0])

    assert result["success"] is True
    assert log_entry["operation"] == "add_component"
    assert log_entry["revision_id"] == "rev-000001"
    assert (repository.revisions_dir / "rev-000001.json").exists()


def test_model_api_repository_dry_run_does_not_write_file(tmp_path):
    model_path = tmp_path / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    original = {
        "schema_version": "circuit-model.v1",
        "request_id": "demo",
        "project_id": "demo-board",
        "topology": "demo_board",
        "components": [],
        "nets": [],
    }
    model_path.write_text(json.dumps(original), encoding="utf-8")
    service = ModelApiService.from_repository(CircuitModelRepository(model_path))
    request = _request("add_net", {"name": "+5V", "members": []})
    request["options"] = {"dry_run": True}

    result = service.handle_dict(request)
    saved = json.loads(model_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["after"]["nets"] == [{"name": "+5V", "members": []}]
    assert saved == original


def test_model_api_validation_rejects_duplicate_net_names():
    service = ModelApiService.from_model(
        {
            "schema_version": "circuit-model.v1",
            "request_id": "demo",
            "project_id": "demo-board",
            "topology": "demo_board",
            "components": [],
            "nets": [{"name": "+3V3", "members": []}, {"name": "+3V3", "members": []}],
        }
    )

    result = service.handle_dict(_request("validate_model", {}))

    assert result["success"] is False
    assert result["errors"][0]["code"] == "VALIDATION_FAILED"
    assert "duplicate nets.name" in result["diagnostics"]["errors"][0]


def test_model_api_cli_applies_request_to_model_file(tmp_path, capsys):
    model_path = tmp_path / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    request_path = tmp_path / "request.json"
    model_path.write_text(
        json.dumps(
            {
                "schema_version": "circuit-model.v1",
                "request_id": "demo",
                "project_id": "demo-board",
                "topology": "demo_board",
                "components": [],
                "nets": [],
            }
        ),
        encoding="utf-8",
    )
    request_path.write_text(
        json.dumps(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"})),
        encoding="utf-8",
    )

    code = main(["model-api", str(request_path), "--model", str(model_path)])
    output = json.loads(capsys.readouterr().out)
    resolved_path = tmp_path / "build" / "circuit-model.resolved.json"
    saved_source = json.loads(model_path.read_text(encoding="utf-8"))
    saved_resolved = json.loads(resolved_path.read_text(encoding="utf-8"))

    assert code == 0
    assert output["success"] is True
    assert saved_source["components"] == []
    assert saved_resolved["components"][0]["ref"] == "U1"


def test_model_api_creates_hardware_project_without_agent_scaffold(tmp_path):
    source_path = tmp_path / "source" / "circuit-model.source.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        json.dumps(
            {
                "schema_version": "circuit-model.v1",
                "request_id": "source-demo",
                "project_id": "source-board",
                "topology": "source_board",
                "components": [
                    {
                        "ref": "U1",
                        "role": "mcu",
                        "value": "GD32F303",
                        "selected_part": {"part_id": "gd32f303-c8t6", "package": "LQFP-48"},
                        "pinmap": {"1": {"net": "+3V3", "role": "VDD"}},
                    }
                ],
                "nets": [{"name": "+3V3", "members": ["U1.1"], "kind": "power"}],
            }
        ),
        encoding="utf-8",
    )
    project_dir = tmp_path / "generated-board"
    service = ModelApiService()

    result = service.handle_dict(
        _request(
            "create_hardware_project",
            {
                "project_dir": str(project_dir),
                "project_id": "generated-board",
                "title": "Generated Board",
                "topology": "generated_board",
                "source_model": str(source_path),
                "initialize_state": True,
                "validate_ir": True,
                "export_ir": True,
            },
        )
    )

    generated_source = json.loads((project_dir / "source" / "circuit-model.source.json").read_text(encoding="utf-8"))
    generated_resolved = json.loads((project_dir / "build" / "circuit-model.resolved.json").read_text(encoding="utf-8"))
    generated_state = json.loads((project_dir / "project.state.json").read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["result"]["design_intent"]["status"] == "warning"
    assert result["diagnostics"]["warnings"]
    assert any("design intent section" in warning.lower() for warning in result["diagnostics"]["warnings"])
    assert generated_source["project_id"] == "generated-board"
    assert generated_resolved["project_id"] == "generated-board"
    assert generated_source["topology"] == "generated_board"
    assert generated_state["status"] == "VALID"
    assert generated_state["diagnostics"]["warnings"] >= 1
    assert (project_dir / "build" / "ir.json").exists()
    assert not (project_dir / "agent").exists()


def test_model_api_creates_generic_project_template(tmp_path):
    project_dir = tmp_path / "generic-hardware-template"
    service = ModelApiService()

    result = service.handle_dict(
        _request(
            "create_project_template",
            {
                "project_dir": str(project_dir),
                "title": "Generic Hardware Template",
            },
        )
    )

    assert result["success"] is True
    assert (project_dir / "README.md").exists()
    assert (project_dir / "docs" / "00_requirements.md").exists()
    assert (project_dir / "hardware" / "schematic").exists()
    assert not (project_dir / "software").exists()
    assert not (project_dir / "agent").exists()


def test_model_api_updates_component_and_selected_part():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    update = service.handle_dict(_request("update_component", {"ref": "U1", "patch": {"value": "GD32F303"}}))
    selected = service.handle_dict(
        _request(
            "set_selected_part",
            {
                "ref": "U1",
                "part": {
                    "part_id": "gd32f303-c8t6",
                    "lcsc_id": "C123",
                    "package": "LQFP-48",
                },
            },
        )
    )

    assert update["success"] is True
    assert selected["success"] is True
    assert service.model["components"][0]["value"] == "GD32F303"
    assert service.model["components"][0]["selected_part"]["part_id"] == "gd32f303-c8t6"


def test_model_api_locks_and_unlocks_selected_part():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    locked = service.handle_dict(_request("lock_selected_part", {"ref": "U1"}))
    unlocked = service.handle_dict(_request("unlock_selected_part", {"ref": "U1"}))

    assert locked["success"] is True
    assert unlocked["success"] is True
    assert service.model["components"][0]["selected_part_locked"] is False


def test_model_api_adds_and_removes_candidate_part():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    add = service.handle_dict(
        _request("add_candidate_part", {"ref": "U1", "part": {"part_id": "candidate-a", "lcsc_id": "C1"}})
    )
    remove = service.handle_dict(_request("remove_candidate_part", {"ref": "U1", "part_id": "candidate-a"}))

    assert add["success"] is True
    assert remove["success"] is True
    assert service.model["components"][0]["candidate_parts"] == []


def test_model_api_updates_net_and_disconnects_member():
    service = ModelApiService()
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": ["U1.VDD"]}))

    update = service.handle_dict(_request("update_net", {"name": "+3V3", "patch": {"notes": ["logic rail"]}}))
    disconnect = service.handle_dict(_request("disconnect_member", {"net": "+3V3", "member": "U1.VDD"}))

    assert update["success"] is True
    assert disconnect["success"] is True
    assert service.model["nets"][0]["notes"] == ["logic rail"]
    assert service.model["nets"][0]["members"] == []


def test_model_api_removes_component_and_cleans_net_members():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": ["U1.VDD", "J1.1"]}))

    result = service.handle_dict(_request("remove_component", {"ref": "U1"}))

    assert result["success"] is True
    assert service.model["components"] == []
    assert service.model["nets"][0]["members"] == ["J1.1"]


def test_model_api_removes_net():
    service = ModelApiService()
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": []}))

    result = service.handle_dict(_request("remove_net", {"name": "+3V3"}))

    assert result["success"] is True
    assert service.model["nets"] == []


def test_model_api_updates_metadata_and_searches_components():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "pmic", "value": "AXP313A"}))

    metadata = service.handle_dict(_request("update_metadata", {"topology": "new_topology"}))
    search = service.handle_dict(_request("search_components", {"query": "AXP"}))

    assert metadata["success"] is True
    assert service.model["topology"] == "new_topology"
    assert search["result"]["components"][0]["ref"] == "U1"


def test_model_api_batch_applies_operations_atomically():
    service = ModelApiService()

    result = service.handle_dict(
        _request(
            "apply_batch",
            {
                "operations": [
                    {"operation": "add_component", "payload": {"ref": "U1", "role": "mcu", "value": "GD32"}},
                    {"operation": "add_net", "payload": {"name": "+3V3", "members": []}},
                    {"operation": "connect_member", "payload": {"net": "+3V3", "member": "U1.VDD"}},
                ]
            },
        )
    )

    assert result["success"] is True
    assert service.model["components"][0]["ref"] == "U1"
    assert service.model["nets"][0]["members"] == ["U1.VDD"]


def test_model_api_generic_risk_decision_sheet_and_constraint_crud():
    service = ModelApiService()

    risk = service.handle_dict(_request("add_risk", {"key": "ddr", "title": "DDR review"}))
    decision = service.handle_dict(_request("add_design_decision", {"title": "Use LPDDR4", "status": "accepted"}))
    sheet = service.handle_dict(_request("add_sheet", {"name": "memory", "components": [], "nets": []}))
    constraint = service.handle_dict(_request("add_constraint", {"name": "hs-usb", "type": "high_speed"}))
    mark = service.handle_dict(_request("mark_risk_resolved", {"key": "ddr"}))

    assert risk["success"] is True
    assert decision["success"] is True
    assert sheet["success"] is True
    assert constraint["success"] is True
    assert mark["success"] is True
    assert service.model["risks"][0]["status"] == "resolved"


def test_model_api_link_operations_update_source_entity():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "soc", "value": "H618"}))
    service.handle_dict(_request("add_net", {"name": "DRAM_DQ0", "members": []}))
    service.handle_dict(_request("add_risk", {"key": "ddr", "title": "DDR timing"}))
    service.handle_dict(_request("add_design_decision", {"title": "Use LPDDR4", "status": "proposed"}))

    risk_link = service.handle_dict(_request("link_risk_to_net", {"key": "ddr", "target": "DRAM_DQ0"}))
    decision_link = service.handle_dict(
        _request("link_decision_to_component", {"decision": "Use LPDDR4", "target": "U1"})
    )

    assert risk_link["success"] is True
    assert decision_link["success"] is True
    assert service.model["risks"][0]["nets"] == ["DRAM_DQ0"]
    assert service.model["design_decisions"][0]["components"] == ["U1"]


def test_model_api_set_risk_due_reason_keeps_full_field_name():
    service = ModelApiService()
    service.handle_dict(_request("add_risk", {"key": "pmic-seq", "title": "PMIC sequencing"}))

    result = service.handle_dict(_request("set_risk_due_reason", {"key": "pmic-seq", "value": "await datasheet"}))

    assert result["success"] is True
    assert service.model["risks"][0]["due_reason"] == "await datasheet"
    assert "reason" not in service.model["risks"][0]


def test_model_api_pinmap_connects_pin_to_net():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    result = service.handle_dict(_request("connect_pin_to_net", {"ref": "U1", "pin": "VDD", "net": "+3V3"}))

    assert result["success"] is True
    assert service.model["components"][0]["pinmap"]["VDD"]["net"] == "+3V3"
    assert service.model["nets"][0]["members"] == ["U1.VDD"]


def test_model_api_power_rail_and_validation_operations():
    service = ModelApiService()

    add = service.handle_dict(_request("add_power_rail", {"name": "+3V3", "voltage": 3.3}))
    validate = service.handle_dict(_request("validate_power_tree", {}))

    assert add["success"] is True
    assert validate["success"] is True
    assert service.model["power_rails"][0]["name"] == "+3V3"


def test_model_api_readiness_fails_on_broken_references():
    service = ModelApiService()
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": ["U404.VDD"]}))

    result = service.handle_dict(_request("validate_readiness", {}))

    assert result["success"] is False
    assert "references missing component" in result["diagnostics"]["errors"][0]


def test_model_api_readiness_fails_on_missing_design_intent():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "main_controller_bare_soc", "value": "ESP32-S3"}))

    result = service.handle_dict(_request("validate_readiness", {}))

    assert result["success"] is False
    assert any("design intent" in message.lower() for message in result["diagnostics"]["warnings"] + result["diagnostics"]["errors"])


def test_model_api_validate_intent_is_available_as_dedicated_gate():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "main_controller_bare_soc", "value": "ESP32-S3"}))

    result = service.handle_dict(_request("validate_intent", {}))

    assert result["success"] is False
    assert any("design_decisions" in message for message in result["diagnostics"]["errors"])


def test_model_api_pinmap_validation_fails_on_missing_net():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))
    service.handle_dict(_request("set_pinmap", {"ref": "U1", "pinmap": {"VDD": {"net": "+3V3"}}}))

    result = service.handle_dict(_request("validate_pinmap", {}))

    assert result["success"] is False
    assert "references missing net" in result["diagnostics"]["errors"][0]


def test_model_api_compile_netlist_uses_existing_pipeline_builder():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": ["U1.VDD"]}))

    result = service.handle_dict(_request("compile_netlist", {}))

    assert result["success"] is True
    assert result["result"]["netlist"]["schema_version"] == "netlist.v1"
    assert result["result"]["netlist"]["components"][0]["ref"] == "U1"


def test_model_api_compile_spice_netlist_returns_schema_payload():
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "R1", "role": "resistor", "value": "10k"}))
    service.handle_dict(_request("add_net", {"name": "N1", "members": ["R1.1"]}))
    service.handle_dict(_request("add_net", {"name": "N2", "members": ["R1.2"]}))

    result = service.handle_dict(_request("compile_spice_netlist", {}))

    assert result["success"] is True
    assert result["result"]["spice_netlist"]["schema_version"] == "spice-netlist.v1"
    assert result["result"]["spice_netlist"]["lines"][-1]["text"] == ".end"


def test_model_api_run_simulation_plan_writes_artifacts(tmp_path):
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    result = service.handle_dict(_request("run_simulation_plan", {"output_dir": str(tmp_path)}))

    assert result["success"] is True
    assert result["result"]["simulation"]["plan_file"]
    assert (tmp_path / "simulation-plan.json").exists()


def test_model_api_export_kicad_project_uses_ir_backend(tmp_path):
    fake_plan = KiCadExecutionPlan(
        schema_version="kicad-execution-plan.v1",
        request_id="req-export",
        target=KiCadTarget(
            project_name="demo",
            output_dir=str(tmp_path / "demo"),
            schematic_file=str(tmp_path / "demo" / "demo.kicad_sch"),
            project_file=str(tmp_path / "demo" / "demo.kicad_pro"),
        ),
        symbols=[],
        nets=[],
        diagnostics=KiCadDiagnostics(),
    )
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    with patch("kicad_suite.application_services.model_api.handlers_extended.ir_to_kicad", return_value=fake_plan) as ir_to_kicad:
        with patch(
            "kicad_suite.application_services.model_api.handlers_extended.write_project",
            return_value={"project_file": str(tmp_path / "demo" / "demo.kicad_pro")},
        ) as write_project:
            result = service.handle_dict(
                _request(
                    "export_kicad_project",
                    {"output_dir": str(tmp_path), "project_name": "demo"},
                )
            )

    assert result["success"] is True
    ir_to_kicad.assert_called_once()
    assert ir_to_kicad.call_args.args[0]["schema_version"] == "ir.v1"
    write_project.assert_called_once()


def test_deep_diff_nested_change_detects_field_level_paths():
    """When a nested component field changes, the diff path drills into that field."""
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    update = service.handle_dict(_request("update_component", {"ref": "U1", "patch": {"value": "GD32F303"}}))

    assert update["success"] is True
    diff_paths = [d["path"] for d in update["diff"]]
    # The diff should contain a nested path into the component's value field.
    value_paths = [p for p in diff_paths if "value" in p and "U1" in p]
    assert len(value_paths) > 0, f"Expected nested diff path with U1.value, got {diff_paths}"


def test_deep_diff_net_member_change_detects_array_element():
    """When a net member changes, the diff identifies the changed array element."""
    service = ModelApiService()
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": ["U1.VDD"]}))

    connect = service.handle_dict(_request("connect_member", {"net": "+3V3", "member": "U2.VDD"}))

    assert connect["success"] is True
    diff_paths = [d["path"] for d in connect["diff"]]
    member_paths = [p for p in diff_paths if "members" in p or "+3V3" in p]
    assert len(member_paths) > 0, f"Expected diff path referencing net members, got {diff_paths}"


def test_payload_validation_update_component_requires_patch():
    """update_component without a patch dict returns INVALID_PAYLOAD."""
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    result = service.handle_dict(_request("update_component", {"ref": "U1"}))

    assert result["success"] is False
    assert result["errors"][0]["code"] == "INVALID_PAYLOAD"


def test_payload_validation_set_selected_part_requires_part():
    """set_selected_part without a part dict returns INVALID_PAYLOAD."""
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    result = service.handle_dict(_request("set_selected_part", {"ref": "U1"}))

    assert result["success"] is False
    assert result["errors"][0]["code"] == "INVALID_PAYLOAD"


def test_payload_validation_rename_net_requires_old_name():
    """rename_net without old_name returns INVALID_PAYLOAD."""
    service = ModelApiService()
    service.handle_dict(_request("add_net", {"name": "+3V3", "members": []}))

    result = service.handle_dict(_request("rename_net", {"new_name": "+5V"}))

    assert result["success"] is False
    assert result["errors"][0]["code"] == "INVALID_PAYLOAD"


def test_deep_diff_model_compares_nested_structures():
    """diff_model produces nested diff paths when models differ in nested fields."""
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    other = {
        "schema_version": "circuit-model.v1",
        "request_id": "other",
        "project_id": "other-board",
        "topology": "other",
        "components": [{"ref": "U1", "role": "mcu", "value": "GD32F303"}],
        "nets": [],
    }
    result = service.handle_dict(_request("diff_model", {"other": other}))

    assert result["success"] is True
    diff = result["result"]["diff"]
    diff_paths = [d["path"] for d in diff]
    assert len(diff) > 0
    assert any("U1" in p for p in diff_paths)


def test_external_tools_config_sets_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "external-tools.local.json"
    config_path.write_text(
        json.dumps(
            {
                "kicad": {
                    "cli_bin": "C:/KiCad/bin/kicad-cli.exe",
                    "timeout_sec": 12,
                    "erc": {"format": "json", "exit_code_violations": True},
                },
                "ngspice": {"bin": "C:/Spice/ngspice.exe"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("KICAD_CLI_BIN", raising=False)
    config = load_external_tools_config(config_path)

    with external_tool_env(config):
        assert os.environ["KICAD_CLI_BIN"] == "C:/KiCad/bin/kicad-cli.exe"
        assert os.environ["KICAD_CLI_TIMEOUT_SEC"] == "12"
        assert os.environ["KICAD_ERC_EXIT_CODE_VIOLATIONS"] == "true"
        assert os.environ["NGSPICE_BIN"] == "C:/Spice/ngspice.exe"

    assert "KICAD_CLI_BIN" not in os.environ


def test_model_api_run_simulation_plan_uses_config_output_dir(tmp_path):
    config_path = tmp_path / "external-tools.local.json"
    output_dir = tmp_path / "sim-out"
    config_path.write_text(json.dumps({"simulation": {"output_dir": str(output_dir)}}), encoding="utf-8")
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    result = service.handle_dict(_request("run_simulation_plan", {"config": str(config_path)}))

    assert result["success"] is True
    assert (output_dir / "simulation-plan.json").exists()
