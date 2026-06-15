# 08 LCSC Workflow Queue

Status: Completed Rev A candidate selection

This file summarizes the `lcsc_selection_v1` part-selection workflow and the Rev A candidate selections now written to `source/circuit-model.source.json`.

## Current Queue

- active workflow: none
- `lcsc_selection_v1` status: completed
- pending LCSC tasks: 0
- explicitly LCSC-exempt components: 16
- source-level selected LCSC parts synced: 56
- selected CAD-library candidates, including DNP reserves: 60 resolved/downloaded
- KiCad export: succeeds for Rev A prototype project output

All Rev A BOM or assembly-relevant parts now have either a selected LCSC candidate or an explicit non-LCSC/DNP/internal classification.

## ICs / Active Devices

All pure IC / active-device LCSC selections are complete. Remaining active or mixed-domain parts are listed under audio, UI, haptics, and connectors.

## Resolved / Exempt Since Last Queue Snapshot

| Ref | Decision | Notes |
| --- | --- | --- |
| U1 | ESP32-S3R8, LCSC C2913194 | Rev A controller. In-package 8 MB PSRAM, external flash still required. |
| U2 | AP2112K-3.3TRG1, LCSC C51118 | Rev A 3.3 V LDO. |
| U3 | MCP73831T-2ACI/OT, LCSC C424093 | Rev A single-cell LiPo charger. |
| U4 | W25Q128JVSIQ, LCSC C97521 | 16 MB external SPI flash for ESP32-S3R8. |
| U5 | DNP reserve | External PSRAM footprint kept as fallback, not assembled by default. |
| U6 | USBLC6-2SC6, LCSC C7519 | USB 2.0 ESD protection. |
| D2 | KT-0603R, LCSC C2286 | Red recording/privacy LED. |
| R1/R2 | 0603WAF5101T5E, LCSC C23186 | USB-C 5.1K Rd resistors. |
| R3 | 0603WAF2001T5E, LCSC C22975 | Charger PROG resistor; value still tied to charge-current review. |
| R8 | 0603WAF1004T5E, LCSC C22935 | VBAT divider upper resistor. |
| R9 | 0603WAF3303T5E, LCSC C23137 | VBAT divider lower resistor. |
| R10 | 0402WGF0000TCE, LCSC C17168 | RF series tuning jumper. |
| R11/R12/R13 | 0603WAF0000T5E, LCSC C21189 | 0R jumpers. |
| R17 | 0603WAF1000T5E, LCSC C22775 | Motor gate resistor. |
| R18 | 0603WAF1003T5E, LCSC C25803 | Motor gate pulldown. |

## Connectors

| Ref | Decision | Notes |
| --- | --- | --- | --- | --- |
| J2 | S2B-PH-SM4-TB(LF)(SN), LCSC C295747 | JST PH 2.0 mm right-angle SMD battery connector; confirm polarity and cable direction. |
| J3 | U.FL-R-SMT-1(80), LCSC C88374 | U.FL/IPEX RF connector; confirm footprint and keepout. |
| J5 | TF-001B, LCSC C125617 | microSD socket candidate; verify card-detect pin orientation. |

## Clock / RF

| Ref | Decision | Notes |
| --- | --- | --- | --- | --- |
| Y1 | 3225 40M 12PF 10PPM, LCSC C5380316 | 40 MHz crystal candidate for ESP32-S3R8. |

## Crystal Load Capacitors

| Ref | Decision | Notes |
| --- | --- | --- | --- | --- |
| C8 | CL10C180JB8NNNC 18pF, LCSC C1647 | Initial load cap for 12 pF crystal, assuming about 2-3 pF stray capacitance. |
| C9 | CL10C180JB8NNNC 18pF, LCSC C1647 | Same as C8; tune after PCB bring-up if needed. |

## Audio / UI / Haptics

| Ref | Decision | Notes |
| --- | --- | --- | --- | --- |
| MK1 | MSM261S3526Z0CM, LCSC C966933 | I2S bottom-port MEMS microphone; verify acoustic port and L/R select strapping. |
| MK2 | MSM261S3526Z0CM, LCSC C966933 | Same as MK1. |
| SW4 | MSK12C02-HB, LCSC C431541 | Right-angle SPDT slide switch; match actuator direction to enclosure label. |
| Q1 | AO3400A, LCSC C20917 | Logic-level NMOS low-side switch for motor. |
| M1 | LCM0827A3038F, LCSC C2759981 | 3 V flat vibration motor candidate; confirm attachment and pad geometry. |

## Rule

Do not mark a future item as non-LCSC unless the design explicitly changes. Descriptive fields such as `value: "DNP"` or a role name are not enough to skip LCSC selection.

`TP1` through `TP12` are the current internal exception: they are `part_source: "internal"` and `bom_exclude: true`, and use a local `TP_1P` symbol plus `TP-SMD_1P` footprint.

The connector, microphone, switch, RF, and motor candidates above still need footprint/mechanical review before PCB layout release.
