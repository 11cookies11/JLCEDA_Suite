"""Tests for the Pin Manager."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.domain.core.pin_manager import PinManager, build_pin_assignment_table


def _make_ir():
    return {
        "schema_version": "ir.v1",
        "request_id": "test", "project_id": "test",
        "topology": "test",
        "components": [
            {"ref": "U1", "role": "mcu", "value": "ESP32-S3",
             "pins": [
                 {"number": "GPIO1", "net": "LED_R", "source": "pinmap"},
                 {"number": "GPIO2", "net": "LED_G", "source": "pinmap"},
                 {"number": "GPIO3", "net": "", "source": "pinmap"},
                 {"number": "GPIO21", "net": "I2C_SDA", "source": "pinmap"},
             ]},
        ],
        "nets": [
            {"name": "LED_R", "members": ["U1.GPIO1"]},
            {"name": "LED_G", "members": ["U1.GPIO2"]},
            {"name": "I2C_SDA", "members": ["U1.GPIO21"]},
        ],
        "pinmap": {
            "U1": {
                "GPIO1": {"net": "LED_R", "role": "led_r", "locked": True},
                "GPIO2": {"net": "LED_G", "role": "led_g"},
                "GPIO21": {"net": "I2C_SDA", "role": "i2c_sda", "locked": True},
            },
        },
        "sheets": [], "interfaces": [], "power_tree": [],
        "risks": [], "calculations": [], "design_decisions": [], "constraints": [],
    }


def test_list_all_returns_assigned_pins():
    pm = PinManager(_make_ir())
    pins = pm.list_all()
    assert len(pins) >= 2
    signals = {p["signal"] for p in pins}
    assert "led_r" in signals or "LED_R" in signals


def test_get_owner_returns_signal():
    pm = PinManager(_make_ir())
    owner = pm.get_owner("GPIO1", "U1")
    assert owner is not None
    assert "led_r" in owner["signal"] or "LED_R" in owner["signal"]


def test_get_owner_returns_none_for_free_pin():
    pm = PinManager(_make_ir())
    owner = pm.get_owner("GPIO99", "U1")
    assert owner is None


def test_is_locked_detects_locked_pin():
    pm = PinManager(_make_ir())
    assert pm.is_locked("GPIO1", "U1") is True
    assert pm.is_locked("GPIO2", "U1") is False


def test_check_conflict_returns_error_for_taken_pin():
    pm = PinManager(_make_ir())
    err = pm.check_conflict("GPIO2", "U1", "LED_BLUE")
    assert err is not None
    assert "GPIO2" in err


def test_check_conflict_returns_none_for_free_pin():
    pm = PinManager(_make_ir())
    err = pm.check_conflict("GPIO99", "U1", "LED_BLUE")
    assert err is None


def test_check_pin_capability_checks_adc():
    pm = PinManager(_make_ir(), mcu_family="ESP32-S3")
    err = pm.check_pin_capability("GPIO1", "ADC")
    assert err is None  # GPIO1 has ADC1_CH0


def test_list_free_returns_unused_gpios():
    pm = PinManager(_make_ir(), mcu_family="ESP32-S3")
    free = pm.list_free("U1")
    free_pins = {f["pin"] for f in free}
    assert "GPIO1" not in free_pins
    assert "GPIO2" not in free_pins
    assert "GPIO0" in free_pins


def test_build_assignment_table_renders_markdown():
    pm = PinManager(_make_ir())
    table = build_pin_assignment_table(pm)
    assert "| Pin |" in table
    assert "GPIO1" in table
