# Rev A Module Preliminary BOM

## Must Place

| Ref | Function | Selected Part / Status |
| --- | --- | --- |
| U1 | ESP32-S3 controller module | ESP32-S3-WROOM-1-N8R8, C2913201 |
| U3 | Li-ion charger with power path | BQ24074RGTR, C54313 |
| U2 | Rev A 3.3 V bring-up LDO | AP2112K-3.3TRG1, C51118 |
| J1 | USB-C USB2.0 power/data | KH-TYPE-C-16P, C709357 |
| U6 | USB ESD protection | USBLC6-2SC6, C7519 |
| J2 | Battery connector | JST PH 2P SMD, C295747 |
| MK1/MK2 | I2S MEMS microphones | MSM261S3526Z0CM, C966933 |
| J5 | microSD socket | TF-001B, C125617 |
| U9 | MIC_3V3 load switch | TPS22918DBVR, C131941 |
| U10 | SD_3V3 load switch | TPS22918DBVR, C131941 |
| SW3/SW5/SW6 | MARK / REC / MODE buttons | Side/tact switch candidates selected in source model |
| SW4 | Physical mute slide switch | MSK12C02-HB, C431541 |
| D2 | Recording/privacy LED | KT-0603R red LED, C2286 |
| Q1/M1 | Haptic motor driver and motor | AO3400A + LCM0827A3038F |
| R/C passives | Pullups, links, decoupling | Selected 0603/0402 JLC parts in source model |

## DNP

| Ref | Function | Reason |
| --- | --- | --- |
| C20/C21 | NFC antenna tuning capacitors | Tune after antenna/enclosure measurement |
| U7 | Secure element reserve | Optional security expansion |
| C19 | Motor suppression capacitor | Tune/DNP depending on motor noise |

## Optional / TBD Footprint

| Ref | Function | Status |
| --- | --- | --- |
| J6 | 2.13 inch e-paper connector | Exact FPC or adapter-board connector TBD |
| J7 | NFC antenna pads/connector | PCB coil or external coil connection TBD |
| TPx | Test points | Excluded from assembled BOM but required for Rev A bring-up access |

## Removed From BOM

| Ref | Removed Item |
| --- | --- |
| U4 | External SPI flash |
| U5 | External PSRAM |
| Y1 | 40 MHz crystal |
| C8/C9 | Crystal load capacitors |
| J3 | U.FL antenna connector |
| R10/C12/C13 | Bare-chip RF pi network |
