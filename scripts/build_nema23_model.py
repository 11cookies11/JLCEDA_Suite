"""Build expanded NEMA23 circuit model with all required functional blocks.

Adds LEDs, gate resistors, bootstrap capacitors, decoupling capacitors,
ADC RC filters, reverse-polarity protection, USB-UART, test points,
and other passive components to the V0.1 skeleton.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "examples" / "nema23-industrial-stepper-driver-v0.1" / "nema23-industrial-stepper-driver-v0.1.circuit-model.json"


def _comp(ref, role, value, part_id, display_name, package, pin_count, named_pin_count=None, notes=None):
    result = {
        "ref": ref,
        "role": role,
        "value": value,
        "selected_part": {
            "part_id": part_id,
            "display_name": display_name,
            "package": package,
            "pin_count": pin_count,
            "named_pin_count": named_pin_count or pin_count,
        },
        "candidate_parts": [],
        "availability_status": "unknown",
    }
    if notes:
        result["notes"] = notes
    return result


def _net(name, members):
    return {"name": name, "members": members}


def build_model():
    """Return the expanded circuit model dict."""
    components = [
        # =====================================================================
        # Block 1: Power Input & Protection (existing + new)
        # =====================================================================
        _comp("J1", "power_input_terminal", "18V-50V DC input",
              "power-input-terminal-pending", "2-pin high-current power input terminal",
              "TerminalBlock:TerminalBlock_bornier-2_P5.08mm", 2, 2,
              ["1=VM_IN, 2=GND. Final current rating and pitch require LCSC selection."]),
        _comp("F1", "input_fuse", "5A fuse/PTC",
              "input-fuse-pending", "Input fuse or resettable fuse",
              "Fuse:Fuse_1206_3216Metric", 2, 2),
        _comp("Q_REV", "reverse_protection_pmos", "PMOS reverse protection",
              "reverse-pmos-pending", "P-channel MOSFET reverse-polarity protection",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3,
              ["PMOS with gate pull-down to GND; body diode conducts forward then channel turns on."]),
        _comp("R_GATE_REV", "reverse_protection_gate_resistor", "10k gate pull-down",
              "resistor-10k-0603-pending", "10k 0603 resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("D_TVS", "bus_tvs_diode", "58V SMBJ-class TVS",
              "bus-tvs-pending", "Bus TVS diode",
              "Diode_SMD:D_SMB", 2, 2,
              ["TVS across VM_BUS to GND."]),

        # =====================================================================
        # Block 2: Bus Capacitance (existing + new)
        # =====================================================================
        _comp("C_BULK1", "bus_bulk_capacitor", "470uF 80V electrolytic",
              "bus-bulk-cap-pending", "Bus bulk electrolytic capacitor",
              "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", 2, 2),
        _comp("C_BUS_MLCC1", "bus_ceramic_capacitor", "1uF 100V X7R 1210",
              "bus-ceramic-cap-pending", "Bus ceramic decoupling capacitor",
              "Capacitor_SMD:C_1210_3225Metric", 2, 2),
        _comp("C_BUS_MLCC2", "bus_ceramic_capacitor", "100nF 100V X7R 0805",
              "bus-ceramic-cap-2-pending", "Bus ceramic decoupling capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("L_EMI", "emi_filter_inductor_reserved", "EMI ferrite bead / inductor reserved",
              "emi-inductor-reserved-pending", "EMI inductor or ferrite bead (reserved position)",
              "Inductor_SMD:L_1210_3225Metric", 2, 2,
              ["Reserved EMI filter position; can be replaced with 0R jumper for V0.1."]),
        _comp("R_BRAKE", "braking_resistor_reserved", "Braking dump resistor (reserved)",
              "braking-resistor-reserved-pending", "Braking dump resistor placeholder",
              "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm", 2, 2,
              ["Reserved for regenerative braking; not populated in V0.1."]),

        # =====================================================================
        # Block 3: Power Conversion — Buck 5V (existing + decoupling)
        # =====================================================================
        _comp("U_BUCK", "buck_5v_regulator", "60V to 5V buck regulator",
              "buck-5v-pending", "60V-capable 5V buck regulator",
              "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 8, 8),
        _comp("C_BUCK_IN", "buck_input_capacitor", "10uF 100V MLCC",
              "buck-input-cap-pending", "Buck input capacitor",
              "Capacitor_SMD:C_1210_3225Metric", 2, 2),
        _comp("C_BUCK_OUT", "buck_output_capacitor", "22uF 10V MLCC",
              "buck-output-cap-pending", "Buck output capacitor",
              "Capacitor_SMD:C_1210_3225Metric", 2, 2),
        _comp("C_BUCK_BS", "buck_bootstrap_capacitor", "100nF 50V",
              "buck-bs-cap-pending", "Buck bootstrap capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("L_BUCK", "buck_inductor", "47uH power inductor",
              "buck-inductor-pending", "Buck power inductor",
              "Inductor_SMD:L_12x12mm", 2, 2),
        _comp("D_BUCK", "buck_catch_diode", "Schottky catch diode",
              "buck-diode-pending", "Buck catch diode",
              "Diode_SMD:D_SMA", 2, 2),

        # =====================================================================
        # Block 4: LDO 3.3V (existing + decoupling)
        # =====================================================================
        _comp("U_LDO", "ldo_3v3_regulator", "5V to 3.3V LDO",
              "ldo-3v3-pending", "3.3V LDO regulator",
              "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 3, 3),
        _comp("C_LDO_IN", "ldo_input_capacitor", "10uF 10V MLCC",
              "ldo-input-cap-pending", "LDO input capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("C_LDO_OUT", "ldo_output_capacitor", "10uF 10V MLCC",
              "ldo-output-cap-pending", "LDO output capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),

        # =====================================================================
        # Block 5: MCU (existing + decoupling + support)
        # =====================================================================
        _comp("U_MCU", "stm32g4_mcu", "STM32G431CBT6",
              "stm32g431cbt6-pending", "STM32G431CBT6 motor-control MCU",
              "MCU_ST_STM32G4:STM32G431CBTx", 48, 48,
              ["LQFP-48 motor-control MCU."]),
        _comp("C_MCU_DEC1", "mcu_decoupling_capacitor", "100nF 10V X7R 0603",
              "mcu-decap-pending", "MCU VDD decoupling capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("C_MCU_DEC2", "mcu_decoupling_capacitor", "100nF 10V X7R 0603",
              "mcu-decap-pending", "MCU VDD decoupling capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("C_MCU_DEC3", "mcu_decoupling_capacitor", "100nF 10V X7R 0603",
              "mcu-decap-pending", "MCU VDD decoupling capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("C_MCU_DEC4", "mcu_decoupling_capacitor", "4.7uF 10V X7R 0805",
              "mcu-bulk-decap-pending", "MCU bulk decoupling capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("C_VDDA", "mcu_vdda_capacitor", "100nF 10V + 1uF 10V",
              "mcu-vdda-cap-pending", "MCU VDDA decoupling capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2,
              ["VDDA decoupling for ADC reference."]),
        _comp("R_NRST", "nrst_pullup_resistor", "10k pull-up",
              "resistor-10k-0603-pending", "10k 0603 resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_NRST", "nrst_filter_capacitor", "100nF",
              "cap-100nf-0603-pending", "NRST filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("R_BOOT0", "boot0_pulldown_resistor", "10k pull-down",
              "resistor-10k-0603-pending", "10k 0603 resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("Y_MCU", "mcu_crystal_oscillator", "8MHz crystal or OSC",
              "crystal-8mhz-pending", "8MHz crystal with load caps",
              "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", 4, 4,
              ["MCU HSE crystal."]),
        _comp("C_OSC1", "crystal_load_capacitor", "12pF 50V NP0 0603",
              "cap-12pf-0603-pending", "Crystal load capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("C_OSC2", "crystal_load_capacitor", "12pF 50V NP0 0603",
              "cap-12pf-0603-pending", "Crystal load capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 6: Gate Drivers (existing + bootstrap + decoupling)
        # =====================================================================
        _comp("U_GATE_A", "phase_a_gate_driver", "Phase A H-bridge gate driver",
              "phase-a-gate-driver-pending", "Phase A half-bridge gate driver",
              "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 8, 8,
              ["Half-bridge gate driver with bootstrap high-side supply."]),
        _comp("U_GATE_B", "phase_b_gate_driver", "Phase B H-bridge gate driver",
              "phase-b-gate-driver-pending", "Phase B half-bridge gate driver",
              "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 8, 8),
        _comp("C_BOOT_A", "phase_a_bootstrap_capacitor", "1uF 50V X7R 0805",
              "bootstrap-cap-pending", "Phase A bootstrap capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("C_BOOT_B", "phase_b_bootstrap_capacitor", "1uF 50V X7R 0805",
              "bootstrap-cap-pending", "Phase B bootstrap capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("C_GVDD_A", "gate_driver_decoupling_a", "10uF 25V MLCC 0805",
              "gate-driver-decap-pending", "Gate driver A VCC decoupling",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("C_GVDD_B", "gate_driver_decoupling_b", "10uF 25V MLCC 0805",
              "gate-driver-decap-pending", "Gate driver B VCC decoupling",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("D_BOOT_A", "phase_a_bootstrap_diode", "Bootstrap diode",
              "bootstrap-diode-pending", "Phase A bootstrap diode",
              "Diode_SMD:D_SOD-123", 2, 2),
        _comp("D_BOOT_B", "phase_b_bootstrap_diode", "Bootstrap diode",
              "bootstrap-diode-pending", "Phase B bootstrap diode",
              "Diode_SMD:D_SOD-123", 2, 2),

        # =====================================================================
        # Block 7: MOSFET Power Stage (existing) + gate resistors (new)
        # =====================================================================
        _comp("Q_A_HL", "phase_a_high_left_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_A_LL", "phase_a_low_left_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_A_HR", "phase_a_high_right_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_A_LR", "phase_a_low_right_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_B_HL", "phase_b_high_left_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_B_LL", "phase_b_low_left_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_B_HR", "phase_b_high_right_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        _comp("Q_B_LR", "phase_b_low_right_mosfet", "100V N-MOSFET",
              "power-mosfet-pending", "N-channel power MOSFET",
              "Package_TO_SOT_SMD:TO-252-2", 3, 3),
        # Gate resistors (one per MOSFET)
        _comp("RG_A_HL", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_A_LL", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_A_HR", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_A_LR", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_B_HL", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_B_LL", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_B_HR", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RG_B_LR", "gate_resistor", "10R 0603",
              "gate-resistor-pending", "MOSFET gate resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        # Gate-source pulldown resistors
        _comp("RGS_A_HL", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_A_LL", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_A_HR", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_A_LR", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_B_HL", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_B_LL", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_B_HR", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("RGS_B_LR", "gate_source_resistor", "100k 0603",
              "gs-pulldown-pending", "Gate-source pulldown resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 8: Current Sense (existing + filtering)
        # =====================================================================
        _comp("RSH_A", "phase_a_current_sense_resistor", "50mR 1% 2512",
              "phase-a-shunt-pending", "Phase A current sense shunt",
              "Resistor_SMD:R_2512_6332Metric", 2, 2,
              ["Kelvin connection required."]),
        _comp("RSH_B", "phase_b_current_sense_resistor", "50mR 1% 2512",
              "phase-b-shunt-pending", "Phase B current sense shunt",
              "Resistor_SMD:R_2512_6332Metric", 2, 2,
              ["Kelvin connection required."]),
        _comp("U_AMP_A", "phase_a_current_sense_amplifier", "Current sense amplifier A",
              "current-sense-amp-pending", "Current sense amplifier",
              "Package_TO_SOT_SMD:SOT-23-5", 5, 5),
        _comp("U_AMP_B", "phase_b_current_sense_amplifier", "Current sense amplifier B",
              "current-sense-amp-pending", "Current sense amplifier",
              "Package_TO_SOT_SMD:SOT-23-5", 5, 5),
        # ADC RC filters
        _comp("R_IA_FLT", "ia_adc_filter_resistor", "100R 0603",
              "adc-filter-r-pending", "ADC filter resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_IA_FLT", "ia_adc_filter_capacitor", "1nF 50V NP0 0603",
              "adc-filter-c-pending", "ADC filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("R_IB_FLT", "ib_adc_filter_resistor", "100R 0603",
              "adc-filter-r-pending", "ADC filter resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_IB_FLT", "ib_adc_filter_capacitor", "1nF 50V NP0 0603",
              "adc-filter-c-pending", "ADC filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 9: Hardware Overcurrent Comparator (existing)
        # =====================================================================
        _comp("U_OC", "hardware_overcurrent_comparator", "OC comparator",
              "overcurrent-comparator-pending", "Overcurrent comparator",
              "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 8, 8),
        _comp("R_OC_REF1", "oc_reference_resistor", "10k 1% 0603",
              "resistor-10k-0603-pending", "OC threshold divider resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_OC_REF2", "oc_reference_resistor", "2.2k 1% 0603",
              "resistor-2k2-0603-pending", "OC threshold divider resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 10: Bus Voltage Sense (existing + filter cap)
        # =====================================================================
        _comp("R_BUS_TOP", "bus_voltage_sense_top_resistor", "200k 0.1% 0603",
              "bus-divider-top-pending", "Bus divider top resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_BUS_BOT", "bus_voltage_sense_bottom_resistor", "12k 0.1% 0603",
              "bus-divider-bottom-pending", "Bus divider bottom resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_BUS_SENSE", "bus_sense_filter_capacitor", "10nF 50V NP0 0603",
              "bus-sense-cap-pending", "Bus sense filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 11: Temperature Sense (existing + filter cap)
        # =====================================================================
        _comp("R_NTC", "temperature_sense_ntc", "10k NTC 0603",
              "ntc-10k-pending", "10k NTC thermistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_TEMP_BIAS", "temperature_bias_resistor", "10k 1% 0603",
              "resistor-10k-0603-pending", "NTC bias resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_TEMP_FLT", "temp_sense_filter_capacitor", "10nF 50V NP0 0603",
              "temp-sense-cap-pending", "Temp sense filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 12: Motor Output Terminal (existing)
        # =====================================================================
        _comp("J_MOTOR", "motor_output_terminal", "A+ A- B+ B-",
              "motor-terminal-pending", "4-pin high-current motor terminal",
              "TerminalBlock:TerminalBlock_bornier-4_P5.08mm", 4, 4),
        # Output TVS and snubber (reserved)
        _comp("D_MOTOR_TVS1", "motor_tvs_reserved", "Motor output TVS (reserved)",
              "motor-tvs-reserved-pending", "Motor output TVS diode placeholder",
              "Diode_SMD:D_SMC", 2, 2,
              ["Reserved TVS across motor outputs; populate based on motor inductance."]),
        _comp("R_SNUB_A", "motor_snubber_reserved", "RC snubber A (reserved)",
              "snubber-r-reserved-pending", "Snubber resistor placeholder",
              "Resistor_SMD:R_1206_3216Metric", 2, 2,
              ["Reserved RC snubber for phase A."]),
        _comp("C_SNUB_A", "motor_snubber_reserved", "RC snubber A (reserved)",
              "snubber-c-reserved-pending", "Snubber capacitor placeholder",
              "Capacitor_SMD:C_1206_3216Metric", 2, 2),

        # =====================================================================
        # Block 13: STEP/DIR/EN Control Input (existing + protection)
        # =====================================================================
        _comp("J_CTRL", "step_dir_enable_input_header", "STEP DIR EN GND",
              "control-header-pending", "4-pin control input header",
              "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 4, 4),
        _comp("R_STEP_SERIES", "step_series_resistor", "100R 0603",
              "resistor-100r-0603-pending", "STEP series protection resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_DIR_SERIES", "dir_series_resistor", "100R 0603",
              "resistor-100r-0603-pending", "DIR series protection resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_EN_SERIES", "en_series_resistor", "100R 0603",
              "resistor-100r-0603-pending", "EN series protection resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_STEP_PU", "step_pullup_resistor", "10k 0603",
              "resistor-10k-0603-pending", "STEP pull-up to 3V3",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_DIR_PU", "dir_pullup_resistor", "10k 0603",
              "resistor-10k-0603-pending", "DIR pull-up to 3V3",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_EN_PU", "en_pullup_resistor", "10k 0603",
              "resistor-10k-0603-pending", "EN pull-up to 3V3",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_STEP_FLT", "step_filter_capacitor", "1nF 50V 0603",
              "step-filter-cap-pending", "STEP RC filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("C_DIR_FLT", "dir_filter_capacitor", "1nF 50V 0603",
              "dir-filter-cap-pending", "DIR RC filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("C_EN_FLT", "en_filter_capacitor", "1nF 50V 0603",
              "en-filter-cap-pending", "EN RC filter capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("D_ESD_STEP", "step_esd_diode", "ESD protection diode",
              "esd-diode-pending", "ESD protection diode",
              "Diode_SMD:D_SOD-523", 2, 2),
        _comp("D_ESD_DIR", "dir_esd_diode", "ESD protection diode",
              "esd-diode-pending", "ESD protection diode",
              "Diode_SMD:D_SOD-523", 2, 2),
        _comp("D_ESD_EN", "en_esd_diode", "ESD protection diode",
              "esd-diode-pending", "ESD protection diode",
              "Diode_SMD:D_SOD-523", 2, 2),

        # =====================================================================
        # Block 14: SWD Debug Header (existing)
        # =====================================================================
        _comp("J_SWD", "swd_debug_header", "SWD",
              "swd-header-pending", "5-pin SWD header",
              "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", 5, 5),

        # =====================================================================
        # Block 15: UART Debug (existing)
        # =====================================================================
        _comp("J_UART", "uart_debug_header", "UART",
              "uart-header-pending", "4-pin UART header",
              "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 4, 4),

        # =====================================================================
        # Block 16: USB-UART Bridge (new — optional)
        # =====================================================================
        _comp("U_USB_UART", "usb_uart_bridge", "CH340C USB-UART",
              "usb-uart-pending", "USB-UART bridge IC",
              "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", 16, 16,
              ["Optional USB-UART bridge for debug and configuration."]),
        _comp("J_USB", "usb_c_receptacle", "USB-C receptacle",
              "usb-c-receptacle-pending", "USB-C receptacle",
              "Connector:USB_C_Receptacle", 16, 6,
              ["USB-C connector for USB-UART; only USB2.0 D+/D- and VBUS/GND connected."]),
        _comp("C_USB_VBUS", "usb_vbus_capacitor", "10uF 10V 0805",
              "usb-vbus-cap-pending", "USB VBUS decoupling capacitor",
              "Capacitor_SMD:C_0805_2012Metric", 2, 2),
        _comp("C_USB_DEC", "usb_uart_decoupling", "100nF 10V 0603",
              "usb-uart-decap-pending", "USB-UART decoupling capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2),
        _comp("R_USB_DP", "usb_dp_resistor", "22R 0603",
              "usb-dp-r-pending", "USB D+ series resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("R_USB_DN", "usb_dn_resistor", "22R 0603",
              "usb-dn-r-pending", "USB D- series resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("C_USB_V3", "usb_uart_3v3_capacitor", "100nF 10V 0603",
              "usb-uart-v3-cap-pending", "CH340C V3 capacitor",
              "Capacitor_SMD:C_0603_1608Metric", 2, 2,
              ["CH340C V3 pin decoupling to GND."]),

        # =====================================================================
        # Block 17: Status LEDs (new)
        # =====================================================================
        _comp("D_PWR_LED", "power_led", "Green LED",
              "led-green-0603-pending", "Green LED 0603",
              "LED_SMD:LED_0603_1608Metric", 2, 2),
        _comp("R_PWR_LED", "power_led_resistor", "1k 0603",
              "resistor-1k-0603-pending", "LED current-limit resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("D_STAT_LED", "status_led", "Blue LED",
              "led-blue-0603-pending", "Blue LED 0603",
              "LED_SMD:LED_0603_1608Metric", 2, 2),
        _comp("R_STAT_LED", "status_led_resistor", "470R 0603",
              "resistor-470r-0603-pending", "LED current-limit resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),
        _comp("D_FAULT_LED", "fault_led", "Red LED",
              "led-red-0603-pending", "Red LED 0603",
              "LED_SMD:LED_0603_1608Metric", 2, 2),
        _comp("R_FAULT_LED", "fault_led_resistor", "470R 0603",
              "resistor-470r-0603-pending", "LED current-limit resistor",
              "Resistor_SMD:R_0603_1608Metric", 2, 2),

        # =====================================================================
        # Block 18: Test Points (new)
        # =====================================================================
        _comp("TP_GND", "test_point", "TP GND",
              "test-point-pending", "Test point",
              "TestPoint:TestPoint_Pad_D1.5mm", 1, 1),
        _comp("TP_3V3", "test_point", "TP 3V3",
              "test-point-pending", "Test point",
              "TestPoint:TestPoint_Pad_D1.5mm", 1, 1),
        _comp("TP_5V", "test_point", "TP 5V",
              "test-point-pending", "Test point",
              "TestPoint:TestPoint_Pad_D1.5mm", 1, 1),
        _comp("TP_VM", "test_point", "TP VM_BUS",
              "test-point-pending", "Test point",
              "TestPoint:TestPoint_Pad_D1.5mm", 1, 1),
        _comp("TP_IA", "test_point", "TP IA_ADC",
              "test-point-pending", "Test point",
              "TestPoint:TestPoint_Pad_D1.5mm", 1, 1),
        _comp("TP_IB", "test_point", "TP IB_ADC",
              "test-point-pending", "Test point",
              "TestPoint:TestPoint_Pad_D1.5mm", 1, 1),
    ]

    nets = [
        # =====================================================================
        # Power input nets
        # =====================================================================
        _net("VM_IN", ["J1.1", "F1.1"]),
        _net("VM_RAW", ["F1.2", "Q_REV.2", "L_EMI.1"]),
        _net("L_EMI_OUT", ["L_EMI.2", "R_GATE_REV.1"]),
        _net("GATE_REV", ["R_GATE_REV.2", "Q_REV.1"]),
        _net("VM_BUS", ["Q_REV.3", "D_TVS.1", "C_BULK1.1", "C_BUS_MLCC1.1", "C_BUS_MLCC2.1",
                        "U_BUCK.1", "C_BUCK_IN.1",
                        "Q_A_HL.2", "Q_A_HR.2", "Q_B_HL.2", "Q_B_HR.2",
                        "R_BUS_TOP.1", "R_BRAKE.1", "R_PWR_LED.1", "TP_VM.1"]),

        # =====================================================================
        # Braking resistor
        # =====================================================================
        _net("BRAKE_RTN", ["R_BRAKE.2", "GND"]),

        # =====================================================================
        # Buck 5V nets
        # =====================================================================
        _net("BUCK_SW", ["U_BUCK.3", "L_BUCK.1", "D_BUCK.1"]),
        _net("BUCK_FB", ["U_BUCK.5", "L_BUCK.2", "C_BUCK_OUT.1"]),
        _net("BUCK_BS", ["U_BUCK.6", "C_BUCK_BS.1"]),
        _net("BUCK_BS_RTN", ["C_BUCK_BS.2", "L_BUCK.2"]),
        _net("+5V", ["C_BUCK_OUT.1", "U_BUCK.5", "U_LDO.3", "C_LDO_IN.1",
                     "U_GATE_A.5", "C_GVDD_A.1", "U_GATE_B.5", "C_GVDD_B.1",
                     "D_BOOT_A.1", "D_BOOT_B.1", "TP_5V.1"]),

        # =====================================================================
        # LDO 3.3V nets
        # =====================================================================
        _net("+3V3", ["U_LDO.2", "C_LDO_OUT.1", "U_MCU.1",
                      "C_MCU_DEC1.1", "C_MCU_DEC2.1", "C_MCU_DEC3.1", "C_MCU_DEC4.1",
                      "C_VDDA.1", "R_NRST.1",
                      "U_AMP_A.5", "U_AMP_B.5", "U_OC.8",
                      "J_SWD.1", "J_UART.1",
                      "R_TEMP_BIAS.1",
                      "R_STEP_PU.1", "R_DIR_PU.1", "R_EN_PU.1",
                      "D_STAT_LED.1", "D_FAULT_LED.1",
                      "U_USB_UART.4", "C_USB_V3.1",
                      "TP_3V3.1"]),

        # =====================================================================
        # GND net — all ground connections
        # =====================================================================
        _net("GND", ["J1.2", "D_TVS.2", "C_BULK1.2", "C_BUS_MLCC1.2", "C_BUS_MLCC2.2",
                     "Q_REV.1", "R_GATE_REV.2",
                     "U_BUCK.2", "U_BUCK.4", "C_BUCK_IN.2", "C_BUCK_OUT.2", "D_BUCK.2",
                     "U_LDO.1", "C_LDO_IN.2", "C_LDO_OUT.2",
                     "U_MCU.8",
                     "C_MCU_DEC1.2", "C_MCU_DEC2.2", "C_MCU_DEC3.2", "C_MCU_DEC4.2",
                     "C_VDDA.2", "C_NRST.2", "R_BOOT0.2",
                     "U_GATE_A.2", "U_GATE_A.4", "C_GVDD_A.2",
                     "U_GATE_B.2", "U_GATE_B.4", "C_GVDD_B.2",
                     "Q_A_LL.3", "Q_A_LR.3", "Q_B_LL.3", "Q_B_LR.3",
                     "RSH_A.2", "RSH_B.2",
                     "U_AMP_A.2", "U_AMP_B.2",
                     "C_IA_FLT.2", "C_IB_FLT.2",
                     "U_OC.4",
                     "R_OC_REF2.2",
                     "R_BUS_BOT.2", "C_BUS_SENSE.2",
                     "R_NTC.2", "C_TEMP_FLT.2",
                     "J_CTRL.4",
                     "R_STEP_PU.2", "R_DIR_PU.2", "R_EN_PU.2",
                     "C_STEP_FLT.2", "C_DIR_FLT.2", "C_EN_FLT.2",
                     "D_ESD_STEP.2", "D_ESD_DIR.2", "D_ESD_EN.2",
                     "J_SWD.2", "J_UART.2",
                     "R_PWR_LED.2", "R_STAT_LED.2", "R_FAULT_LED.2",
                     "RGS_A_HL.2", "RGS_A_LL.2", "RGS_A_HR.2", "RGS_A_LR.2",
                     "RGS_B_HL.2", "RGS_B_LL.2", "RGS_B_HR.2", "RGS_B_LR.2",
                     "U_USB_UART.8", "C_USB_DEC.2", "C_USB_V3.2", "J_USB.5",
                     "C_USB_VBUS.2",
                     "D_PWR_LED.2", "D_STAT_LED.2", "D_FAULT_LED.2",
                     "Y_MCU.3", "Y_MCU.4", "C_OSC1.2", "C_OSC2.2",
                     "R_SNUB_A.2", "C_SNUB_A.2", "R_BRAKE.2",
                     "TP_GND.1"]),

        # =====================================================================
        # Motor output nets (Phase A & B)
        # =====================================================================
        _net("PHASE_A_PLUS", ["Q_A_HL.3", "Q_A_LL.2", "J_MOTOR.1", "C_BOOT_A.2", "D_MOTOR_TVS1.1"]),
        _net("PHASE_A_MINUS", ["Q_A_HR.3", "Q_A_LR.2", "J_MOTOR.2", "D_MOTOR_TVS1.2"]),
        _net("PHASE_B_PLUS", ["Q_B_HL.3", "Q_B_LL.2", "J_MOTOR.3", "C_BOOT_B.2"]),
        _net("PHASE_B_MINUS", ["Q_B_HR.3", "Q_B_LR.2", "J_MOTOR.4"]),

        # =====================================================================
        # Phase return nets (low-side MOSFET sources to shunt)
        # =====================================================================
        _net("PHASE_A_LOW_RETURN", ["Q_A_LL.3", "Q_A_LR.3", "RSH_A.1"]),
        _net("PHASE_B_LOW_RETURN", ["Q_B_LL.3", "Q_B_LR.3", "RSH_B.1"]),

        # =====================================================================
        # MCU PWM outputs to gate driver inputs
        # =====================================================================
        _net("PWM_AH", ["U_MCU.20", "U_GATE_A.1"]),
        _net("PWM_AL", ["U_MCU.21", "U_GATE_A.3"]),
        _net("PWM_BH", ["U_MCU.22", "U_GATE_B.1"]),
        _net("PWM_BL", ["U_MCU.23", "U_GATE_B.3"]),

        # =====================================================================
        # Gate driver outputs → gate resistors → MOSFET gates (A phase)
        # =====================================================================
        _net("GATE_A_HL_DRV", ["U_GATE_A.6", "RG_A_HL.1"]),
        _net("GATE_A_HL_GATE", ["RG_A_HL.2", "Q_A_HL.1", "RGS_A_HL.1"]),
        _net("GATE_A_LL_DRV", ["U_GATE_A.7", "RG_A_LL.1"]),
        _net("GATE_A_LL_GATE", ["RG_A_LL.2", "Q_A_LL.1", "RGS_A_LL.1"]),
        _net("GATE_A_HR_DRV", ["U_GATE_A.8", "RG_A_HR.1"]),
        _net("GATE_A_HR_GATE", ["RG_A_HR.2", "Q_A_HR.1", "RGS_A_HR.1"]),
        _net("GATE_A_LR_DRV", ["U_GATE_A.9", "RG_A_LR.1"]),
        _net("GATE_A_LR_GATE", ["RG_A_LR.2", "Q_A_LR.1", "RGS_A_LR.1"]),

        # =====================================================================
        # Gate driver outputs → gate resistors → MOSFET gates (B phase)
        # =====================================================================
        _net("GATE_B_HL_DRV", ["U_GATE_B.6", "RG_B_HL.1"]),
        _net("GATE_B_HL_GATE", ["RG_B_HL.2", "Q_B_HL.1", "RGS_B_HL.1"]),
        _net("GATE_B_LL_DRV", ["U_GATE_B.7", "RG_B_LL.1"]),
        _net("GATE_B_LL_GATE", ["RG_B_LL.2", "Q_B_LL.1", "RGS_B_LL.1"]),
        _net("GATE_B_HR_DRV", ["U_GATE_B.8", "RG_B_HR.1"]),
        _net("GATE_B_HR_GATE", ["RG_B_HR.2", "Q_B_HR.1", "RGS_B_HR.1"]),
        _net("GATE_B_LR_DRV", ["U_GATE_B.9", "RG_B_LR.1"]),
        _net("GATE_B_LR_GATE", ["RG_B_LR.2", "Q_B_LR.1", "RGS_B_LR.1"]),

        # =====================================================================
        # Bootstrap nets
        # =====================================================================
        _net("BOOT_A", ["D_BOOT_A.2", "C_BOOT_A.1", "U_GATE_A.7"]),
        _net("BOOT_B", ["D_BOOT_B.2", "C_BOOT_B.1", "U_GATE_B.7"]),

        # =====================================================================
        # Current sense nets
        # =====================================================================
        _net("IA_SENSE_RAW", ["RSH_A.1", "U_AMP_A.1", "U_AMP_A.3", "U_OC.1"]),
        _net("IB_SENSE_RAW", ["RSH_B.1", "U_AMP_B.1", "U_AMP_B.3", "U_OC.2"]),
        _net("IA_AMP_OUT", ["U_AMP_A.4", "R_IA_FLT.1"]),
        _net("IB_AMP_OUT", ["U_AMP_B.4", "R_IB_FLT.1"]),
        _net("IA_ADC", ["R_IA_FLT.2", "C_IA_FLT.1", "U_MCU.10", "TP_IA.1"]),
        _net("IB_ADC", ["R_IB_FLT.2", "C_IB_FLT.1", "U_MCU.11", "TP_IB.1"]),

        # =====================================================================
        # Overcurrent comparator nets
        # =====================================================================
        _net("OC_REF", ["R_OC_REF1.2", "R_OC_REF2.1", "U_OC.3"]),
        _net("OC_FAULT", ["U_OC.7", "U_MCU.24", "U_GATE_A.10", "U_GATE_B.10"]),

        # =====================================================================
        # Bus voltage sense nets
        # =====================================================================
        _net("BUS_VSENSE", ["R_BUS_TOP.2", "R_BUS_BOT.1", "C_BUS_SENSE.1", "U_MCU.12"]),

        # =====================================================================
        # Temperature sense nets
        # =====================================================================
        _net("TEMP_BIAS", ["R_TEMP_BIAS.2", "R_NTC.1", "C_TEMP_FLT.1", "U_MCU.13"]),

        # =====================================================================
        # Control input nets (STEP/DIR/EN)
        # =====================================================================
        _net("STEP_RAW", ["J_CTRL.1", "R_STEP_SERIES.1"]),
        _net("DIR_RAW", ["J_CTRL.2", "R_DIR_SERIES.1"]),
        _net("EN_RAW", ["J_CTRL.3", "R_EN_SERIES.1"]),
        _net("STEP_IN", ["R_STEP_SERIES.2", "R_STEP_PU.1", "C_STEP_FLT.1", "D_ESD_STEP.1", "U_MCU.30"]),
        _net("DIR_IN", ["R_DIR_SERIES.2", "R_DIR_PU.1", "C_DIR_FLT.1", "D_ESD_DIR.1", "U_MCU.31"]),
        _net("EN_IN", ["R_EN_SERIES.2", "R_EN_PU.1", "C_EN_FLT.1", "D_ESD_EN.1", "U_MCU.32"]),

        # =====================================================================
        # SWD nets
        # =====================================================================
        _net("SWDIO", ["J_SWD.3", "U_MCU.34"]),
        _net("SWCLK", ["J_SWD.4", "U_MCU.37"]),
        _net("NRST", ["J_SWD.5", "U_MCU.7", "R_NRST.2", "C_NRST.1"]),

        # =====================================================================
        # UART nets
        # =====================================================================
        _net("UART_TX", ["U_MCU.40", "J_UART.3", "U_USB_UART.2"]),
        _net("UART_RX", ["U_MCU.41", "J_UART.4", "U_USB_UART.3"]),

        # =====================================================================
        # USB-UART nets
        # =====================================================================
        _net("USB_VBUS", ["J_USB.1", "C_USB_VBUS.1"]),
        _net("USB_DP", ["J_USB.3", "R_USB_DP.1"]),
        _net("USB_DN", ["J_USB.4", "R_USB_DN.1"]),
        _net("USB_DP_UART", ["R_USB_DP.2", "U_USB_UART.6"]),
        _net("USB_DN_UART", ["R_USB_DN.2", "U_USB_UART.7"]),
        _net("USB_UART_DEC", ["U_USB_UART.16", "C_USB_DEC.1"]),

        # =====================================================================
        # MCU support nets
        # =====================================================================
        _net("MCU_BOOT0", ["U_MCU.44", "R_BOOT0.1"]),
        _net("MCU_OSC_IN", ["U_MCU.5", "Y_MCU.1", "C_OSC1.1"]),
        _net("MCU_OSC_OUT", ["U_MCU.6", "Y_MCU.2", "C_OSC2.1"]),
        _net("MCU_OSC_GND", ["Y_MCU.3", "Y_MCU.4", "C_OSC1.2", "C_OSC2.2"]),

        # =====================================================================
        # LED nets
        # =====================================================================
        _net("PWR_LED_NET", ["R_PWR_LED.2", "D_PWR_LED.1"]),
        _net("STAT_LED_IN", ["U_MCU.33", "R_STAT_LED.1"]),
        _net("STAT_LED_NET", ["R_STAT_LED.2", "D_STAT_LED.1"]),
        _net("FAULT_LED_IN", ["U_MCU.42", "R_FAULT_LED.1"]),
        _net("FAULT_LED_NET", ["R_FAULT_LED.2", "D_FAULT_LED.1"]),

        # =====================================================================
        # Snubber reserved
        # =====================================================================
        _net("SNUB_A", ["R_SNUB_A.1", "C_SNUB_A.1"]),
    ]

    return {
        "schema_version": "circuit-model.v1",
        "request_id": "nema23-industrial-stepper-driver-v0.1",
        "project_id": "nema23-industrial-stepper-driver-v0.1",
        "topology": "nema23_industrial_stepper_driver_v0_1",
        "components": components,
        "nets": nets,
        "calculations": [
            {
                "name": "phase_current_target",
                "formula": "I_peak = 3A, I_rms = 2A",
                "inputs": {"phase_current_rms_a": 2.0, "phase_current_peak_a": 3.0},
                "result": 3.0,
                "unit": "A_peak",
            },
            {
                "name": "bus_voltage_sense_ratio",
                "formula": "Vadc = Vbus * Rbottom / (Rtop + Rbottom)",
                "inputs": {"vbus_max_v": 50.0, "rtop_ohm": 200000.0, "rbottom_ohm": 12000.0},
                "result": 2.83,
                "unit": "V_at_50V",
            },
        ],
        "design_decisions": [
            {
                "title": "Use external gate drivers and MOSFET H-bridges",
                "rationale": "The V0.1 board validates an industrial stepper-driver architecture without integrated driver ICs.",
                "impact": "The design exposes gate driver, MOSFET, shunt, and hardware protection blocks for review.",
            },
            {
                "title": "Use STM32G4-class MCU",
                "rationale": "STM32G4 devices provide motor-control timers, complementary PWM, ADC synchronization, DMA, break inputs, UART, and SWD.",
                "impact": "The schematic skeleton reserves PWM, ADC, fault, STEP/DIR/EN, UART, and SWD nets.",
            },
            {
                "title": "Gate resistors and bootstrap capacitors added",
                "rationale": "Each MOSFET gate must have a series resistor to control switching speed and prevent ringing. Bootstrap capacitors are required for high-side N-MOSFET drive.",
                "impact": "Added 8 gate resistors, 8 gate-source pulldown resistors, and 2 bootstrap capacitors with bootstrap diodes.",
            },
            {
                "title": "ADC RC filters added for all analog inputs",
                "rationale": "Current sense, bus voltage sense, and temperature sense signals require anti-aliasing filters before the MCU ADC inputs.",
                "impact": "Added RC low-pass filters for IA, IB, VBUS, and TEMP ADC channels.",
            },
            {
                "title": "USB-UART bridge included as optional debug interface",
                "rationale": "A USB-UART bridge (CH340C-class) provides convenient debug and configuration access without requiring an external USB-UART adapter.",
                "impact": "Added USB-C connector and CH340C-class bridge IC connections, sharing TX/RX with the UART debug header.",
            },
            {
                "title": "Keep LCSC locking pending",
                "rationale": "Availability, stock, package, and EasyEDA/KiCad library quality must be checked live before locking fabrication parts.",
                "impact": "The model uses pending placeholder parts and requires a later part.lock.yaml pass.",
            },
        ],
        "risks": [
            "This is a KiCad skeleton model, not a production-ready schematic.",
            "Final LCSC part numbers are not locked; run resolver and datasheet review before fabrication.",
            "Gate-driver and MOSFET pairing is high risk until drive current, bootstrap behavior, UVLO, Qg, and dead-time behavior are verified.",
            "MOSFET thermal design and high-current terminal footprints require manual PCB review.",
            "Hardware overcurrent threshold values and comparator delay are not finalized.",
            "Bus regenerative energy handling is only reserved conceptually; braking dump control is not implemented in V0.1.",
            "Gate resistors may need tuning based on actual MOSFET Qg and driver strength to optimize switching losses vs EMI.",
            "Bootstrap capacitor values depend on gate driver switching frequency and MOSFET Qg; verify before fabrication.",
        ],
    }


if __name__ == "__main__":
    model = build_model()
    output_path = MODEL_PATH
    # Keep backup
    backup = MODEL_PATH.with_suffix(".circuit-model.json.bak")
    if MODEL_PATH.exists():
        backup.write_text(MODEL_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    output_path.write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(model['components'])} components, {len(model['nets'])} nets to {output_path}")
    print(f"Backup at {backup}")
