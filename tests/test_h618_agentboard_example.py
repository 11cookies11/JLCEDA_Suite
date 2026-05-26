"""Basic checks for the H618 AgentBoard V1 example scaffold."""

from __future__ import annotations

import json
from pathlib import Path


def test_h618_example_circuit_model_is_present_and_shaped():
    model_path = Path("examples/h618-agentboard-v1/circuit-model.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    assert model["schema_version"] == "circuit-model.v1"
    assert model["project_id"] == "h618-agentboard-v1"
    assert model["request_id"] == "h618-agentboard-v1-initial"
    assert model["topology"] == "h618_agentboard_v1_initial"
    assert len(model["components"]) >= 30
    assert len(model["nets"]) >= 18
    assert len(model["calculations"]) >= 4
    assert len(model["design_decisions"]) >= 4
    assert len(model["risks"]) >= 1


def test_h618_usb_c_power_input_has_explicit_sink_rd():
    model_path = Path("examples/h618-agentboard-v1/circuit-model.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}
    assert components["R5"]["role"] == "usb_c_cc1_sink_rd"
    assert components["R5"]["value"] == "5.1k"
    assert components["R6"]["role"] == "usb_c_cc2_sink_rd"
    assert components["R6"]["value"] == "5.1k"

    nets = {net["name"]: set(net["members"]) for net in model["nets"]}
    assert nets["USB_C_CC1"] == {"J1.A5", "R5.1"}
    assert nets["USB_C_CC2"] == {"J1.B5", "R6.1"}
    assert {"R5.2", "R6.2"}.issubset(nets["GND"])


def test_h618_usb_c_power_path_places_fuse_between_input_and_system_rail():
    model_path = Path("examples/h618-agentboard-v1/circuit-model.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    nets = {net["name"]: set(net["members"]) for net in model["nets"]}
    assert {"J1.A4B9", "J1.B4A9", "D1.1", "F1.1", "TP1.1"}.issubset(nets["+5V_IN"])
    assert "D1.2" in nets["GND"]
    assert "F1.2" not in nets["GND"]
    assert "F1.2" in nets["+5V_SYS"]


def test_h618_power_and_reset_defaults_are_explicit():
    model_path = Path("examples/h618-agentboard-v1/circuit-model.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}
    assert components["R7"]["role"] == "h618_reset_pullup"
    assert components["R8"]["role"] == "h618_fel_boot_pullup"
    assert components["TP9"]["value"] == "+1V2_DDR"
    assert components["TP10"]["value"] == "+0V9_DDR"

    nets = {net["name"]: set(net["members"]) for net in model["nets"]}
    assert {"R7.1", "R8.1", "U2.VDD2"}.issubset(nets["+3V3"])
    assert {"U2.VDD1", "TP4.1"}.issubset(nets["+1V1_CORE"])
    assert {"U2.VDDQ", "TP9.1"}.issubset(nets["+1V2_DDR"])
    assert "TP10.1" in nets["+0V9_DDR"]
    assert {"U2.RESET_N", "SW1.2", "TP7.1", "R7.2"}.issubset(nets["H618_RESET_N"])
    assert {"U2.BOOT0", "SW2.2", "TP8.1", "R8.2"}.issubset(nets["H618_FEL_BOOT"])
