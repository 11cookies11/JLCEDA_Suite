"""Basic checks for the H618 AgentBoard V1 example scaffold."""

from __future__ import annotations

import json
import re
from pathlib import Path


def test_h618_example_circuit_model_is_present_and_shaped():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
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
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
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
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    nets = {net["name"]: set(net["members"]) for net in model["nets"]}
    assert {"J1.A4B9", "J1.B4A9", "D1.1", "F1.1", "TP1.1"}.issubset(nets["+5V_IN"])
    assert "D1.2" in nets["GND"]
    assert "F1.2" not in nets["GND"]
    assert "F1.2" in nets["+5V_SYS"]


def test_h618_power_and_reset_defaults_are_explicit():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}
    assert components["R3"]["role"] == "h618_pmic_pwron_pullup"
    assert components["R7"]["role"] == "h618_reset_pullup"
    assert components["R8"]["role"] == "h618_fel_boot_pullup"
    assert components["R9"]["role"] == "spi_nor_wp_pullup"
    assert components["R10"]["role"] == "spi_nor_hold_pullup"
    assert components["R11"]["role"] == "micro_sd_cmd_pullup"
    assert components["R12"]["role"] == "micro_sd_dat0_pullup"
    assert components["R13"]["role"] == "micro_sd_dat1_pullup"
    assert components["R14"]["role"] == "micro_sd_dat2_pullup"
    assert components["R15"]["role"] == "micro_sd_dat3_pullup"
    assert components["J3"]["role"] == "h618_debug_uart_header"
    assert components["TP9"]["value"] == "+1V2_DDR"
    assert components["TP10"]["value"] == "+0V9_DDR"

    nets = {net["name"]: set(net["members"]) for net in model["nets"]}
    assert {"R7.1", "R8.1", "R9.1", "R10.1", "R11.1", "R12.1", "R13.1", "R14.1", "R15.1", "U2.VDD2"}.issubset(nets["+3V3"])
    assert {"U2.VDD1", "TP4.1"}.issubset(nets["+1V1_CORE"])
    assert {"U2.VDDQ", "TP9.1"}.issubset(nets["+1V2_DDR"])
    assert "TP10.1" in nets["+0V9_DDR"]
    assert {"U2.RESET_N", "SW1.2", "TP7.1", "R7.2"}.issubset(nets["H618_RESET_N"])
    assert {"U2.BOOT0", "SW2.2", "TP8.1", "R8.2"}.issubset(nets["H618_FEL_BOOT"])
    assert {"U2.PH0", "J3.2", "TP5.1"}.issubset(nets["H618_UART0_TX"])
    assert {"U2.PH1", "J3.3", "TP6.1"}.issubset(nets["H618_UART0_RX"])
    assert {"U1.11", "U2.PMIC_INT_N"}.issubset(nets["H618_PMIC_INT"])
    assert {"U2.SD_CMD", "J2.3", "R11.2"}.issubset(nets["H618_SD_CMD"])
    assert {"U2.SD_D0", "J2.7", "R12.2"}.issubset(nets["H618_SD_D0"])
    assert {"U2.SD_D1", "J2.8", "R13.2"}.issubset(nets["H618_SD_D1"])
    assert {"U2.SD_D2", "J2.1", "R14.2"}.issubset(nets["H618_SD_D2"])
    assert {"U2.SD_D3", "J2.2", "R15.2"}.issubset(nets["H618_SD_D3"])
    assert {"U4.3", "R9.2"}.issubset(nets["H618_SPI0_WP_N"])
    assert {"U4.7", "R10.2"}.issubset(nets["H618_SPI0_HOLD_N"])


def test_h618_lpddr4_remains_a_constrained_skeleton_domain():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}
    assert components["U3"]["role"] == "lpddr4_2gb_memory"
    assert any("resolved for the current H618/H616-derived board revision" in note for note in components["U3"]["notes"])

    nets = {net["name"]: set(net["members"]) for net in model["nets"]}
    lpddr4_nets = sorted(name for name in nets if name.startswith("H618_LPDDR4_"))
    assert lpddr4_nets == [
        "H618_LPDDR4_CKE",
        "H618_LPDDR4_DQ0",
        "H618_LPDDR4_DQ1",
        "H618_LPDDR4_DQ2",
        "H618_LPDDR4_DQ3",
    ]
    assert {"U3.VDDQ", "U2.VDDQ", "TP9.1"}.issubset(nets["+1V2_DDR"])
    assert "TP10.1" in nets["+0V9_DDR"]

    decisions = model["design_decisions"]
    assert any(decision["title"] == "Resolve DDR topology for V1" for decision in decisions)
    risks = model["risks"]
    assert any("LPDDR4 is resolved to the current V1 board topology" in risk for risk in risks)


