"""Fix NEMA23 power supply: buck feedback, fuse, LDO stability, braking protection."""
import json
from pathlib import Path

model_path = Path('examples/nema23-industrial-stepper-driver-v0.1/nema23-industrial-stepper-driver-v0.1.circuit-model.json')
model = json.loads(model_path.read_text(encoding='utf-8'))

# === Fix 1: Buck feedback resistors for XL7015E1 ===
# Vout = 1.25*(1 + R1/R2), for 5V: R1=30k, R2=10k
model['components'].append({
    'ref': 'R_BUCK_FB1', 'role': 'buck_feedback_resistor_top',
    'value': '30k 1% 0603',
    'selected_part': {
        'part_id': 'buck-fb-top', 'display_name': 'Buck feedback resistor (top)',
        'package': 'Resistor_SMD:R_0603_1608Metric', 'pin_count': 2, 'named_pin_count': 2,
        'lcsc_id': 'C25804', 'mpn': '0603WAF1002T5E', 'availability_status': 'locked',
        'note': 'VOUT to FB. Vout=1.25*(1+30k/10k)=5.0V'
    },
    'candidate_parts': [], 'availability_status': 'locked',
})
model['components'].append({
    'ref': 'R_BUCK_FB2', 'role': 'buck_feedback_resistor_bottom',
    'value': '10k 1% 0603',
    'selected_part': {
        'part_id': 'buck-fb-bottom', 'display_name': 'Buck feedback resistor (bottom)',
        'package': 'Resistor_SMD:R_0603_1608Metric', 'pin_count': 2, 'named_pin_count': 2,
        'lcsc_id': 'C25804', 'mpn': '0603WAF1002T5E', 'availability_status': 'locked',
        'note': 'FB to GND. Vout=1.25*(1+30k/10k)=5.0V'
    },
    'candidate_parts': [], 'availability_status': 'locked',
})
# Soft-start cap for XL7015E1
model['components'].append({
    'ref': 'C_BUCK_SS', 'role': 'buck_soft_start_capacitor',
    'value': '100nF 50V 0603',
    'selected_part': {
        'part_id': 'buck-ss-cap', 'display_name': 'Buck soft-start capacitor',
        'package': 'Capacitor_SMD:C_0603_1608Metric', 'pin_count': 2, 'named_pin_count': 2,
        'lcsc_id': 'C14663', 'mpn': 'CC0603KRX7R9BB104', 'availability_status': 'locked',
    },
    'candidate_parts': [], 'availability_status': 'locked',
})

# === Fix 2: Fuse - replace 0.5A PTC with proper 5A SMD fuse ===
for c in model['components']:
    if c['ref'] == 'F1':
        sp = c['selected_part']
        sp['lcsc_id'] = 'C2838938'
        sp['mpn'] = '2410FA-5A'
        sp['manufacturer'] = 'CONQUER'
        sp['display_name'] = '5A 125V SMD fuse'
        sp['package'] = 'Fuse_SMD:Fuse_2410_6125Metric'
        sp['availability_status'] = 'locked'
        c['value'] = '5A 125V SMD fuse'
        c['availability_status'] = 'locked'
        c.setdefault('notes', []).append('5A 125V SMD fuse (2410 package). Replaces incorrect 0.5A PTC.')
        break

# === Fix 3: AMS1117 LDO ESR resistor ===
model['components'].append({
    'ref': 'R_LDO_ESR', 'role': 'ldo_output_esr_resistor',
    'value': '0.5R 0603',
    'selected_part': {
        'part_id': 'ldo-esr-r', 'display_name': 'LDO output ESR resistor',
        'package': 'Resistor_SMD:R_0603_1608Metric', 'pin_count': 2, 'named_pin_count': 2,
        'lcsc_id': 'C22758', 'mpn': '0603WAF100JT5E', 'availability_status': 'locked',
        'note': '0.5R ESR for AMS1117 stability with MLCC output cap.'
    },
    'candidate_parts': [], 'availability_status': 'locked',
})

# === Fix 4: Bus overvoltage protection ===
# 1500W SMC TVS for braking energy absorption
model['components'].append({
    'ref': 'D_BUS_CLAMP', 'role': 'bus_overvoltage_tvs',
    'value': 'SMCJ58A 1500W TVS',
    'selected_part': {
        'part_id': 'bus-ov-tvs', 'display_name': 'Bus overvoltage TVS (braking clamp)',
        'package': 'Diode_SMD:D_SMC', 'pin_count': 2, 'named_pin_count': 2,
        'lcsc_id': 'C353350', 'mpn': 'SMCJ58A', 'availability_status': 'locked',
        'note': '1500W TVS across VM_BUS for regenerative braking energy absorption.'
    },
    'candidate_parts': [], 'availability_status': 'locked',
})
# Active braking MOSFET + gate resistor (reserved for future)
model['components'].append({
    'ref': 'Q_BRAKE', 'role': 'braking_mosfet_switch',
    'value': 'N-MOSFET braking (reserved)',
    'selected_part': {
        'part_id': 'brake-mosfet', 'display_name': 'Braking MOSFET switch (reserved)',
        'package': 'Package_TO_SOT_SMD:TO-252-2', 'pin_count': 3, 'named_pin_count': 3,
        'lcsc_id': '', 'mpn': '', 'availability_status': 'unpopulated',
    },
    'candidate_parts': [], 'availability_status': 'unpopulated',
})
model['components'].append({
    'ref': 'RG_BRAKE', 'role': 'braking_gate_resistor',
    'value': '100R 0603 (reserved)',
    'selected_part': {
        'part_id': 'brake-gate-r', 'display_name': 'Braking MOSFET gate resistor (reserved)',
        'package': 'Resistor_SMD:R_0603_1608Metric', 'pin_count': 2, 'named_pin_count': 2,
        'lcsc_id': '', 'mpn': '', 'availability_status': 'unpopulated',
    },
    'candidate_parts': [], 'availability_status': 'unpopulated',
})

