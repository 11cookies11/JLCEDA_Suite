# 05 ESP32-S3 Bare Chip Design

Status: Draft

## Why Bare Chip

The project will use an ESP32-S3 bare SoC as the main controller instead of an ESP32-S3 module.

Reasons:

- closer to final wearable product size
- better control of antenna placement and industrial design
- flexible external Flash/PSRAM selection
- direct control over power layout and current measurement
- earlier validation of production-relevant RF design

Tradeoff:

- higher Rev A bring-up risk
- more schematic and PCB layout responsibility
- RF tuning and certification path becomes our responsibility

## Required Support Circuits

Bare ESP32-S3 design must include:

- 3.3 V power rails and local decoupling
- EN/reset network
- boot strap resistors
- USB or UART download path
- 40 MHz crystal and load capacitors
- external SPI Flash
- external PSRAM if selected
- RF matching network
- PCB antenna, chip antenna, or antenna connector
- ground stitching and antenna keep-out

## Memory Plan

Rev A should use:

- 8-16 MB external SPI Flash
- 8 MB class external PSRAM if package and routing allow

Design rules:

- place Flash/PSRAM close to ESP32-S3
- keep SPI traces short and referenced to ground
- reserve 0R series resistors near ESP32-S3 on memory clock/data lines if recommended by layout guidance
- add local decoupling near Flash/PSRAM supplies
- avoid routing memory bus through noisy power or RF areas

## Clock Plan

Use a 40 MHz crystal circuit following Espressif guidance.

Design rules:

- place crystal close to ESP32-S3
- keep crystal traces short and symmetric
- keep copper and noisy traces away from the crystal area
- select load capacitors based on crystal CL and board parasitics
- expose enough test visibility during bring-up to confirm clock startup indirectly

## RF Plan

Rev A should use one of two RF paths:

1. PCB antenna with pi matching network.
2. U.FL/IPEX antenna connector with pi matching network.

Recommendation:

- Use U.FL/IPEX or a selectable PCB antenna/connector network in Rev A if board space allows.
- This reduces risk while microphone and power behavior are still being validated.

Design rules:

- place ESP32-S3 RF pin, matching network and antenna feed close together
- keep RF trace short and impedance-controlled
- reserve pi-network footprints for tuning
- keep antenna area away from battery, metal clip, USB shell and user hand as much as possible
- provide ground stitching near RF feed while preserving antenna keep-out

## Boot And Debug Plan

Required:

- EN/reset button
- BOOT button
- USB D+/D- routed for native USB
- UART0 TX/RX test pads as fallback
- test pads for 3.3 V, GND and key strap pins

Rev A should support manual bootloader entry even if auto-download is not implemented.

## Power Integrity Plan

Bare chip layout must prioritize:

- short 3.3 V path to ESP32-S3
- bulk capacitance near the chip power entry
- local decoupling near each power pin group
- clean ground return
- Wi-Fi burst current margin
- current measurement option for ESP32-S3/system rail

## Layout Risk Checklist

- RF trace too long or not impedance-controlled.
- Antenna blocked by battery, clip or USB connector.
- Crystal placed too far from chip.
- Flash/PSRAM bus too long or routed over split reference.
- Boot strap pins reused without checking startup behavior.
- Decoupling capacitors placed too far away.
- USB pair routed with stubs or poor reference.
- Microphone acoustic ports placed near RF shield/antenna region or noisy power.

## Fallback Strategy

If bare-chip bring-up blocks the audio product validation, create a temporary Rev A-module variant:

- ESP32-S3 module
- same microphones
- same microSD
- same power/UI interfaces

This fallback is only for system validation. The product direction remains bare chip.
