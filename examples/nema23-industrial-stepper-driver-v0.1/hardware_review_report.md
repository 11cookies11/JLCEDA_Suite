# Hardware Review Report: NEMA23 Industrial Stepper Driver V0.1

Generated: 2026-05-15

## Overall Status: IN PROGRESS (V0.1 Skeleton)

The expanded circuit model contains **118 components and 76 nets**, covering all functional blocks from the hardware spec. **10 semiconductor/connector parts are locked** with real LCSC IDs and JLC MCP KiCad symbols. Standard passives are mapped to LCSC commodity part numbers.

## Locked Parts Summary

### Semiconductors & Critical Components (10 locked)

| Ref | Role | MPN | LCSC ID | Package | Validation |
|-----|------|-----|---------|---------|------------|
| U_MCU | Motor-control MCU | STM32G431CBT6 | C529355 | LQFP-48 | 48p/48p |
| U_BUCK | 5V Buck Regulator | XL7015E1 | C73013 | TO-252-5 | installed |
| U_LDO | 3.3V LDO | AMS1117-3.3 | C6186 | SOT-223 | 4p/4p |
| U_GATE_x4 | Half-Bridge Gate Driver | IRS2104STR(UMW) | C20623202 | SOP-8 | 8p/8p |
| Q_x8 | Power N-MOSFET | IRFR3710ZTRPBF | C52839 | TO-252 | installed |
| RSH_x2 | Current Sense Shunt | RLP25FEER050 | C160588 | 2512 | installed |
| U_AMP_x2 | Current Sense Amp | INA180A1IDBVR(LX) | C48533472 | SOT-23-5 | 5p/5p |
| U_OC | Overcurrent Comparator | LM393 | C5252905 | SOP-8 | 8p/8p (repaired) |
| J_MOTOR | Motor Output Terminal | DB2EVC-5.08-4P-GN | C395750 | 5.08mm 4P | installed |
| J1 | Power Input Terminal | KF2EDGR-5.0-2P | C441193 | 5mm 2P | installed |

### Standard Passives (LCSC commodity parts mapped)

| Value | Package | LCSC ID | MPN | Use |
|-------|---------|---------|-----|-----|
| 10k | 0603 | C25804 | 0603WAF1002T5E | Pull-up/down, divider |
| 100R | 0603 | C22775 | 0603WAF1000T5E | Series protection |
| 470R | 0603 | C23036 | 0603WAF4700T5E | LED current limit |
| 1k | 0603 | C21190 | 0603WAF1001T5E | LED current limit |
| 10R | 0603 | C22758 | 0603WAF100JT5E | Gate resistor |
| 100k | 0603 | C25803 | 0603WAF1003T5E | Gate-source pulldown |
| 2.2k | 0603 | C22778 | 0603WAF2201T5E | OC threshold divider |
| 200k | 0603 | C25900 | 0603WAF2003T5E | Bus divider top |
| 12k | 0603 | C25807 | 0603WAF1202T5E | Bus divider bottom |
| 100nF 50V | 0603 | C14663 | CC0603KRX7R9BB104 | Decoupling |
| 10nF 50V | 0603 | C1580 | CC0603KRX7R9BB103 | ADC filter |
| 1nF 50V | 0603 | C1583 | CC0603KRX7R9BB102 | ADC filter |
| 1uF 50V | 0805 | C15850 | CC0805KRX7R9BB105 | Bootstrap, filter |
| 10uF 25V | 0805 | C1710 | CL21A106KAYNNNE | Bulk decoupling |
| 22uF 10V | 1210 | C15866 | CL32A226KOJNNNE | Buck output |
| 4.7uF 10V | 0805 | C1592 | CL21A475KOFNNNE | MCU bulk decoupling |
| 12pF 50V | 0603 | C1632 | CC0603FRNPO9BN120 | Crystal load |
| Green LED | 0603 | C72043 | 19-217/GHC-YR1S2/3T | Power indicator |
| Blue LED | 0603 | C72041 | 19-217/BHC-ZL1M2RY/3T | Status indicator |
| Red LED | 0603 | C72038 | 19-217/R6C-AL1M2VY/3T | Fault indicator |
| 100nF 100V | 0805 | C49678 | CC0805KRX7R9BB104 | Bus decoupling |
| 470uF 80V | Radial | C59373 | EEETP1K471V | Bus bulk |

