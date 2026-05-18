"""Tests for simulation plan generation."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.simulation_planner import build_ngspice_task_plan, build_simulation_plan, default_simulation_profile


class TestSimulationPlanner(unittest.TestCase):
    def test_nexdap_style_model_generates_multiple_scenarios(self) -> None:
        model = {
            "schema_version": "circuit-model.v1",
            "request_id": "nexdap-request",
            "project_id": "nexdap-project",
            "topology": "nexdap_style",
            "components": [
                {"ref": "U1", "role": "main_3v3_buck", "value": "SY8089A1AAC"},
                {"ref": "F1", "role": "usb_vbus_ptc_fuse", "value": "SMD1206-050-33"},
                {"ref": "D1", "role": "usb_vbus_tvs_diode", "value": "SMF5.0A"},
                {"ref": "R1", "role": "esp_chip_en_pullup", "value": "10k"},
                {"ref": "U2", "role": "rp2040_target_swd_uart_coprocessor", "value": "RP2040"},
                {"ref": "J1", "role": "target_power_enable_jumper", "value": "Jumper"},
                {"ref": "LED1", "role": "power_indicator_led", "value": "Green"},
            ],
            "nets": [
                {"name": "USB_VBUS", "members": ["F1.1"]},
                {"name": "+3V3_MAIN", "members": ["U1.2"]},
                {"name": "VTREF_TARGET", "members": ["R1.1"]},
                {"name": "RP_BOOTSEL_QSPI_SS", "members": ["U2.1"]},
                {"name": "+5V_TGT", "members": ["J1.1"]},
                {"name": "LED_PWR", "members": ["LED1.1"]},
            ],
            "calculations": [],
            "design_decisions": [],
            "risks": [],
        }
        profile = default_simulation_profile(model)
        plan = build_simulation_plan(model, profile)
        task_plan = build_ngspice_task_plan(model, profile=profile, plan=plan)
        scenario_ids = {scenario.scenario_id for scenario in plan.scenarios}
        self.assertIn("power-startup", scenario_ids)
        self.assertIn("usb-input-protection", scenario_ids)
        self.assertIn("esp32-startup-and-strap", scenario_ids)
        self.assertIn("rp2040-debug-and-bootsel", scenario_ids)
        self.assertIn("target-power-path", scenario_ids)
        self.assertIn("indicator-current", scenario_ids)
        self.assertIn("interface-bias", scenario_ids)
        self.assertGreaterEqual(plan.summary["scenario_count"], 7)
        self.assertEqual(task_plan.summary["task_count"], plan.summary["scenario_count"])
        self.assertEqual(task_plan.tasks[0].backend, "ngspice")
        self.assertIn("ngspice", task_plan.tasks[0].command[0])
