"""Regression tests for equivalent SPICE model generation."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.orchestration.circuit_pipeline import (  # noqa: E402
    NetlistComponent,
    NetlistModel,
    NetlistNet,
    NetlistPart,
    NetlistPin,
    NetlistSourceModel,
    build_spice_netlist_from_netlist,
    render_spice_netlist,
)
from kicad_suite.shared.schema_versions import CIRCUIT_MODEL_SCHEMA_VERSION, NETLIST_SCHEMA_VERSION  # noqa: E402


def _make_component(ref: str, role: str, value: str, pins: list[tuple[str, str]]) -> NetlistComponent:
    return NetlistComponent(
        ref=ref,
        role=role,
        value=value,
        part=NetlistPart(
            part_id=f'{ref}-part',
            display_name=role,
            pin_count=max(len(pins), 2),
            named_pin_count=max(len(pins), 2),
        ),
        pins=[NetlistPin(pin=pin, net=net) for pin, net in pins],
        availability_status='available',
    )


def _make_netlist() -> NetlistModel:
    components = [
        _make_component('U_BUCK', 'main_3v3_buck', 'SY8089A1AAC', [('1', 'VIN_5V'), ('2', 'GND'), ('3', 'SW'), ('4', 'FB')]),
        _make_component('L_BUCK', 'buck_power_inductor', '2.2uH', [('1', 'SW'), ('2', '+3V3_MAIN')]),
        _make_component('C_OUT', 'buck_output_capacitor', '22uF', [('1', '+3V3_MAIN'), ('2', 'GND')]),
        _make_component('D_ESD', 'usb_esd_protection', 'USBLC6-2SC6', [('1', 'USB_D_P'), ('2', 'GND')]),
        _make_component('D_TVS', 'usb_vbus_tvs_diode', 'SMF5.0A', [('1', 'VIN_5V'), ('2', 'GND')]),
        _make_component('D_LED', 'power_indicator_led', 'green LED', [('1', '+3V3_MAIN'), ('2', 'LED_A')]),
        _make_component('U_HOST', 'esp32c3_host_controller', 'ESP32-C3FH4X', [('1', '+3V3_MAIN'), ('2', 'GND')]),
        _make_component('J_USB', 'usb_c_input', 'USB-C-16P', []),
        _make_component('SW_BOOT', 'esp32_boot_button', 'TK-6580S-2', []),
    ]
    nets = [
        NetlistNet(name='VIN_5V', kind='power', members=['U_BUCK.1', 'D_TVS.1']),
        NetlistNet(name='GND', kind='ground', members=['U_BUCK.2', 'C_OUT.2', 'D_ESD.2', 'D_TVS.2', 'U_HOST.2']),
        NetlistNet(name='SW', kind='signal', members=['U_BUCK.3', 'L_BUCK.1']),
        NetlistNet(name='FB', kind='signal', members=['U_BUCK.4']),
        NetlistNet(name='+3V3_MAIN', kind='power', members=['L_BUCK.2', 'C_OUT.1', 'D_LED.1', 'U_HOST.1']),
        NetlistNet(name='USB_D_P', kind='signal', members=['D_ESD.1']),
        NetlistNet(name='LED_A', kind='signal', members=['D_LED.2']),
    ]
    return NetlistModel(
        schema_version=NETLIST_SCHEMA_VERSION,
        request_id='equivalent-models',
        project_id='equivalent-models',
        source_model=NetlistSourceModel(
            schema_version=CIRCUIT_MODEL_SCHEMA_VERSION,
            request_id='equivalent-models',
        ),
        components=components,
        nets=nets,
    )


class TestEquivalentSpiceModels(unittest.TestCase):
    def test_equivalent_models_cover_common_nexdap_roles(self) -> None:
        spice = build_spice_netlist_from_netlist(_make_netlist())
        rendered = render_spice_netlist(spice)

        self.assertIn('VU1_REG', rendered)
        self.assertIn('DC 3.3', rendered)
        self.assertIn('.model DTVS_EQ', rendered)
        self.assertIn('.model DLED_EQ', rendered)
        self.assertIn('omitted in equivalent model', rendered)
        self.assertTrue(all(item.supported for item in spice.lines if item.kind not in {'analysis', 'control'}))
        self.assertTrue(any('equivalent' in warning.lower() for warning in spice.warnings))


if __name__ == '__main__':
    unittest.main()
