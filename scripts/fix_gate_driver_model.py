"""Patch NEMA23 circuit model: 2x16p full-bridge -> 4x8p half-bridge gate drivers."""
import json
from pathlib import Path

model_path = Path('examples/nema23-industrial-stepper-driver-v0.1/nema23-industrial-stepper-driver-v0.1.circuit-model.json')
model = json.loads(model_path.read_text(encoding='utf-8'))

# Step 1: Remove old 16-pin gate drivers
model['components'] = [c for c in model['components'] if c['ref'] not in {'U_GATE_A', 'U_GATE_B'}]

# Step 2: Add 4 new 8-pin half-bridge gate drivers
for ref, role, display in [
    ('U_GATE_AH', 'phase_a_high_half_bridge', 'Phase A high-side half-bridge'),
    ('U_GATE_AL', 'phase_a_low_half_bridge', 'Phase A low-side half-bridge'),
    ('U_GATE_BH', 'phase_b_high_half_bridge', 'Phase B high-side half-bridge'),
    ('U_GATE_BL', 'phase_b_low_half_bridge', 'Phase B low-side half-bridge'),
]:
    model['components'].append({
        'ref': ref, 'role': role, 'value': 'IRS2104STR half-bridge gate driver',
        'selected_part': {
            'part_id': 'irs2104str-locked', 'display_name': display,
            'package': 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
            'pin_count': 8, 'named_pin_count': 8,
            'mpn': 'IRS2104STR(UMW)', 'manufacturer': 'UMW',
            'lcsc_id': 'C20623202', 'availability_status': 'locked',
        },
        'candidate_parts': [], 'availability_status': 'locked',
    })

# Step 3: Replace 2 bootstrap caps with 4
model['components'] = [c for c in model['components'] if c['ref'] not in {'C_BOOT_A', 'C_BOOT_B', 'D_BOOT_A', 'D_BOOT_B', 'C_GVDD_A', 'C_GVDD_B'}]
for ref in ['C_BOOT_AH', 'C_BOOT_AL', 'C_BOOT_BH', 'C_BOOT_BL']:
    model['components'].append({
        'ref': ref, 'role': 'bootstrap_capacitor', 'value': '1uF 50V X7R 0805',
        'selected_part': {'part_id': 'bootstrap-cap-locked', 'display_name': 'Bootstrap capacitor',
            'package': 'Capacitor_SMD:C_0805_2012Metric', 'pin_count': 2, 'named_pin_count': 2,
            'lcsc_id': 'C15850', 'mpn': 'CC0805KRX7R9BB105', 'availability_status': 'locked'},
        'candidate_parts': [], 'availability_status': 'locked',
    })

# Step 4: Remove old gate + bootstrap nets
remove_nets = {
    'GATE_A_HL_DRV', 'GATE_A_HL_GATE', 'GATE_A_LL_DRV', 'GATE_A_LL_GATE',
    'GATE_A_HR_DRV', 'GATE_A_HR_GATE', 'GATE_A_LR_DRV', 'GATE_A_LR_GATE',
    'GATE_B_HL_DRV', 'GATE_B_HL_GATE', 'GATE_B_LL_DRV', 'GATE_B_LL_GATE',
    'GATE_B_HR_DRV', 'GATE_B_HR_GATE', 'GATE_B_LR_DRV', 'GATE_B_LR_GATE',
    'BOOT_A', 'BOOT_B',
}
model['nets'] = [n for n in model['nets'] if n['name'] not in remove_nets]

# Step 5: Add new gate drive and bootstrap nets
new_nets = [
    # Phase A high-side half-bridge: drives left leg
    {'name': 'GATE_AH_HO', 'members': ['U_GATE_AH.7', 'RG_A_HL.1']},
    {'name': 'GATE_AH_HO_MOS', 'members': ['RG_A_HL.2', 'Q_A_HL.1', 'RGS_A_HL.1']},
    {'name': 'GATE_AH_LO', 'members': ['U_GATE_AH.5', 'RG_A_LL.1']},
    {'name': 'GATE_AH_LO_MOS', 'members': ['RG_A_LL.2', 'Q_A_LL.1', 'RGS_A_LL.1']},
    # Phase A low-side half-bridge: drives right leg
    {'name': 'GATE_AL_HO', 'members': ['U_GATE_AL.7', 'RG_A_HR.1']},
    {'name': 'GATE_AL_HO_MOS', 'members': ['RG_A_HR.2', 'Q_A_HR.1', 'RGS_A_HR.1']},
    {'name': 'GATE_AL_LO', 'members': ['U_GATE_AL.5', 'RG_A_LR.1']},
    {'name': 'GATE_AL_LO_MOS', 'members': ['RG_A_LR.2', 'Q_A_LR.1', 'RGS_A_LR.1']},
    # Phase B high-side half-bridge
    {'name': 'GATE_BH_HO', 'members': ['U_GATE_BH.7', 'RG_B_HL.1']},
    {'name': 'GATE_BH_HO_MOS', 'members': ['RG_B_HL.2', 'Q_B_HL.1', 'RGS_B_HL.1']},
    {'name': 'GATE_BH_LO', 'members': ['U_GATE_BH.5', 'RG_B_LL.1']},
    {'name': 'GATE_BH_LO_MOS', 'members': ['RG_B_LL.2', 'Q_B_LL.1', 'RGS_B_LL.1']},
    # Phase B low-side half-bridge
    {'name': 'GATE_BL_HO', 'members': ['U_GATE_BL.7', 'RG_B_HR.1']},
    {'name': 'GATE_BL_HO_MOS', 'members': ['RG_B_HR.2', 'Q_B_HR.1', 'RGS_B_HR.1']},
    {'name': 'GATE_BL_LO', 'members': ['U_GATE_BL.5', 'RG_B_LR.1']},
    {'name': 'GATE_BL_LO_MOS', 'members': ['RG_B_LR.2', 'Q_B_LR.1', 'RGS_B_LR.1']},
    # Bootstrap: VB(pin8)-VS(pin6) cap per half-bridge
    {'name': 'BOOT_AH_CAP', 'members': ['C_BOOT_AH.1', 'U_GATE_AH.8']},
    {'name': 'BOOT_AH_VS', 'members': ['C_BOOT_AH.2', 'U_GATE_AH.6']},
    {'name': 'BOOT_AL_CAP', 'members': ['C_BOOT_AL.1', 'U_GATE_AL.8']},
    {'name': 'BOOT_AL_VS', 'members': ['C_BOOT_AL.2', 'U_GATE_AL.6']},
    {'name': 'BOOT_BH_CAP', 'members': ['C_BOOT_BH.1', 'U_GATE_BH.8']},
    {'name': 'BOOT_BH_VS', 'members': ['C_BOOT_BH.2', 'U_GATE_BH.6']},
    {'name': 'BOOT_BL_CAP', 'members': ['C_BOOT_BL.1', 'U_GATE_BL.8']},
    {'name': 'BOOT_BL_VS', 'members': ['C_BOOT_BL.2', 'U_GATE_BL.6']},
]
model['nets'].extend(new_nets)