## Design Rule Checks

### Architecture

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Input voltage range 18-50V | PASS | XL7015E1 rated 5-80V |
| 2 | Buck output 5V/500mA+ | PASS | XL7015E1 rated 800mA |
| 3 | LDO 3.3V/300mA+ | PASS | AMS1117-3.3 rated 1A |
| 4 | MOSFET Vds >= 80V | PASS | IRFR3710Z rated 100V |
| 5 | MOSFET Rds(on) | PASS | 18mOhm at 10Vgs |
| 6 | Gate driver matches MOSFET | REVIEW | IRS2104STR: 300/600mA gate drive; IRFR3710Z Qg=100nC |
| 7 | Shunt power rating | PASS | 50mOhm 2W, I2R=0.45W at 3A peak |
| 8 | ADC input range safe | PASS | Bus divider 200k/12k -> 2.83V at 50V bus |
| 9 | Hardware overcurrent path | PASS | LM393 -> gate driver disable + MCU BKIN |
| 10 | STEP/DIR/EN protection | PASS | 100R series + ESD + RC filter + pull-up |
| 11 | SWD/UART debug access | PASS | Standard headers |
| 12 | Motor terminal current | PASS | DB2EVC rated 15A |
| 13 | PCB layers | PLANNED | 4-layer specified |
| 14 | Power loop short | PENDING | PCB not started |
| 15 | Kelvin sense routing | PENDING | PCB not started |
| 16 | Gate trace short | PENDING | PCB not started |
| 17 | Analog isolation | PENDING | PCB not started |

### Known Gaps

| # | Issue | Severity | Action |
|---|-------|----------|--------|
| 1 | Gate driver model: 2x16p vs 4x8p | Medium | Model needs update to 4x IRS2104STR SOIC-8 half-bridge |
| 2 | XL7015E1 150kHz switching | Low | Larger inductor needed; acceptable for V0.1 |
| 3 | AIAgent placeholder symbols | Medium | Substitute with JLC-MCP symbols |
| 4 | ERC fails on placeholder symbols | Medium | Will pass after symbol substitution |
| 5 | Bootstrap cap value not verified | Medium | 1uF placeholder; calculate from Qg and f_sw |
| 6 | USB-UART not locked | Low | CH340C selection pending |
| 7 | Reverse protection PMOS not locked | Low | IRFR9024NTRPBF (C83536) identified |
| 8 | Braking dump not implemented | Low | V0.1 scope exclusion |

## Compliance with Hardware Spec

| Requirement | Status |
|-------------|--------|
| No integrated stepper driver chips | PASS |
| External gate drivers + MOSFET H-bridges | PASS |
| STM32G4 MCU | PASS (STM32G431CBT6) |
| UART + SWD debug | PASS |
| STEP/DIR/EN inputs | PASS |
| Hardware overcurrent protection | PASS |
| Bus voltage + temperature sense | PASS |
| 4-layer PCB | PLANNED |
| No RS485/CAN/EtherCAT | PASS |
| No encoder closed-loop | PASS |

## Next Steps

1. Fix gate driver architecture: update model from 2x16p to 4x8p half-bridge drivers
2. Substitute AIAgent placeholder symbols with JLC-MCP library symbols in schematic
3. Re-run ERC after symbol substitution
4. Install remaining JLC MCP parts (reverse protection PMOS, USB-UART, crystal)
5. Generate BOM from circuit model + lcsc-parts-map.json
6. Start PCB layout with 4-layer stackup
7. Datasheet review of gate driver + MOSFET pairing (Qg vs drive current)
8. Bootstrap capacitor sizing calculation
