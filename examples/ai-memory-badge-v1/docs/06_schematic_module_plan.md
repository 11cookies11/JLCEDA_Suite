# 06 Schematic Module Plan

Status: Draft

## Purpose

This document defines the schematic-level modules for the AI Memory Badge V1 bare-chip design. It is the bridge between the product design documents and `source/circuit-model.source.json`.

Rev A should be drawn as independent schematic sheets so each risky subsystem can be reviewed and tested separately.

## Sheet List

| Sheet | Name | Purpose |
| --- | --- | --- |
| 01 | USB and Charging | USB-C input, CC resistors, ESD, charger, battery connector |
| 02 | System Power | 3.3 V regulation, current measurement, rail test points |
| 03 | ESP32-S3 Core | bare SoC, EN/BOOT, straps, decoupling, USB debug |
| 04 | Memory | external Flash and PSRAM |
| 05 | Clock and RF | 40 MHz crystal, RF matching, antenna option |
| 06 | Audio Front End | two I2S MEMS microphones |
| 07 | Storage | microSD socket over SPI |
| 08 | User Interface | mark button, mute switch, LEDs, vibration motor |
| 09 | Security Reserve | optional I2C secure element footprint |
| 10 | Test and Bring-Up | debug headers, test pads, measurement jumpers |

## 01 USB And Charging

### Components

- USB-C receptacle with USB2.0 D+/D-
- CC1 and CC2 sink resistors
- USB VBUS ESD / transient protection
- USB data ESD protection
- single-cell LiPo charger
- charger programming resistor
- charger status outputs
- battery connector
- optional battery NTC input if charger supports it

### Nets

- `USB_5V`
- `USB_D_P`
- `USB_D_N`
- `CC1`
- `CC2`
- `BAT_P`
- `CHG_STAT`
- `PGOOD` or `USB_PRESENT`
- `GND`

### Design Notes

- Route USB D+/D- as a short pair to ESP32-S3.
- Keep charger thermal pad and copper area reasonable for selected charge current.
- Rev A can use a simple charger, but leave schematic notes for future power-path charger.
- Add test points for `USB_5V`, `BAT_P`, charger status and ground.

## 02 System Power

### Components

- 3.3 V regulator
- input/output bulk capacitors
- local high-frequency capacitors
- optional ferrite bead or 0R split for audio/digital rail experiments
- current measurement jumper or 0R link
- battery voltage divider
- optional divider enable MOSFET or GPIO-controlled high side

### Nets

- `BAT_P`
- `SYS_3V3`
- `AUDIO_3V3` or `MIC_3V3`
- `VBAT_SENSE`
- `VBAT_SENSE_EN`
- `GND`

### Design Notes

- Size regulator transient response for Wi-Fi bursts.
- Do not leave LED pull-ups or divider leakage as hidden standby current.
- Add one measurement break on `SYS_3V3` so real current can be measured.
- If using LDO in Rev A, document that Rev B may replace it with buck/buck-boost.

## 03 ESP32-S3 Core

### Components

- ESP32-S3 bare SoC
- local decoupling capacitors for all power pin groups
- EN pull-up / reset network
- BOOT button and boot strap components
- manual reset button
- USB D+/D- connection
- UART0 test pads
- selected boot strap pull-ups/pull-downs

### Nets

- `SYS_3V3`
- `ESP_EN`
- `ESP_BOOT`
- `USB_D_P`
- `USB_D_N`
- `UART0_TX`
- `UART0_RX`
- `I2S_BCLK`
- `I2S_LRCLK`
- `I2S_DIN`
- `SD_SCLK`
- `SD_MOSI`
- `SD_MISO`
- `SD_CS`
- `I2C_SDA`
- `I2C_SCL`
- `LED_RECORD`
- `LED_STATUS`
- `BTN_MARK`
- `SW_MUTE`
- `MOTOR_DRV`
- `VBAT_SENSE`
- `GND`

### Design Notes

- Check all boot strapping pins before assigning UI or storage signals.
- Keep decoupling close to ESP32-S3 power pins.
- Put EN, BOOT, UART0 and USB test access in accessible board areas.
- Keep high-current motor and charger paths away from ESP32-S3 RF and crystal areas.

## 04 Memory

### Components

- external SPI Flash, 8-16 MB
- external PSRAM, 8 MB class preferred
- local decoupling capacitors
- optional 0R series resistors on clock/data lines

### Nets

- `FLASH_CS`
- `FLASH_CLK`
- `FLASH_D0`
- `FLASH_D1`
- `FLASH_D2`
- `FLASH_D3`
- `PSRAM_CS`
- shared memory clock/data nets if selected bus mode requires it
- `SYS_3V3`
- `GND`

### Design Notes

