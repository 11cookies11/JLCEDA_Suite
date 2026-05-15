"""Generate BOM.csv from circuit model + LCSC parts map."""
import json, csv, io
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
parts_map = json.loads((REPO / 'examples/nema23-industrial-stepper-driver-v0.1/lcsc-parts-map.json').read_text(encoding='utf-8'))
model = json.loads((REPO / 'examples/nema23-industrial-stepper-driver-v0.1/nema23-industrial-stepper-driver-v0.1.circuit-model.json').read_text(encoding='utf-8'))

locked_semis = parts_map.get('locked_semiconductors', {})
standard_passives = parts_map.get('parts', {})

sem_role_map = {
    'stm32g4_mcu': 'mcu', 'buck_5v_regulator': 'buck_5v', 'ldo_3v3_regulator': 'ldo_3v3',
    'phase_a_high_half_bridge': 'gate_driver', 'phase_a_low_half_bridge': 'gate_driver',
    'phase_b_high_half_bridge': 'gate_driver', 'phase_b_low_half_bridge': 'gate_driver',
    'phase_a_high_left_mosfet': 'mosfet_power', 'phase_a_low_left_mosfet': 'mosfet_power',
    'phase_a_high_right_mosfet': 'mosfet_power', 'phase_a_low_right_mosfet': 'mosfet_power',
    'phase_b_high_left_mosfet': 'mosfet_power', 'phase_b_low_left_mosfet': 'mosfet_power',
    'phase_b_high_right_mosfet': 'mosfet_power', 'phase_b_low_right_mosfet': 'mosfet_power',
    'phase_a_current_sense_resistor': 'current_sense_shunt', 'phase_b_current_sense_resistor': 'current_sense_shunt',
    'phase_a_current_sense_amplifier': 'current_sense_amp', 'phase_b_current_sense_amplifier': 'current_sense_amp',
    'hardware_overcurrent_comparator': 'overcurrent_comparator',
    'motor_output_terminal': 'motor_terminal', 'power_input_terminal': 'power_input_terminal',
    'reverse_protection_pmos': 'pmos_reverse_protection_100V', 'bus_tvs_diode': 'bus_tvs_diode',
    'crystal_oscillator': 'crystal_8MHz_3225', 'usb_uart_bridge': 'usb_uart_bridge',
    'bus_bulk_capacitor': 'electrolytic_470uF_80V_radial',
}

passive_role_map = {
    'resistor': 'resistor_10k_0603_1pct', 'gate_resistor': 'resistor_10R_0603_5pct',
    'gate_source_resistor': 'resistor_100k_0603_1pct', 'power_led_resistor': 'resistor_1k_0603_1pct',
    'status_led_resistor': 'resistor_470R_0603_1pct', 'fault_led_resistor': 'resistor_470R_0603_1pct',
    'step_series_resistor': 'resistor_100R_0603_1pct', 'dir_series_resistor': 'resistor_100R_0603_1pct',
    'en_series_resistor': 'resistor_100R_0603_1pct', 'step_pullup_resistor': 'resistor_10k_0603_1pct',
    'dir_pullup_resistor': 'resistor_10k_0603_1pct', 'en_pullup_resistor': 'resistor_10k_0603_1pct',
    'nrst_pullup_resistor': 'resistor_10k_0603_1pct', 'boot0_pulldown_resistor': 'resistor_10k_0603_1pct',
    'bus_voltage_sense_top_resistor': 'resistor_200k_0603_1pct',
    'bus_voltage_sense_bottom_resistor': 'resistor_12k_0603_1pct',
    'temperature_bias_resistor': 'resistor_10k_0603_1pct',
    'reverse_protection_gate_resistor': 'resistor_10k_0603_1pct',
    'ia_adc_filter_resistor': 'resistor_100R_0603_1pct', 'ib_adc_filter_resistor': 'resistor_100R_0603_1pct',
    'usb_dp_resistor': 'resistor_22R_0603_1pct', 'usb_dn_resistor': 'resistor_22R_0603_1pct',
    'mcu_decoupling_capacitor': 'capacitor_100nF_50V_0603_X7R',
    'mcu_vdda_capacitor': 'capacitor_100nF_50V_0603_X7R',
    'gate_driver_decoupling_a': 'capacitor_10uF_25V_0805_X5R',
    'gate_driver_decoupling_b': 'capacitor_10uF_25V_0805_X5R',
    'nrst_filter_capacitor': 'capacitor_100nF_50V_0603_X7R',
    'crystal_load_capacitor': 'capacitor_12pF_50V_0603_NP0',
    'bootstrap_capacitor': 'capacitor_1uF_50V_0805_X7R',
    'buck_input_capacitor': 'capacitor_10uF_25V_0805_X5R',
    'buck_output_capacitor': 'capacitor_22uF_10V_1210_X5R',
    'buck_bootstrap_capacitor': 'capacitor_100nF_50V_0603_X7R',
    'ldo_input_capacitor': 'capacitor_10uF_25V_0805_X5R',
    'ldo_output_capacitor': 'capacitor_10uF_25V_0805_X5R',
    'bus_ceramic_capacitor': 'capacitor_100nF_100V_0805',
    'usb_vbus_capacitor': 'capacitor_10uF_25V_0805_X5R',
    'usb_uart_decoupling': 'capacitor_100nF_50V_0603_X7R',
    'usb_uart_3v3_capacitor': 'capacitor_100nF_50V_0603_X7R',
    'ia_adc_filter_capacitor': 'capacitor_1nF_50V_0603',
    'ib_adc_filter_capacitor': 'capacitor_1nF_50V_0603',
    'bus_sense_filter_capacitor': 'capacitor_10nF_50V_0603',
    'temp_sense_filter_capacitor': 'capacitor_10nF_50V_0603',
    'step_filter_capacitor': 'capacitor_1nF_50V_0603',
    'dir_filter_capacitor': 'capacitor_1nF_50V_0603',
    'en_filter_capacitor': 'capacitor_1nF_50V_0603',
    'power_led': 'led_green_0603', 'status_led': 'led_blue_0603', 'fault_led': 'led_red_0603',
    'step_esd_diode': 'esd_diode_sod523', 'dir_esd_diode': 'esd_diode_sod523', 'en_esd_diode': 'esd_diode_sod523',
    'buck_catch_diode': 'schottky_diode_sod123_1A_100V',
    'temperature_sense_ntc': 'ntc_10k_0603', 'input_fuse': 'fuse_1206_5A',
    'oc_reference_resistor': 'resistor_10k_0603_1pct',
}

