# 01 System Architecture

Status: Draft

## System Block Diagram

```text
                USB-C
                  |
        +---------+----------+
        |                    |
 USB data / debug      LiPo charger
        |                    |
        |              Battery protection
        |                    |
        |                 LiPo cell
        |                    |
        +----------+---------+
                   |
             3.3 V regulator
                   |
              ESP32-S3 bare SoC
       +-----------+-----------+-----------+
       |           |           |           |
   I2S mic L   I2S mic R   microSD     status LED
       |           |           |           |
  voice input  voice input  storage   record/privacy
       |
  optional mic bias / filtering

 ESP32-S3 also connects to:

 - external SPI flash / PSRAM
 - 40 MHz crystal
 - RF matching network and antenna
 - record / mark button
 - physical mute switch
 - vibration motor driver
 - battery voltage divider
 - boot / reset controls
 - optional secure element footprint
 - optional expansion / debug pads
```

## Main Modules

### Compute And Connectivity

Recommended V1 part family: ESP32-S3 bare SoC.

Responsibilities:

- I2S audio capture from digital MEMS microphones
- VAD pre-processing or simple audio level gating
- local file segmentation
- Wi-Fi upload
- BLE provisioning / companion control
- USB debug / export
- battery and state management

Bare-chip support circuits:

- external flash, and preferably PSRAM
- main crystal and required load capacitors
- RF matching network and antenna or antenna connector
- EN, boot strap and auto-download support
- dense local decoupling for all ESP32-S3 power pins
- reference-design-based PCB stackup and RF layout

### Audio Front End

V1 uses two I2S digital MEMS microphones placed with physical spacing on the top edge or front edge of the board.

Design intent:

- keep microphones away from switching regulator noise
- add acoustic keep-out around mic ports
- expose mic port direction clearly in mechanical design
- route I2S signals short and clean
- allow single-mic fallback in firmware

### Storage

V1 should use microSD for prototype flexibility.

Rationale:

- enough capacity for long testing sessions
- easy offline inspection during bring-up
- avoids early tuning around limited flash capacity

Future versions may replace microSD with eMMC, SPI NAND, or larger managed flash.

### Power

Power architecture:

- USB-C 5 V input
- single-cell LiPo charger
- battery protection
- low-quiescent-current 3.3 V regulator
- switched or firmware-controlled power domains where useful

Power goals:

- maintain stable 3.3 V during Wi-Fi transmit bursts
- keep audio rail quiet enough for MEMS microphone operation
- measure sleep current and recording current on V1

### User Interaction

Minimum V1 controls:

- one record / mark button
- one physical mute switch
- one status LED or RGB LED
- one vibration motor

State examples:

- recording possible
- recording active
- muted
- syncing
- charging
- low battery
- storage fault

### Privacy And Security

V1 must make privacy state visible.

Required:

- physical mute switch wired to GPIO
- firmware must treat mute as a hard recording disable
- visible LED indication when recording is active or possible

Reserved:

- secure element footprint for key storage
- encryption-ready storage abstraction
- unique device identity provisioning flow

## Proposed V1 Board Interfaces

- USB-C connector
- LiPo battery connector
- microSD card socket
- boot and reset buttons
- UART or SWD-style debug pads where applicable
- test pads for 5 V, battery, 3.3 V, GND, I2S, key GPIOs

## Firmware Assumptions

- audio is segmented into short files
- VAD decides whether a segment is retained
- marked segments are protected from automatic deletion
- Wi-Fi upload can be deferred until charging or user request
- USB mass storage or serial export is considered for bring-up

## Major Risks

- Bare ESP32-S3 design increases bring-up risk compared with a module because RF, crystal, flash/PSRAM and power integrity are now board-level responsibilities.
- ESP32-S3 power consumption may challenge all-day battery life if Wi-Fi or audio pipeline is inefficient.
- VAD quality may determine whether the product feels useful or noisy.
- microSD write bursts can affect power and audio timing if not buffered well.
- microphone placement and enclosure acoustics can dominate perceived audio quality.
- privacy expectations require clear physical and software behavior.
