"""Tests for the Resolved Hardware IR compiler."""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.domain.core.ir_compiler import build_ir


def _make_model(**overrides):
    model = {
        "schema_version": "circuit-model.v1",
        "request_id": "test",
        "project_id": "test-board",
        "topology": "test_board",
        "components": [
            {"ref": "U1", "role": "mcu", "value": "H618",
             "selected_part": {"part_id": "h618", "mpn": "H618", "package": "BGA-484"}},
            {"ref": "R1", "role": "resistor", "value": "10k",
             "selected_part": {"part_id": "r-0603", "package": "0603"}},
        ],
        "nets": [
            {"name": "+3V3", "members": ["U1.VDD", "R1.1"]},
            {"name": "GND", "members": ["U1.GND", "R1.2"]},
        ],
        "sheets": [],
        "risks": [],
        "calculations": [],
        "design_decisions": [],
        "constraints": [],
    }
    model.update(overrides)
    return model


# ---- schema ------------------------------------------------------------

def test_build_ir_produces_correct_schema_version():
    ir = build_ir(_make_model())
    assert ir["schema_version"] == "ir.v1"
    assert ir["request_id"] == "test"
    assert ir["project_id"] == "test-board"


# ---- components → pins ------------------------------------------------

def test_ir_components_have_pins_from_nets():
    ir = build_ir(_make_model())
    u1 = next(c for c in ir["components"] if c["ref"] == "U1")
    pin_nets = {p["number"]: p["net"] for p in u1["pins"]}
    assert "VDD" in pin_nets
    assert pin_nets["VDD"] == "+3V3"
    assert pin_nets["GND"] == "GND"


def test_ir_pins_have_source_field():
    ir = build_ir(_make_model())
    u1 = next(c for c in ir["components"] if c["ref"] == "U1")
    sources = {p["source"] for p in u1["pins"]}
    assert "netlist" in sources


def test_ir_pinmap_overrides_netlist_pins():
    model = _make_model()
    model["components"][0]["pinmap"] = {"VDD": {"net": "+5V", "locked": True}}
    ir = build_ir(model)
    u1 = next(c for c in ir["components"] if c["ref"] == "U1")
    vdd_pin = next(p for p in u1["pins"] if p["number"] == "VDD")
    assert vdd_pin["net"] == "+5V"
    assert vdd_pin["source"] == "pinmap"
    assert vdd_pin["locked"] is True


def test_ir_pinmap_only_pins_added():
    model = _make_model()
    model["components"][0]["pinmap"] = {"TEST": {"net": "", "locked": True, "role": "test_pin"}}
    ir = build_ir(model)
    u1 = next(c for c in ir["components"] if c["ref"] == "U1")
    test_pin = next((p for p in u1["pins"] if p["number"] == "TEST"), None)
    assert test_pin is not None
    assert test_pin["source"] == "pinmap"
    assert test_pin["name"] == "test_pin"


# ---- no KiCad fields in IR ---------------------------------------------

def test_ir_has_no_kicad_fields():
    ir = build_ir(_make_model())
    ir_str = json.dumps(ir)
    assert "lib_id" not in ir_str
    assert "AIAgent:" not in ir_str
    for c in ir["components"]:
        assert "lib_id" not in c
        assert "footprint" not in c
        assert "at" not in c
        assert "unit" not in c
        sp = c.get("selected_part", {})
        # package is a hardware fact — allowed
        assert "footprint" not in sp or not any(":" in str(sp.get(k, "")) for k in sp)


def test_ir_carries_top_level_package_into_selected_part():
    model = _make_model()
    model["components"][0]["selected_part"] = {"part_id": "h618", "mpn": "H618"}
    model["components"][0]["package"] = "BGA-484"
    ir = build_ir(model)
    u1 = next(c for c in ir["components"] if c["ref"] == "U1")
    assert u1["selected_part"]["package"] == "BGA-484"


# ---- power tree --------------------------------------------------------

def test_ir_power_tree_structure():
    model = _make_model()
    model["power_rails"] = [
        {"name": "+5V", "voltage": 5.0, "current_limit": 2.0},
        {"name": "+3V3", "voltage": 3.3, "parent": "+5V"},
        {"name": "+1V8", "voltage": 1.8, "parent": "+5V"},
    ]
    ir = build_ir(model)
    assert len(ir["power_tree"]) == 3
    p5 = next(r for r in ir["power_tree"] if r["rail"] == "+5V")
    assert "+3V3" in p5["children"]
    assert "+1V8" in p5["children"]


# ---- sheets ------------------------------------------------------------

def test_ir_sheets_assign_component():
    model = _make_model()
    model["components"][0]["sheet"] = "sheet_01_mcu"
    model["sheets"] = [{"name": "sheet_01_mcu", "components": ["U1"], "nets": [], "inputs": [], "outputs": []}]
    ir = build_ir(model)
    u1 = next(c for c in ir["components"] if c["ref"] == "U1")
    assert u1["assigned_sheet"] == "sheet_01_mcu"


# ---- reference validation ---------------------------------------------

def test_ir_reference_validation_raises_on_broken_refs():
    model = _make_model()
    model["nets"].append({"name": "BROKEN", "members": ["U404.PIN1"]})
    try:
        build_ir(model)
        assert False, "Expected ValueError for broken reference"
    except ValueError as exc:
        assert "U404" in str(exc)
        assert "BROKEN" in str(exc)


# ---- interfaces ---------------------------------------------------------

def test_ir_interfaces_from_constraints():
    model = _make_model()
    model["constraints"] = [{
        "name": "USB-C Port", "type": "interface_definition", "scope": "usb_power",
        "rules": ["+5V", "USB_DN", "USB_DP"],
    }]
    ir = build_ir(model)
    assert len(ir["interfaces"]) >= 1
    iface = ir["interfaces"][0]
    assert iface["name"] == "USB-C Port"
    assert "+5V" in iface["nets"]
    assert iface["type"] == "usb_power"
