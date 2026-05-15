# NEMA23 Industrial Stepper Driver V0.1

This example captures the first structured design pass for an industrial-architecture single-axis NEMA23/57 bipolar stepper motor driver.

It is intentionally a V0.1 engineering validation board, not a production-ready motor drive. The goal is to make the architecture reviewable in KiCad and to prepare the design for LCSC-backed part locking.

## Targets

- 18V to 50V DC input, nominal 24V
- 2A RMS per phase, 3A peak per phase
- Two external N-MOSFET H-bridges
- STM32G4-class motor-control MCU
- STEP, DIR, EN control inputs
- UART debug and SWD programming
- A/B phase current sensing
- Bus voltage and temperature sensing
- Hardware overcurrent shutdown path
- 4-layer PCB layout assumptions

## Current State (2026-05-15)

### Circuit Model

The expanded circuit model now contains **118 components** and **76 nets**, covering:

- Power input with reverse-polarity protection (PMOS), fuse, TVS, and EMI reserve
- Bus bulk electrolytic + ceramic decoupling capacitance
- 60V-capable buck regulator to 5V (pending correct LCSC selection)
- 3.3V LDO (AMS1117-3.3 locked)
- STM32G431CBT6 MCU with crystal oscillator, NRST, BOOT0, and decoupling
- 4x half-bridge gate drivers (IRS2104STR SOIC-8, locked — model currently uses 2x SOIC-16, needs architectural update)
- 8x N-MOSFET power stage with gate resistors and gate-source pulldowns
- Phase current sensing with shunt resistors, INA180 amplifiers, and ADC RC filters
- Hardware overcurrent comparator (LM393 locked, symbol repaired)
- Bus voltage divider with filter capacitor
- NTC temperature sensing near MOSFET region
- Motor output terminal with reserved TVS and RC snubber positions
- STEP/DIR/EN inputs with series resistors, pull-ups, ESD diodes, and RC filters
- SWD and UART debug headers
- USB-UART bridge (CH340C-class, optional) with USB-C connector
- Power, Status, and Fault LEDs
- Test points for GND, 3V3, 5V, VM_BUS, IA_ADC, IB_ADC
- Reserved braking dump resistor position

### Locked LCSC Parts (5 of 118)

| Role | MPN | LCSC ID | Symbol | Footprint | Risk |
|------|-----|---------|--------|-----------|------|
| MCU | STM32G431CBT6 | C529355 | JLC-MCP-MCUs:STM32G431CBT6 | LQFP-48 | low |
| LDO 3.3V | AMS1117-3.3 | C6186 | JLC-MCP-Power:AMS1117-3_3 | SOT-223 | low |
| Gate Driver | IRS2104STR(UMW) | C20623202 | JLC-MCP-Transistors:IRS2104STR_UMW_ | SOIC-8 | low |
| Current Sense Amp | INA180A1IDBVR(LX) | C48533472 | JLC-MCP-Sensors:INA180A1IDBVR_LX_ | SOT-23-5 | low |
| Comparator | LM393 | C5252905 | JLC-MCP-Misc:LM393_C5252905 | SOP-8 | low |

### Key Gaps

- **Buck regulator**: TPS62153 selected by resolver is 3-17V input only, not suitable for 50V bus. Need to re-search for 60V+ input buck.
- **Power MOSFET**: No candidates found by resolver. Need to refine search query for 80-100V N-MOSFET in TO-252/LFPAK.
- **Current sense resistor**: No candidates found. Need to refine query for 2512 shunt.
- **Motor output terminal**: No candidates found. Need to refine query for 5.08mm 4P terminal.
- **Gate driver architecture mismatch**: IRS2104STR is an SOIC-8 half-bridge driver (2 outputs). The current circuit model uses 2x SOIC-16 full-bridge drivers. Need to update the model to use 4x SOIC-8 half-bridge drivers instead, or find SOIC-16 dual-half-bridge drivers from LCSC.
- **Passive components**: 100+ resistors, capacitors, LEDs, diodes, test points still need LCSC selection. Most are standard values (10k, 100nF, 1k, etc.) and can be batch-selected.
- **KiCad schematic**: Generated successfully with 118 symbols, but many are AIAgent placeholders. Needs symbols updated to JLC-MCP references for locked parts.

## Generated KiCad Skeleton

```powershell
python scripts/build_nema23_model.py
python scripts/run_pipeline.py examples/nema23-industrial-stepper-driver-v0.1/nema23-industrial-stepper-driver-v0.1.circuit-model.json .where/nema23-industrial-stepper-driver-v0.1
```

Generated output:

- `.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1/nema23_industrial_stepper_driver_v0_1.kicad_pro`
- `.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1/nema23_industrial_stepper_driver_v0_1.kicad_sch`
- `.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1/kicad-execution-plan.json`
- `.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1/part.lock.yaml`
- `.where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1/part-risk-report.md`

Pipeline count: 118 symbols and 76 nets (updated from the original 30/38).

### LCSC Selection Commands

```powershell
# Run part selector
python scripts/select_parts.py --json examples/nema23-industrial-stepper-driver-v0.1/part.requirements.resolver.json --output .where/nema23-industrial-stepper-driver-v0.1/selected-parts.json

# Batch install selected parts
python scripts/install_jlc_mcp_parts.py --selections .where/nema23-industrial-stepper-driver-v0.1/selected-parts.json --project-dir .where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1 --include-3d --timeout 300

# Fix known symbol issues
python scripts/fix_lm393_jlc_mcp_symbol.py --project-dir .where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1 --id C5252905

# Re-register library tables after fix
python scripts/install_jlc_mcp_parts.py --project-dir .where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1 --register-only

# Write part lock and risk report
python scripts/write_jlc_mcp_part_lock.py --selections .where/nema23-industrial-stepper-driver-v0.1/selected-parts.json --install-report .where/nema23-industrial-stepper-driver-v0.1/jlc-mcp-install-report.json --project-dir .where/nema23-industrial-stepper-driver-v0.1/nema23_industrial_stepper_driver_v0_1
```

## Important Gaps

- Final LCSC part numbers are only partially locked (5 of 118 components). MOSFET, shunt resistor, terminal block, buck regulator, and all passives still require LCSC selection.
- The gate driver architecture needs updating: the model uses 2x 16-pin full-bridge drivers, but the selected IRS2104STR is an 8-pin half-bridge driver. The model should switch to 4x half-bridge drivers per the hardware spec's "方案 A".
- JLC MCP installed symbols/footprints must be inspected before schematic acceptance. The LM393 install initially reported `pin_count=0` and was repaired with the standard 8-pin comparator pinout.
- Gate driver, MOSFET, current sense amplifier, comparator, and terminals require datasheet-level selection.
- KiCad output from this model is a schematic skeleton for review, not a finished production schematic.
- PCB thermal, creepage, and high-current copper checks must be completed before fabrication.