# Step 6: Update PWM nets - each half-bridge HIN(pin2)/LIN(pin3)
# Both half-bridges in a phase share PWM signals (V0.1 simplification)
for net in model['nets']:
    if net['name'] == 'PWM_AH':
        net['members'] = ['U_MCU.20', 'U_GATE_AH.2', 'U_GATE_AL.2']
    elif net['name'] == 'PWM_AL':
        net['members'] = ['U_MCU.21', 'U_GATE_AH.3', 'U_GATE_AL.3']
    elif net['name'] == 'PWM_BH':
        net['members'] = ['U_MCU.22', 'U_GATE_BH.2', 'U_GATE_BL.2']
    elif net['name'] == 'PWM_BL':
        net['members'] = ['U_MCU.23', 'U_GATE_BH.3', 'U_GATE_BL.3']

# Step 7: Power + GND for all 4 gate drivers
for net in model['nets']:
    if net['name'] == '+5V':
        net['members'].extend(['U_GATE_AH.1', 'U_GATE_AL.1', 'U_GATE_BH.1', 'U_GATE_BL.1'])
    elif net['name'] == 'GND':
        net['members'].extend(['U_GATE_AH.4', 'U_GATE_AL.4', 'U_GATE_BH.4', 'U_GATE_BL.4'])

# Step 8: OC_FAULT - IRS2104 has no fault pin; goes to MCU BKIN only
for net in model['nets']:
    if net['name'] == 'OC_FAULT':
        net['members'] = ['U_OC.7', 'U_MCU.24']

# Step 9: Update phase output nets with VS pins
phase_map = {
    'PHASE_A_PLUS': ['Q_A_HL.3', 'Q_A_LL.2', 'J_MOTOR.1', 'U_GATE_AH.6', 'C_BOOT_AH.2'],
    'PHASE_A_MINUS': ['Q_A_HR.3', 'Q_A_LR.2', 'J_MOTOR.2', 'U_GATE_AL.6', 'C_BOOT_AL.2'],
    'PHASE_B_PLUS': ['Q_B_HL.3', 'Q_B_LL.2', 'J_MOTOR.3', 'U_GATE_BH.6', 'C_BOOT_BH.2'],
    'PHASE_B_MINUS': ['Q_B_HR.3', 'Q_B_LR.2', 'J_MOTOR.4', 'U_GATE_BL.6', 'C_BOOT_BL.2'],
}
for net in model['nets']:
    if net['name'] in phase_map:
        net['members'] = phase_map[net['name']]

# Step 10: Deduplicate GND and +5V members
for net in model['nets']:
    if net['name'] in ('GND', '+5V'):
        net['members'] = list(dict.fromkeys(net['members']))

# Step 11: Add design decision
model.setdefault('design_decisions', []).append({
    'title': 'Use 4x IRS2104STR SOIC-8 half-bridge gate drivers',
    'rationale': 'Each IRS2104STR drives one half-bridge (2 MOSFETs). Two half-bridges per phase form a full H-bridge. Matches hardware spec option A.',
    'impact': 'Updated model from 2x16p full-bridge to 4x8p half-bridge drivers with individual bootstrap caps and PWM routing.',
})

# Save
model_path.write_text(json.dumps(model, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

# Stats
comps = model['components']
nets = model['nets']
locked = sum(1 for c in comps if c.get('availability_status') == 'locked')
print(f'Updated: {len(comps)} components ({locked} locked), {len(nets)} nets')
print('Gate driver architecture: 4x SOIC-8 half-bridge (IRS2104STR)')
print(f'Design decisions: {len(model.get("design_decisions", []))}')