def test_h618_high_speed_interfaces_remain_reference_captured_domains():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}
    assert any("Power-path protection and CC behavior are resolved" in note for note in components["J1"]["notes"])
    assert any("PMIC choice is resolved" in note for note in components["U1"]["notes"])
    assert any("RGMII timing and magnetics selection are resolved" in note for note in components["U5"]["notes"])
    assert any("resolved board revision" in note for note in components["U6"]["notes"])
    assert any("stage 4 reference-capture path" in note for note in components["J6"]["notes"])
    assert any("stage 4 checklist" in note for note in components["J7"]["notes"])
    assert any("stage 4 checklist" in note for note in components["J8"]["notes"])
    assert any("HDMI connector and protection choices are resolved" in note for note in components["J9"]["notes"])

    decisions = model["design_decisions"]
    assert any(
        decision["title"] == "Resolve high-speed interfaces for V1"
        for decision in decisions
    )

    risks = model["risks"]
    assert any("high-speed interface capture is now part of the resolved H618 V1 revision" in risk for risk in risks)


def test_h618_procurement_settles_standard_bom_items():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}

    assert components["F1"]["availability_status"] == "available"
    assert components["F1"]["selected_part"]["lcsc_id"] == "C91409"
    assert components["D1"]["availability_status"] == "available"
    assert components["D1"]["selected_part"]["lcsc_id"] == "C918847"
    assert components["SW1"]["availability_status"] == "available"
    assert components["SW1"]["selected_part"]["lcsc_id"] == "C528775"
    assert components["SW2"]["availability_status"] == "available"
    assert components["SW2"]["selected_part"]["lcsc_id"] == "C528775"

    assert components["C1"]["availability_status"] == "available"
    assert components["C1"]["selected_part"]["lcsc_id"] == "C49326300"
    assert components["C3"]["availability_status"] == "available"
    assert components["C3"]["selected_part"]["lcsc_id"] == "C1575"
    assert components["C5"]["availability_status"] == "available"
    assert components["C5"]["selected_part"]["lcsc_id"] == "C2179526"
    assert components["C8"]["availability_status"] == "available"
    assert components["C8"]["selected_part"]["lcsc_id"] == "C49326689"

    for ref in ("TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7", "TP8", "TP9", "TP10"):
        assert components[ref]["availability_status"] == "available"
        assert components[ref]["selected_part"]["part_id"] == "tp-1p"
        assert components[ref]["selected_part"]["package"] == "1-pin SMD test point"
        assert components[ref]["selected_part"]["kicad_footprint_hint"] == "JLC-MCP:TP-SMD_1P"


def test_h618_all_components_have_a_settled_availability_state():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    statuses = {component["availability_status"] for component in model["components"]}
    assert statuses == {"available"}
    assert not any("Must confirm" in note for component in model["components"] for note in component.get("notes", []))


def test_h618_core_blocks_are_marked_as_resolved_not_pending():
    model_path = Path("examples/h618-agentboard-v1/source/circuit-model.source.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))

    components = {component["ref"]: component for component in model["components"]}
    for ref in ("U1", "U2", "U3", "U5", "U6", "J1", "J9"):
        notes = components[ref].get("notes", [])
        assert all("Must confirm" not in note for note in notes)

    risks = model["risks"]
    assert not any("Must confirm: DDR initialization may fail" in risk for risk in risks)
    assert not any("Must confirm: PMIC and sequencing details still require final confirmation" in risk for risk in risks)
    assert not any("Must confirm: U2 H618 pinmap" in risk for risk in risks)
    assert not any("Must confirm: RGMII timing and USB hub integration" in risk for risk in risks)
    assert not any("Must confirm: HDMI interface details" in risk for risk in risks)


def test_h618_kicad_schematic_is_grouped_into_reviewable_sheets():
    config_path = Path("config/kicad-layout-profiles.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    profile = config["profiles"]["h618_agentboard_v1_initial"]
    sheet_groups = profile["sheet_groups"]

    assert [group["name"] for group in sheet_groups] == [
        "power_entry_pmic",
        "soc_boot_clock",
        "memory_ddr",
        "boot_storage",
        "debug_control",
        "network",
        "usb",
        "display_expansion",
    ]
    assert len(sheet_groups) == 8


def test_h618_lpddr4_multi_unit_instances_keep_distinct_units():
    schematic_path = Path(
        "examples/h618-agentboard-v1/output/v1/"
        "h618_agentboard_v1_initial/03_memory_ddr.kicad_sch"
    )
    schematic = schematic_path.read_text(encoding="utf-8")

    assert re.search(
        r'\(lib_id "jlc_symbols:H9HCNNNBKUMLXR-NEE"\).*?'
        r'\(unit 2\).*?'
        r'\(reference "U3"\)\s*'
        r'\(unit 2\)',
        schematic,
        flags=re.S,
    )
    assert not re.search(
        r'\(lib_id "jlc_symbols:H9HCNNNBKUMLXR-NEE"\).*?'
        r'\(unit 2\).*?'
        r'\(reference "U3"\)\s*'
        r'\(unit 1\)',
        schematic,
        flags=re.S,
    )
