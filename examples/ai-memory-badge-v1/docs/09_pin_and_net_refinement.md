# 09 Pin And Net Refinement

Status: Rev A first-detail pass

This note tracks the first pass from "circuit skeleton" to concrete ESP32-S3R8 net and pin choices.

## Fixed In This Pass

| Area | Change | Reason |
| --- | --- | --- |
| ESP32 enable | `ESP_EN` now connects to `U1.CHIP_PU` | Matches the imported ESP32-S3 symbol pin name. |
| USB native pins | `USB_D_N` uses `U1.GPIO19`; `USB_D_P` uses `U1.GPIO20` | ESP32-S3 native USB routes use GPIO19/GPIO20. |
| RF input | `RF_IO` now connects to `U1.LNA_IN` | Matches the RF input pin name in the ESP32-S3 symbol. |
| Analog/digital supply | `SYS_3V3` also connects to `U1.VDD3P3` and `U1.VDDA` | Avoids leaving ESP32-S3 supply domains represented in the symbol unpowered. |
| Charger PROG resistor | `R3.2` now connects to `GND` | MCP73831 PROG resistor needs a return path. |
| Regulator input capacitor | `C1.1` now connects to `BAT_P` | `C1` is the AP2112 input bulk capacitor; `C2` remains on `SYS_3V3` output. |
| AP2112 pins | Regulator nets now use `VIN`, `VOUT`, and `EN` | Matches the imported AP2112 symbol and ties EN high for always-on Rev A behavior. |
| USB-C connector | Replaced the simplified `USB-TYPE-C-006` selection with `KH-TYPE-C-16P`, LCSC `C709357` | The previous connector only exposed VBUS/GND/CC pins; the new 16-pin receptacle exposes A/B-side VBUS, GND, CC1/CC2, DP, and DN pins for real USB power and USB2.0 data. |
| USB ESD path | `USBLC6-2SC6` now uses numeric pins: D+ through `U6.1`/`U6.6`, D- through `U6.3`/`U6.4`, `U6.2` to GND, and `U6.5` to USB VBUS | Matches the imported symbol and models the connector-side, ESD-output, and ESP32-side USB nets separately. |
| Flash pins | Flash chip-select and IO2/IO3 use the imported symbol pins | Avoids placeholder `CS/HOLD/WP` names that do not exist in the downloaded W25Q128 symbol. |
| MEMS mic pins | I2S nets now use `SCK`, `WS`, `SD`, and `L/R` | Matches the downloaded MSM261S3526Z0CM symbol. |
| microSD pins | SPI and card-detect nets now use exact socket pin numbers | Avoids ambiguity around `CD/DAT3` and duplicate `SW` pin names. |
| Bring-up observability | Added `CHG_STAT` and `MIC_3V3` test points | Makes charger and microphone rail debugging easier. |
| Bus pull-ups/options | Added I2C pull-ups, USB series 0R options, and extra microSD pull-ups | Improves first-board bring-up without changing the core architecture. |

## Current ESP32-S3 GPIO Assignment

| Function | Net | ESP32-S3 pin | Notes |
| --- | --- | --- | --- |
| Boot strap | `ESP_BOOT` | `GPIO0` | BOOT button pulls low for download mode. |
| Battery ADC | `VBAT_SENSE` | `GPIO1` | Needs divider value and ADC calibration review. |
| Power LED | `LED_POWER` | `GPIO2` | Simple GPIO output. |
| Record LED | `LED_RECORD` | `GPIO4` | Simple GPIO output. |
| I2C SCL | `I2C_SCL` | `GPIO5` | Secure element reserve. |
| Mark button | `BTN_MARK` | `GPIO6` | Keep interrupt-capable in firmware. |
| microSD card detect | `SD_CD` | `GPIO7` | Depends on socket CD polarity. |
| microSD CS | `SD_CS` | `GPIO8` | SPI mode DAT3/CS. |
| microSD MISO | `SD_MISO` | `GPIO9` | SPI input from card. |
| microSD SCLK | `SD_SCLK` | `GPIO10` | SPI clock. |
| microSD MOSI | `SD_MOSI` | `GPIO11` | SPI command/MOSI. |
| I2S BCLK | `I2S_BCLK` | `GPIO12` | Shared by both MEMS microphones. |
| I2S LRCLK | `I2S_LRCLK` | `GPIO13` | Shared word select. |
| I2S DIN | `I2S_DIN` | `GPIO14` | Shared data input from microphone pair. |
| Mute switch | `SW_MUTE` | `GPIO17` | Sample on boot and wake. |
| Motor drive | `MOTOR_DRV` | `GPIO18` | Drives MOSFET gate through resistor. |
| USB D- | `USB_D_N` | `GPIO19` | Native USB. Route as differential pair with D+. |
| USB D+ | `USB_D_P` | `GPIO20` | Native USB. Route as differential pair with D-. |
| I2C SDA | `I2C_SDA` | `GPIO21` | Secure element reserve. |

