"""Tests for semantic gate registry and proposal helpers."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.application_services.report_system import build_report
from kicad_suite.application_services.semantic_gate_proposals import propose_gates_from_hardware_erc
from kicad_suite.application_services.semantic_gate_registry import (
    accept_proposed_gate,
    gate_filename,
    list_gate_specs,
    validate_gate_spec,
)


def _valid_gate() -> dict:
    return {
        "schema_version": "semantic-gate.v1",
        "gate_id": "hardware.usb_c_cc_missing_rd.v1",
        "title": "Hardware ERC: USB_C_CC_MISSING_RD",
        "status": "proposed",
        "severity": "BLOCKER",
        "scope": {"source": "hardware-erc"},
        "source_finding": {"code": "USB_C_CC_MISSING_RD"},
        "rules": [
            {
                "code": "USB_C_CC_MISSING_RD",
                "description": "USB-C CC pins require Rd pull-downs for sink designs.",
            }
        ],
    }


def test_validate_gate_spec_accepts_minimal_valid_gate():
    result = validate_gate_spec(_valid_gate())
    assert result.ok
    assert result.errors == []


def test_validate_gate_spec_rejects_missing_rules():
    gate = _valid_gate()
    gate.pop("rules")
    result = validate_gate_spec(gate)
    assert not result.ok
    assert any("rules" in error for error in result.errors)


def test_propose_gates_from_hardware_erc_writes_candidate(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "hardware-erc.v1.json").write_text(
        json.dumps(
            {
                "schema_version": "hardware-erc.v1",
                "ok": False,
                "summary": {"blockers": 1, "warnings": 0, "infos": 0},
                "blockers": [
                    {
                        "severity": "BLOCKER",
                        "code": "USB_C_CC_MISSING_RD",
                        "message": "CC pin is missing Rd.",
                        "component": "J1",
                        "pin": "CC1",
                        "net": "USB_CC1",
                    }
                ],
                "warnings": [],
                "infos": [],
            }
        ),
        encoding="utf-8",
    )

    result = propose_gates_from_hardware_erc(tmp_path)

    assert result["written"] == 1
    gate_path = tmp_path / "build" / "proposed-semantic-gates" / gate_filename("hardware.usb_c_cc_missing_rd.v1")
    assert gate_path.exists()
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate["status"] == "proposed"
    assert gate["rules"][0]["code"] == "USB_C_CC_MISSING_RD"


def test_accept_proposed_gate_promotes_to_project_source(tmp_path):
    proposed_dir = tmp_path / "build" / "proposed-semantic-gates"
    proposed_dir.mkdir(parents=True)
    gate = _valid_gate()
    (proposed_dir / gate_filename(gate["gate_id"])).write_text(json.dumps(gate), encoding="utf-8")

    result = accept_proposed_gate(tmp_path, gate["gate_id"])

    assert result["accepted"]
    accepted_path = tmp_path / "source" / "semantic-gates" / gate_filename(gate["gate_id"])
    assert accepted_path.exists()
    assert not (proposed_dir / gate_filename(gate["gate_id"])).exists()
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    assert accepted["status"] == "accepted"


def test_list_gate_specs_includes_proposed_and_accepted(tmp_path):
    accepted_dir = tmp_path / "source" / "semantic-gates"
    proposed_dir = tmp_path / "build" / "proposed-semantic-gates"
    accepted_dir.mkdir(parents=True)
    proposed_dir.mkdir(parents=True)
    accepted = _valid_gate() | {"status": "accepted"}
    proposed = _valid_gate() | {"gate_id": "hardware.load_switch_output_without_load.v1"}
    (accepted_dir / gate_filename(accepted["gate_id"])).write_text(json.dumps(accepted), encoding="utf-8")
    (proposed_dir / gate_filename(proposed["gate_id"])).write_text(json.dumps(proposed), encoding="utf-8")

    registry = list_gate_specs(tmp_path)

    statuses = {gate["gate_id"]: gate["status"] for gate in registry["gates"]}
    assert statuses["hardware.usb_c_cc_missing_rd.v1"] == "accepted"
    assert statuses["hardware.load_switch_output_without_load.v1"] == "proposed"


def test_report_includes_semantic_gate_review_queue(tmp_path):
    model_path = tmp_path / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        json.dumps(
            {
                "schema_version": "circuit-model.v1",
                "request_id": "demo",
                "project_id": "gate-demo",
                "topology": "gate_demo",
                "components": [],
                "nets": [],
            }
        ),
        encoding="utf-8",
    )
    proposed_dir = tmp_path / "build" / "proposed-semantic-gates"
    proposed_dir.mkdir(parents=True)
    gate = _valid_gate()
    (proposed_dir / gate_filename(gate["gate_id"])).write_text(json.dumps(gate), encoding="utf-8")

    report = build_report(tmp_path)

    section = next(item for item in report["sections"] if item["key"] == "semantic_gates")
    assert section["status"] == "warning"
    assert section["data"]["proposed"] == 1
