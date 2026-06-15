# 10 Flow Based Schematic Review

Status: Rev A review notes

This review looks at the current schematic model through power flow, data flow, control flow, privacy flow, and bring-up flow. The current design is a good exportable skeleton, but several details should be completed before treating it as a board-release schematic.

## Power Flow

Current path:

```text
USB-C VBUS -> MCP73831 charger -> BAT_P -> AP2112 3.3 V LDO -> SYS_3V3 loads
```

What is good:

- USB-C sink CC resistors are modeled.
- Charger, LiPo connector, regulator, and 3.3 V load rail are present.
- Input/output bulk capacitors and test points are present.
- ESP32-S3, flash, microSD, microphones, LEDs, motor, and secure-element reserve all have a 3.3 V path.

Needs improvement before PCB release:

| Priority | Item | Why It Matters | Suggested Next Change |
| --- | --- | --- | --- |
| High | Close the remaining ESP32-S3 pin audit | The current U1 symbol still leaves 17 pins intentionally unconnected, and each one needs an explicit NC or reserved-pin decision. | Document the final treatment for `GPIO3`, `GPIO33`-`GPIO38`, `GPIO45`, `GPIO46`, `MTMS`, `MTDI`, `MTDO`, `MTCK`, `SPICLK_P`, `SPICLK_N`, `XTAL_32K_P`, and `XTAL_32K_N`. |
| High | Add real battery protection/power-path decision | The current charger-to-battery-to-LDO path is simple, but it does not explicitly handle load sharing while USB is plugged in. | Decide whether Rev A uses protected cell only, a protection IC, or a charger with power-path/load sharing. |
| High | Add charger status signal or LED | Firmware/UI currently cannot know charging/full/fault state. | Add `CHG_STAT` from MCP73831 STAT to either an LED/resistor or ESP32 GPIO, preferably with a test point. |
| High | Review MCP73831 charge current | `R3 = 2K` implies a high prototype charge current class. | Set charge current against the actual LiPo capacity and thermal budget. |
| Medium | Add AP2112 enable handling | AP2112 has an enable pin in many packages; the model does not expose regulator enable/shipping mode. | Tie EN correctly or add a system enable/shutdown strategy. |
| Medium | Add ferrite/0R isolation options | Always-on audio memory device benefits from noise isolation between ESP32/RF, microphones, and storage. | Add optional ferrite/0R links for `MIC_3V3` and maybe SD/analog-sensitive sub-rails. |
| Medium | Add more local decoupling intent | ESP32-S3 has several power domains; current model has bulk + three 100 nF caps only. | Add per-domain decoupling notes/components near `VDD3P3`, `VDD3P3_CPU`, `VDD3P3_RTC`, `VDDA`, and `VDD_SPI`. |
| Medium | Add motor flyback/transient strategy | Coin/ERM motors can inject noise into SYS_3V3. | Review whether `C19` is enough; consider diode/TVS/ferrite depending on motor type and measured noise. |

## Data Flow

Current data paths:

```text
MEMS mic pair -> I2S -> ESP32-S3 -> microSD
ESP32-S3 -> USB native D+/D- -> USB-C
ESP32-S3 -> external SPI flash
ESP32-S3 -> Wi-Fi RF -> U.FL antenna path
```

What is good:

- I2S BCLK/LRCLK/DIN are assigned to concrete ESP32-S3 GPIOs.
- microSD uses SPI-mode nets with test points.
- USB-C now uses a data-capable 16-pin receptacle, with A/B-side VBUS, GND, CC, DP, and DN pins connected into the USB power/data path.
- USB native D+/D- now use GPIO19/GPIO20 through the `USBLC6-2SC6` ESD pass-through pins and optional series links.
- External flash uses the ESP32-S3 SPI flash pins.
- RF path now starts at `LNA_IN`.

Needs improvement before PCB release:

| Priority | Item | Why It Matters | Suggested Next Change |
| --- | --- | --- | --- |
| High | Verify microSD socket pin names against the exact footprint | Socket libraries often use physical pin names differently from SPI signal names. | Confirm `CLK`, `CMD`, `DAT0`, `DAT3`, `CD`, `VDD`, `VSS`; add pull-ups for DAT/CMD as needed for the chosen mode. |
| High | Add USB D+/D- series resistors if Espressif reference requires them for this layout | Native USB signal integrity and ESD placement matter. | Check ESP32-S3 reference schematic; add optional 0R/22R series resistor footprints near the SoC if recommended. |
| High | Confirm flash memory voltage and `VDD_SPI` configuration | Wrong flash voltage can prevent boot. | Verify W25Q128JVSIQ voltage, ESP32-S3R8 boot strapping, and `VDD_SPI` tie. |
| Medium | Add I2S microphone static L/R strapping review | Current `R12/R13` select opposite channels, but polarity is not verified. | Confirm selected MSM261 microphone L/R truth table and update notes/net names if needed. |
| Medium | Add secure-element I2C pull-ups | `U7` has SDA/SCL but the I2C bus has no explicit pull-up resistors. | Add DNP or populated pull-ups on `I2C_SDA` and `I2C_SCL`, likely 4.7K-10K depending on bus speed and sleep current. |
| Medium | Decide whether JTAG pads are needed | Current UART is exposed, but JTAG-labelled pins are intentionally unused. | Add compact SWD/JTAG-style pads if deep ESP32 bring-up/debug is expected. |