# Also map second OC ref resistor role
passive_role_map['oc_reference_resistor'] = 'resistor_10k_0603_1pct'

bom = []
for c in model['components']:
    ref = c['ref']
    role = c['role']
    value = c['value']
    sp = c.get('selected_part', {})
    package = sp.get('package', '')
    lcsc_id = sp.get('lcsc_id', '')
    mpn = sp.get('mpn', '')
    manufacturer = sp.get('manufacturer', '')
    price = ''

    # Check locked semiconductor first
    sem_key = sem_role_map.get(role, '')
    if sem_key and sem_key in locked_semis:
        s = locked_semis[sem_key]
        lcsc_id = s.get('lcsc_id', lcsc_id)
        mpn = s.get('mpn', mpn)
        manufacturer = s.get('manufacturer', manufacturer)
    elif sem_key and sem_key in standard_passives:
        s = standard_passives[sem_key]
        lcsc_id = s.get('lcsc_id', lcsc_id)
        mpn = s.get('mpn', mpn)
        manufacturer = s.get('manufacturer', manufacturer)
    else:
        passive_key = passive_role_map.get(role)
        if passive_key and passive_key in standard_passives:
            s = standard_passives[passive_key]
            lcsc_id = s.get('lcsc_id', lcsc_id)
            mpn = s.get('mpn', mpn)
            manufacturer = s.get('manufacturer', manufacturer)

    if lcsc_id and lcsc_id in standard_passives:
        price = standard_passives[lcsc_id].get('price', '') if isinstance(standard_passives.get(lcsc_id), dict) else ''
    elif lcsc_id and sem_key in locked_semis:
        price = locked_semis[sem_key].get('price', '')

    # Look up price from parts map
    for pdata in [locked_semis.get(sem_key, {}), standard_passives.get(passive_role_map.get(role, ''), {})]:
        if isinstance(pdata, dict) and pdata.get('price'):
            price = pdata['price']

    bom.append({
        'Ref': ref, 'Role': role, 'Value': value,
        'MPN': mpn, 'Manufacturer': manufacturer,
        'LCSC_ID': lcsc_id, 'Package': package, 'Price_USD': price,
    })

output = io.StringIO()
writer = csv.DictWriter(output, fieldnames=['Ref', 'Role', 'Value', 'MPN', 'Manufacturer', 'LCSC_ID', 'Package', 'Price_USD'])
writer.writeheader()
writer.writerows(bom)

bom_path = REPO / '.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1/BOM.csv'
bom_path.parent.mkdir(parents=True, exist_ok=True)
bom_path.write_text(output.getvalue(), encoding='utf-8')

with_lcsc = sum(1 for b in bom if b['LCSC_ID'])
without_lcsc = sum(1 for b in bom if not b['LCSC_ID'])
total_price = sum(float(b['Price_USD']) for b in bom if b['Price_USD'] and str(b['Price_USD']).replace('.','').isdigit())

print(f'BOM: {len(bom)} lines -> {bom_path}')
print(f'With LCSC: {with_lcsc}, Pending: {without_lcsc}')
print(f'Estimated total (locked parts only): {total_price:.2f} USD')
pending = [b for b in bom if not b['LCSC_ID']]
if pending:
    print(f'Parts needing LCSC selection ({len(pending)}):')
    for p in pending:
        print(f'  {p["Ref"]} {p["Role"]} {p["Value"][:60]}')
