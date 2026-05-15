# Hardware Spec: NEMA23 Industrial Stepper Driver V0.1

## Product Intent

Design a single-axis industrial-architecture bipolar stepper motor driver for NEMA23 / domestic 57 two-phase motors. The design must avoid integrated stepper driver chips such as A4988, DRV8825, TB6600, and TMC-series parts. The power architecture is MCU current control, external gate drivers, and two N-MOSFET H-bridges.

## Electrical Requirements

- Input: 18V to 50V DC, nominal 24V
- Phase current: 2A RMS per phase
- Peak current: 3A per phase
- Outputs: A+, A-, B+, B-
- Logic rails: 5V and 3.3V
- PCB: 4 layers, JLCPCB/LCSC preferred

## Control and Debug

- External control: STEP, DIR, EN
- Debug interface: UART header, optional USB-UART
- Programming/debug: SWDIO, SWCLK, NRST, GND, 3V3
- MCU class: STM32G431 / STM32G474 preferred

## Required Functional Blocks

- Power input and protection
- Reverse polarity protection
- Bus bulk capacitance and ceramic decoupling
- 50V-capable buck regulator to 5V
- 3.3V LDO
- STM32G4 MCU
- SWD and UART debug headers
- STEP/DIR/EN inputs with ESD, series resistance, pull defaults, and RC filtering
- Gate drivers
- Dual H-bridge MOSFET power stage
- A/B phase current sense
- Hardware overcurrent comparator and gate-driver disable path
- Bus voltage sense
- Temperature sense near MOSFET region
- Motor output terminal
- Power, status, fault, and optional enable LEDs
- Test points

## Out of Scope for V0.1

- RS485, CAN, EtherCAT
- Encoder closed loop
- Multi-axis control
- Continuous current above the 2A RMS / 3A peak validation target
- Formal industrial EMC certification
- Direct production release

## Acceptance Criteria

- Schematic separates power, control, sensing, protection, and debug blocks.
- Every power device has voltage, current, thermal, and package review notes.
- Phase current sensing uses Kelvin routing assumptions.
- Hardware overcurrent protection can shut down the gate drivers independently of firmware.
- MCU ADC inputs stay within 3.3V under worst-case bus and sense conditions.
- KiCad schematic can be generated and reviewed without relying on EasyEDA/JLCEDA GUI bridge code.