Reserved or avoided in this pass:

- `GPIO3` is intentionally unused until strap and boot behavior are reviewed.
- `GPIO45` and `GPIO46` are strap-related and intentionally unused.
- Flash pins `SPICS0`, `SPICLK`, `SPIQ`, `SPID`, `SPIHD`, and `SPIWP` remain dedicated to external flash.
- `SPICS1` is kept only for the DNP PSRAM reserve.
- JTAG-labelled pins are left unused for now to keep bring-up/debug options open.

USB protection chain:

```text
J1 A6/B6 DP -> USB_D_P_CONN -> U6.1 -> U6.6 -> USB_D_P_ESD -> R22 -> USB_D_P -> U1.GPIO20
J1 A7/B7 DN -> USB_D_N_CONN -> U6.3 -> U6.4 -> USB_D_N_ESD -> R23 -> USB_D_N -> U1.GPIO19
USB_5V -> U6.5
GND -> U6.2
```

## Still Needs Hardware Review

| Item | Review Needed |
| --- | --- |
| ESP32-S3R8 memory mode | Confirm external flash wiring and whether `VDD_SPI` should be tied to 3.3 V for the selected flash voltage. |
| ESP32-S3 pin closure | `U1` still has 17 unconnected symbol pins, and the source model now marks them explicitly as `no_connect`. Tentative treatment: `GPIO3` reserved, `GPIO33`-`GPIO38` NC unless a new feature needs them, `GPIO45` and `GPIO46` NC, `MTMS`/`MTDI`/`MTDO`/`MTCK` debug reserve, `SPICLK_P`/`SPICLK_N` NC, and `XTAL_32K_P`/`XTAL_32K_N` NC unless a 32 kHz clock is later added. |
| PSRAM DNP reserve | Confirm whether `SPICS1` remains valid/available when using ESP32-S3R8 in-package PSRAM. |
| RF network | Replace placeholder pi-network values after antenna connector and board stack-up are known. |
| Crystal loading | Recalculate C8/C9 after final crystal CL and PCB parasitics. |
| USB-C connector | Verify J1 pin aggregation and shell/EP pad grounding against the exact `KH-TYPE-C-16P` connector drawing before PCB release. |
| microSD socket | Verify `CLK`, `CMD`, `DAT0`, `DAT3`, and `CD` pin names against the exact TF socket symbol. |
| MEMS microphones | Verify `LR` polarity for left/right channel selection. |
| Charger/regulator passives | Confirm MCP73831 PROG value and AP2112 input/output capacitor placement against datasheets and footprint pins. |
| Mute switch | Verify SPDT common/throw pin numbering against the selected slide switch footprint. |

## Build Check

After this pass, the source model should still pass:

```powershell
python hwtool_entry.py agent build-ir --project examples\ai-memory-badge-v1
python hwtool_entry.py agent validate-ir --project examples\ai-memory-badge-v1
python hwtool_entry.py agent export-kicad --project examples\ai-memory-badge-v1
python hwtool_entry.py agent diagnose --project examples\ai-memory-badge-v1
```