## Control And Function Flow

Current flow:

```text
Reset/BOOT -> ESP32 boot
Mark button -> ESP32 GPIO
Mute switch -> ESP32 GPIO
ESP32 -> LEDs + vibration motor
Battery divider -> ESP32 ADC
```

What is good:

- Reset and boot controls are present.
- Mark and mute controls are present.
- Power/recording LEDs and a haptic motor are present.
- Battery voltage sense divider is present.

Needs improvement before PCB release:

| Priority | Item | Why It Matters | Suggested Next Change |
| --- | --- | --- | --- |
| High | Add hardware microphone power gating for stronger privacy | Current mute is firmware-enforced only. A privacy wearable should be visibly and electrically defensible. | Use the mute switch or a load switch/MOSFET to cut `MIC_3V3`, while still reporting mute state to ESP32. |
| High | Add pull/debounce intent for buttons and mute | Current switches rely on simple pull-ups but do not document debounce/filtering. | Add small RC/filter notes or firmware debounce contract; verify switch common/throw pin numbering. |
| Medium | Add battery divider enable | `1M/330K` always bleeds battery, small but constant. | Add GPIO-controlled divider high-side/low-side switch or raise values after ADC impedance review. |
| Medium | Add recording LED hard policy | Firmware could accidentally repurpose the LED. | Keep `LED_RECORD` as a dedicated privacy indicator in firmware contract and test plan. |
| Low | Add charger status to UI state machine | Charging/full/fault is part of wearable user experience. | Connect MCP73831 STAT to LED or ESP32 GPIO. |

## RF And Clock Flow

Current flow:

```text
40 MHz crystal -> ESP32-S3 XTAL pins
ESP32-S3 LNA_IN -> RF matching placeholders -> U.FL connector
```

Needs improvement before PCB release:

| Priority | Item | Why It Matters | Suggested Next Change |
| --- | --- | --- | --- |
| High | Replace placeholder RF matching with reference topology | RF path is not a generic digital net. | Follow Espressif RF reference and keep C12/C13/R10 as a real pi-network with DNP/default values. |
| High | Confirm crystal load values | Current 18 pF caps are a first estimate. | Recalculate from crystal CL and PCB stray capacitance; keep C0G/NP0. |
| Medium | Add RF keepout and 50 ohm layout notes to PCB constraints | U.FL routing depends on stack-up. | Add controlled impedance and antenna keepout constraints before layout. |

## Bring-Up And Test Flow

What is good:

- Test points exist for rails, I2S, microSD SPI, and mute.
- UART header exists.
- BOOT and RESET buttons exist.

Needs improvement:

| Priority | Item | Why It Matters | Suggested Next Change |
| --- | --- | --- | --- |
| Medium | Add USB D+/D- test access or at least accessible probing guidance | USB enumeration is a critical bring-up step. | Add compact test pads or layout probe points if space allows. |
| Medium | Add charger/regulator test points | Charging and brownout are likely first bring-up issues. | Add `CHG_STAT`, regulator EN if used, and maybe `MIC_3V3` test point. |
| Medium | Add current measurement jumpers | Battery-life validation is a primary requirement. | Add 0R/current-shunt options for main SYS_3V3 and microphone rail. |

## Recommended Next Edits

Implemented in the first refinement pass:

1. Added `CHG_STAT` net from MCP73831 to a 10K pull-up and test point.
2. Added I2C pull-ups for the secure-element reserve.
3. Added USB D+/D- optional 0R series footprints and split the USB path into connector-side, ESD-output, and ESP32-side nets.
4. Added extra microSD CMD/DAT0 pull-ups.
5. Corrected AP2112, flash, microSD, and MEMS microphone pin references against the imported symbols.
6. Added `MIC_3V3` test point.
7. Replaced the simplified USB-C connector with `KH-TYPE-C-16P`, LCSC `C709357`, so J1 now exposes real USB2.0 DP/DN pins as well as VBUS, GND, and CC pins.
8. Added a `SYS_3V3_REG` to `SYS_3V3` current-measurement link through `R26` so regulator output current can be measured separately from the system load rail.

Remaining next edits:

1. Add microphone power gate or at least a DNP load-switch footprint on `MIC_3V3`.
2. Add ESP32-S3 decoupling detail by power domain.
3. Decide whether the DNP external PSRAM footprint should remain when using ESP32-S3R8.
4. Review USB ESD placement order, DP/DN polarity, and USB series resistor default against the PCB layout and the selected `USBLC6-2SC6` datasheet.
5. Verify microSD socket mechanical pinout and card-detect switch polarity against the connector drawing.

## Release Gate

Before ordering PCB, require:

- `validate-ir` has 0 errors and 0 warnings.
- `diagnose` has 0 `must_fix`.
- Every imported symbol footprint is checked against the selected part datasheet.
- ESP32-S3 reference schematic checklist is manually compared against the source model.
- USB-C, battery connector, microSD socket, microphone acoustic port, and U.FL connector footprints are reviewed against mechanical drawings.
