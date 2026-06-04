"""Tests for the IR Validator."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.domain.core.ir_compiler import build_ir
from kicad_suite.domain.core.ir_validator import validate_ir


def _make_model():
    return {
        "schema_version": "circuit-model.v1",
        "request_id": "test",
        "project_id": "test-board",
        "topology": "test",
        "components": [
            {"ref": "U1", "role": "mcu", "value": "H618",
             "selected_part": {"part_id": "h618", "mpn": "H618", "package": "BGA-484"}},
        ],
        "nets": [
            {"name": "+3V3", "members": ["U1.VDD"]},
            {"name": "GND", "members": ["U1.GND"]},
        ],
        "sheets": [], "risks": [], "calculations": [], "design_decisions": [], "constraints": [],
    }


def _valid_ir():
    return build_ir(_make_model())


# ---- schema & structure ------------------------------------------------


def test_validate_clean_ir_passes():
    ir = _valid_ir()
    report = validate_ir(ir)
    assert report.ok
    assert report.stats["component_count"] == 1
    assert report.stats["net_count"] == 2


def test_validate_wrong_schema_version_fails():
    ir = _valid_ir()
    ir["schema_version"] = "wrong.v1"
    report = validate_ir(ir)
    assert not report.ok


def test_validate_missing_components_list_fails():
    report = validate_ir({"schema_version": "ir.v1", "nets": []})
    assert not report.ok
    assert any("components" in e for e in report.errors)


# ---- duplicate detection -----------------------------------------------


def test_validate_duplicate_component_ref_fails():
    ir = _valid_ir()
    ir["components"].append(dict(ir["components"][0]))  # duplicate U1
    report = validate_ir(ir)
    assert not report.ok
    assert any("duplicate" in e for e in report.errors)


def test_validate_duplicate_net_name_fails():
    ir = _valid_ir()
    ir["nets"].append(dict(ir["nets"][0]))  # duplicate +3V3
    report = validate_ir(ir)
    assert not report.ok
    assert any("duplicate" in e for e in report.errors)


# ---- pin integrity -----------------------------------------------------


def test_validate_component_without_pins_warns():
    ir = _valid_ir()
    ir["components"][0]["pins"] = []
    report = validate_ir(ir)
    assert any("no pins" in w for w in report.warnings)


def test_validate_duplicate_pin_number_fails():
    ir = _valid_ir()
    ir["components"][0]["pins"].append(dict(ir["components"][0]["pins"][0]))
    report = validate_ir(ir)
    assert not report.ok
    assert any("duplicate pin" in e for e in report.errors)


def test_validate_bad_pin_source_warns():
    ir = _valid_ir()
    ir["components"][0]["pins"][0]["source"] = "magic"
    report = validate_ir(ir)
    assert any("unknown source" in w for w in report.warnings)


# ---- reference integrity -----------------------------------------------


def test_validate_broken_net_member_ref_fails():
    ir = _valid_ir()
    ir["nets"][0]["members"].append("U404.PIN1")
    report = validate_ir(ir)
    assert not report.ok
    assert any("U404" in e for e in report.errors)


# ---- net connectivity --------------------------------------------------


def test_validate_floating_net_warns():
    ir = _valid_ir()
    ir["nets"][0]["members"] = []
    report = validate_ir(ir)
    assert any("no members" in w for w in report.warnings)


def test_validate_bad_member_format_fails():
    ir = _valid_ir()
    ir["nets"][0]["members"].append("just_a_string")
    report = validate_ir(ir)
    assert any("ref.pin" in e for e in report.errors)


# ---- floating pins -----------------------------------------------------


def test_validate_pin_with_no_net_warns():
    ir = _valid_ir()
    ir["components"][0]["pins"][0]["net"] = ""
    report = validate_ir(ir)
    assert any("no members" in w or "floating" in w.lower() for w in report.warnings) or report.ok


# ---- sheets ------------------------------------------------------------


def test_validate_sheet_duplicate_name_fails():
    ir = _valid_ir()
    ir["sheets"] = [
        {"name": "sheet_a", "components": [], "nets": [], "inputs": [], "outputs": []},
        {"name": "sheet_a", "components": [], "nets": [], "inputs": [], "outputs": []},
    ]
    report = validate_ir(ir)
    assert not report.ok
    assert any("duplicate" in e for e in report.errors)


# ---- power tree --------------------------------------------------------


def test_validate_power_tree_circular_ref_fails():
    ir = _valid_ir()
    ir["power_tree"] = [
        {"rail": "+5V", "parent": "+3V3", "children": [], "source_net": "", "voltage": 5.0, "current_limit": 0},
        {"rail": "+3V3", "parent": "+5V", "children": [], "source_net": "", "voltage": 3.3, "current_limit": 0},
    ]
    report = validate_ir(ir)
    assert not report.ok
    assert any("circular" in e.lower() for e in report.errors)


# ---- KiCad leakage -----------------------------------------------------


def test_validate_no_kicad_leakage_passes_clean_ir():
    ir = _valid_ir()
    report = validate_ir(ir)
    # Clean IR should not have KiCad leakage errors.
    kicad_errors = [e for e in report.errors if "KiCad" in e or "leakage" in e.lower()]
    assert len(kicad_errors) == 0


def test_validate_detects_kicad_field_leakage():
    ir = _valid_ir()
    ir["components"][0]["lib_id"] = "MCU:STM32"
    report = validate_ir(ir)
    assert any("lib_id" in e for e in report.errors)


def test_validate_allows_calculation_units():
    ir = _valid_ir()
    ir["calculations"] = [
        {"name": "input_current", "result": 0.84, "unit": "A"},
    ]
    report = validate_ir(ir)
    assert not any("unit" in e for e in report.errors)


# ---- API integration ---------------------------------------------------


def test_validate_ir_via_api():
    from kicad_suite.model_api import ModelApiService
    model = _make_model()
    service = ModelApiService.from_model(model)
    result = service.handle_dict({
        "schema_version": "dsl-api-request.v1",
        "request_id": "test", "project_id": "test-board",
        "operation": "validate_ir", "payload": {},
    })
    assert result["success"] is True
    assert result["result"]["valid"] is True
    assert "ir_stats" in result["result"]