- Final net names depend on selected ESP32-S3 memory interface mode.
- Place Flash/PSRAM close to ESP32-S3.
- Do not route memory lines under RF matching or crystal.
- Confirm selected parts support ESP32-S3 boot requirements.

## 05 Clock And RF

### Components

- 40 MHz crystal
- crystal load capacitors
- optional series resistor if recommended
- RF pi matching network
- PCB antenna or U.FL/IPEX connector
- optional RF test connector or matching selection network

### Nets

- `XTAL_P`
- `XTAL_N`
- `RF_IO`
- `ANT_FEED`
- `GND`

### Design Notes

- Keep crystal loop compact and quiet.
- Keep RF trace short and impedance-controlled.
- Use pi matching footprints even if initial values are DNP/0R.
- Preserve antenna keep-out from copper, battery, metal clip and USB shell.

## 06 Audio Front End

### Components

- two I2S MEMS microphones
- local decoupling near each microphone
- optional ferrite bead or 0R from `SYS_3V3` to `MIC_3V3`
- optional test pads for I2S signals

### Nets

- `MIC_3V3`
- `I2S_BCLK`
- `I2S_LRCLK`
- `I2S_DIN`
- `MIC_LR_SEL_L`
- `MIC_LR_SEL_R`
- `GND`

### Design Notes

- Use left/right select pins so both microphones can share one data line if supported.
- Place microphones on the outward-facing edge.
- Add acoustic keep-out notes directly in the schematic and PCB.
- Let firmware support single-mic fallback.

## 07 Storage

### Components

- microSD socket
- pull-ups required by selected socket/bus mode
- optional ESD protection
- optional series resistors on SPI lines
- optional card detect switch

### Nets

- `SD_SCLK`
- `SD_MOSI`
- `SD_MISO`
- `SD_CS`
- `SD_CD`
- `SYS_3V3`
- `GND`

### Design Notes

- Use SPI mode for Rev A.
- Put the socket where the card can be removed during testing.
- Add firmware-visible card detect if the socket supports it.
- Protect against write failures and card removal in firmware.

## 08 User Interface

### Components

- mark button
- physical mute slide switch
- recording/privacy LED
- optional status LED or RGB LED
- low-side NMOS motor driver
- vibration motor connector or pads
- gate resistor and gate pulldown

### Nets

- `BTN_MARK`
- `SW_MUTE`
- `LED_RECORD`
- `LED_STATUS`
- `MOTOR_DRV`
- `SYS_3V3`
- `BAT_P` if motor is battery-powered
- `GND`

### Design Notes

- Recording indication must be visually unambiguous.
- Mute should be a physical state, not only a firmware toggle.
- Vibration motor should not share a fragile return path with microphones.
- Add DNP footprints for alternate LED/current-limiting values.

## 09 Security Reserve

### Components

- I2C secure element footprint, DNP by default
- I2C pull-ups if not already populated elsewhere
- local decoupling capacitor

### Nets

- `I2C_SDA`
- `I2C_SCL`
- `SYS_3V3`
- `GND`

### Design Notes

- Keep footprint close enough to ESP32-S3 for clean routing.
- Do not block Rev A bring-up on secure element provisioning.
- Firmware storage format should still reserve encryption metadata fields.

## 10 Test And Bring-Up

### Components

- test pads for power rails
- test pads for USB, UART, I2S, SPI and I2C
- current measurement jumpers or 0R links
- optional Tag-Connect or small debug header
- ground probe points

### Nets

- `USB_5V`
- `BAT_P`
- `SYS_3V3`
- `MIC_3V3`
- `GND`
- `UART0_TX`
- `UART0_RX`
- `I2S_BCLK`
- `I2S_LRCLK`
- `I2S_DIN`
- `SD_SCLK`
- `SD_MOSI`
- `SD_MISO`
- `SD_CS`
- `I2C_SDA`
- `I2C_SCL`

### Design Notes

- Rev A must be easy to probe.
- Add at least two ground test pads.
- Place current measurement links where they can be cut or replaced.
- Keep critical bring-up pads accessible after battery and clip are installed.

## Schematic Review Checklist

- ESP32-S3 boot straps checked against selected chip and memory mode.
- Flash and PSRAM compatible with selected ESP32-S3 boot configuration.
- Crystal values match selected crystal load capacitance.
- RF matching network and antenna path are tunable.
- USB-C sink configuration is correct.
- Charger current matches battery size and thermal budget.
- 3.3 V regulator supports Wi-Fi burst current.
- Microphones have clean local decoupling and acoustic keep-out notes.
- microSD has ESD and card detect decisions documented.
- Mute switch behavior is represented as a hardware net.
- Recording LED cannot be confused with decorative status.
- Test pads exist for all bring-up-critical signals.