# === Add nets ===
new_nets = [
    {'name': 'BUCK_FB', 'members': ['U_BUCK.4', 'R_BUCK_FB1.2', 'R_BUCK_FB2.1']},
    {'name': 'BUCK_FB_TOP', 'members': ['R_BUCK_FB1.1', 'C_BUCK_OUT.1']},
    {'name': 'LDO_OUT_ESR', 'members': ['U_LDO.2', 'R_LDO_ESR.1']},
    {'name': 'LDO_OUT_FILT', 'members': ['R_LDO_ESR.2', 'C_LDO_OUT.1']},
    {'name': 'BRAKE_GATE', 'members': ['RG_BRAKE.1', 'U_MCU.43']},
    {'name': 'BRAKE_GATE_MOS', 'members': ['RG_BRAKE.2', 'Q_BRAKE.1']},
]
model['nets'].extend(new_nets)

# Update existing nets
for net in model['nets']:
    if net['name'] == 'GND':
        net['members'].extend(['R_BUCK_FB2.2', 'C_BUCK_SS.2', 'D_BUS_CLAMP.2', 'Q_BRAKE.3'])
    if net['name'] == 'VM_BUS':
        net['members'].append('D_BUS_CLAMP.1')
    if net['name'] == 'BUCK_BS_RTN':
        net['members'].extend(['C_BUCK_SS.1'])
    # LDO output now goes through ESR resistor
    if net['name'] == '+3V3':
        net['members'] = [m for m in net['members'] if m != 'U_LDO.2']

# Deduplicate GND
for net in model['nets']:
    if net['name'] in ('GND', '+5V', 'VM_BUS'):
        net['members'] = list(dict.fromkeys(net['members']))

# Add design decisions
model.setdefault('design_decisions', []).extend([
    {
        'title': 'Add buck feedback resistors (30k/10k) for XL7015E1 5V output',
        'rationale': 'XL7015E1 is adjustable output. R1=30k/R2=10k gives Vout=1.25*(1+3)=5.0V.',
        'impact': 'R_BUCK_FB1, R_BUCK_FB2, C_BUCK_SS added to power section.'
    },
    {
        'title': 'Fix fuse from 0.5A PTC to 5A SMD fuse (2410FA-5A)',
        'rationale': 'Original C165760 is 0.5A hold current. 24V/3A system needs 5A fuse.',
        'impact': 'F1 updated to C2838938 (2410FA-5A, 5A 125V SMD).'
    },
    {
        'title': 'Add 0.5R ESR resistor for AMS1117-3.3 stability',
        'rationale': 'AMS1117 needs ESR 0.1-10 ohm on output cap. MLCC ESR < 0.01 ohm causes oscillation.',
        'impact': 'R_LDO_ESR=0.5R added in series with C_LDO_OUT.'
    },
    {
        'title': 'Add 1500W SMC TVS for regenerative braking overvoltage protection',
        'rationale': 'Motor deceleration pumps energy back to DC bus. SMCJ58A 1500W TVS provides clamping. Q_BRAKE+RG_BRAKE reserved for active braking.',
        'impact': 'D_BUS_CLAMP across VM_BUS. Q_BRAKE, RG_BRAKE reserved unpopulated.'
    },
])

model_path.write_text(json.dumps(model, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

comps = model['components']
nets = model['nets']
locked = sum(1 for c in comps if c.get('availability_status') == 'locked')
unpop = sum(1 for c in comps if c.get('availability_status') == 'unpopulated')
print(f'Components: {len(comps)} ({locked} locked, {unpop} unpopulated), Nets: {len(nets)}')
print('Power supply fixes applied:')
print('  1. Buck feedback: R_BUCK_FB1(30k) + R_BUCK_FB2(10k) + C_BUCK_SS(100nF)')
print('  2. Fuse: 0.5A PTC -> 5A SMD (C2838938 2410FA-5A)')
print('  3. LDO ESR: R_LDO_ESR=0.5R in series with C_LDO_OUT')
print('  4. Braking: D_BUS_CLAMP (SMCJ58A) + Q_BRAKE/RG_BRAKE reserved')
