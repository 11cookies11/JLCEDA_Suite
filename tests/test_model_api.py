"""Regression tests for the controlled circuit-model DSL API skeleton."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.cli import main
from kicad_suite.model_api.external_tools import external_tool_env, load_external_tools_config
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
    assert result["diff"] == [{"path": "components[U1]", "op": "add"}]
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
    model_path = tmp_path / "circuit-model.json"
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
    saved = json.loads(model_path.read_text(encoding="utf-8"))

    assert result["success"] is True
    assert saved["nets"] == [{"name": "+3V3", "members": []}]


def test_model_api_repository_writes_operation_log_and_revision(tmp_path):
    model_path = tmp_path / "circuit-model.json"
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
    model_path = tmp_path / "circuit-model.json"
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
    model_path = tmp_path / "circuit-model.json"
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
    saved = json.loads(model_path.read_text(encoding="utf-8"))

    assert code == 0
    assert output["success"] is True
    assert saved["components"][0]["ref"] == "U1"


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


def test_model_api_run_simulation_plan_writes_artifacts(tmp_path):
    service = ModelApiService()
    service.handle_dict(_request("add_component", {"ref": "U1", "role": "mcu", "value": "GD32"}))

    result = service.handle_dict(_request("run_simulation_plan", {"output_dir": str(tmp_path)}))

    assert result["success"] is True
    assert result["result"]["simulation"]["plan_file"]
    assert (tmp_path / "simulation-plan.json").exists()


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
