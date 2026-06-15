# 03 Hardware Design Plan

Status: Draft

## Design Target

V1 是一块可调试原型板，目标是验证“全天候佩戴 + 人声触发录音 + 本地缓存 + USB-C/Wi-Fi 同步”这一条主链路。

优先级：

1. 能稳定上电、录音、存储、同步。
2. 能测量真实佩戴功耗。
3. 能评估麦克风位置和外壳声学影响。
4. 为后续小型化和加密版本保留接口。

## Recommended Architecture

```text
USB-C connector
  |-- USB D+/D- ---------------------+
  |                                  |
  |-- 5 V input -> charger -> LiPo --+--> 3.3 V regulator --> ESP32-S3 bare SoC
                                                     |
                                                     +--> external flash / PSRAM
                                                     +--> 40 MHz crystal
                                                     +--> RF match + antenna
                                                     +--> I2S MEMS mic L
                                                     +--> I2S MEMS mic R
                                                     +--> microSD socket
                                                     +--> RGB/status LED
                                                     +--> mark button
                                                     +--> mute switch
                                                     +--> vibration motor driver
                                                     +--> battery sense divider
                                                     +--> optional secure element footprint
                                                     +--> debug/test pads
```

## Module Plan

### 1. Main Controller

Use an ESP32-S3 bare SoC for V1.

Recommended chip class:

- ESP32-S3 bare chip variant with enough GPIO for USB, I2S, SPI storage, UI and debug.
- Pair with external flash and preferably external PSRAM.
- Keep ESP32-S3 module design as a fallback reference path if RF/memory bring-up blocks system validation.

Responsibilities:

- capture two digital microphone channels
- run lightweight VAD or audio-level gate
- segment audio into short files
- write retained audio to microSD
- upload over Wi-Fi
- expose USB serial/debug/export path
- manage LED, buttons, mute switch and vibration motor
- monitor battery voltage

Required bare-chip support:

- 40 MHz crystal circuit
- external flash and PSRAM
- RF matching network
- PCB antenna or U.FL/IPEX antenna connector
- EN reset network
- boot strap resistors
- USB/UART download path
- local decoupling for every relevant power domain
- RF and crystal layout following Espressif guidance

### 2. Audio Capture

Use two digital I2S MEMS microphones.

Recommended topology:

- shared I2S bit clock
- shared I2S word select
- shared data line if the microphones support left/right channel select
- separate power decoupling near each microphone

Placement rules:

- put microphone acoustic ports on the outward-facing edge
- keep microphone ports away from fingers, clip plastic, fabric and mounting holes
- keep switching power components and high-current traces away from microphones
- reserve a mechanical keep-out around each acoustic port
- place left/right microphones with enough spacing to test basic direction and noise behavior

V1 firmware should allow:

- left-only recording
- right-only recording
- stereo recording
- mono mixdown

### 3. Storage

Use microSD for V1.

Why:

- large capacity
- easy test data extraction
- simple replacement during field tests
- avoids premature storage-size decisions

Design notes:

- connect microSD over SPI first for simplicity
- add ESD protection if the slot is externally accessible
- place the socket so the card can be changed without disassembling the whole prototype
- include a card-detect signal if the chosen socket supports it

Future replacement candidates:

- eMMC for production robustness
- SPI NAND for lower profile designs
- larger onboard flash if audio retention requirements shrink

### 4. Power And Charging

Power input:

- USB-C 5 V input
- single-cell LiPo battery

Power blocks:

- USB-C CC resistors for sink mode
- LiPo charger
- battery protection or protected cell connector
- low-quiescent-current 3.3 V regulator
- current-measurement link between regulator output and the main 3.3 V load rail
- battery voltage sense divider controlled by GPIO or high-value resistors

V1 design target:

- stable 3.3 V during Wi-Fi burst current
- low sleep current
- measurable current paths for sleep, listening, recording and sync modes

Recommended test points:

- USB 5 V
- battery positive
- charger status pins
- regulator input
- regulator output side of the 3.3 V measurement link
- 3.3 V output
- GND

### 5. User Interaction

Controls:

- mark button: marks current and recent audio as important
- mute switch: physical privacy control
- reset button
- boot button

Feedback:

- RGB LED or two discrete LEDs
- vibration motor for silent confirmation

Suggested state policy:

| State | LED | Vibration |
| --- | --- | --- |
| idle/listening | short low-duty pulse or off | none |
| voice recording | visible recording indication | none |
| muted | persistent but low-power indication | one short pulse on entry |
| marked | brief confirmation blink | short pulse |
| syncing | slow blink | none |
| storage fault | error blink pattern | double pulse |
| low battery | infrequent warning blink | optional |

### 6. Privacy And Security Reserve

Required for V1:

- physical mute switch connected to GPIO
- recording indicator LED behavior defined in firmware
- test procedure that verifies muted state prevents audio writes

Reserve:

- I2C secure element footprint
- I2C pull-ups sized for low power
- device identity and key storage hooks in firmware
- storage metadata version field

The V1 PCB can populate the secure element as DNP until encryption flow is ready.

### 7. Connectors And Test Access

External connectors:

- USB-C
- LiPo battery connector
- microSD socket

Prototype test access:

- 3.3 V, 5 V, battery, GND
- USB D+, USB D-
- I2S BCLK, LRCLK, DATA
- SPI CLK, MOSI, MISO, CS
- mute GPIO
- mark button GPIO
- motor drive GPIO
- battery sense ADC
- EN/reset and boot pins

## Suggested ESP32-S3 Pin Budget

Exact GPIO assignment should be finalized after ESP32-S3 bare-chip boot strapping pins, flash/PSRAM pins and RF/layout constraints are checked.

Current state: the Rev A model has a working core assignment, but 17 symbol pins are still intentionally left unconnected pending final NC / reserved-pin review. Treat the pin budget as provisional, not release-closed.

Current Rev A pin refinement notes are tracked in `docs/09_pin_and_net_refinement.md`.

| Function | Signals | Notes |
| --- | --- | --- |
| USB | D+, D- | use native USB pins required by ESP32-S3 |
| I2S microphones | BCLK, LRCLK, DIN | shared stereo digital mic bus |
| microSD SPI | SCLK, MOSI, MISO, CS, CD optional | use SPI for prototype simplicity |
| LED | 1 GPIO or 3 GPIO | addressable LED saves pins; discrete RGB is simpler electrically |
| mark button | 1 GPIO | interrupt-capable preferred |
| mute switch | 1 GPIO | must be sampled on wake |
| motor driver | 1 GPIO | low-side MOSFET gate |
| battery sense | 1 ADC | divider should not waste standby current |
| secure element | SDA, SCL | shared I2C reserve |
| charger status | 1-2 GPIO | optional, useful for UI |

## Power Modes

### Shipping / Hard Off

- battery connected but system disabled as much as possible
- only charger/protection remains active
- used before first user activation

### Standby

- ESP32-S3 in deep sleep or light sleep
- periodic wake or low-power audio strategy TBD
- LED off or extremely low duty cycle

### Listening

- microphones powered
- audio ring buffer active
- lightweight VAD active
- Wi-Fi off

### Recording

- microphones active
- audio written to microSD
- pre-roll and post-roll buffers active
- recording indicator active

### Syncing

- Wi-Fi active
- microSD reads active
- uploads deferred if battery is too low
- preferred while charging

## PCB Layout Guidance

Board zones:

- top/outward edge: microphones and acoustic keep-outs
- one board corner/edge: RF matching network and antenna keep-out
- near RF section: ESP32-S3 bare SoC, crystal and RF passives
- opposite side from microphones: charger, regulator and motor driver
- accessible edge: USB-C and microSD
- center/back side: battery connector and clip/mechanical features

Routing priorities:

- keep antenna keep-out free of copper and metal
- keep RF trace short, impedance-controlled and tunable with pi-network footprints
- keep crystal close to ESP32-S3 and away from high-speed/noisy traces
- keep flash/PSRAM close to ESP32-S3 and route memory bus with controlled length and clean reference
- keep microphone ports mechanically open
- keep power switching currents away from microphone area
- route USB D+/D- as a short matched pair
- keep I2S and SPI traces tidy, with nearby ground reference
- add plenty of ground stitching around noisy power and digital areas

## Firmware Interface Contract

The hardware should expose enough signals for this firmware flow:

1. Boot and read mute switch.
2. If muted, disable microphone capture and show muted state.
3. If not muted, enter listening mode.
4. Maintain a short audio pre-roll buffer.
5. When VAD triggers, write a timestamped segment to storage.
6. If mark button is pressed, protect recent/current segment.
7. Sync over Wi-Fi when requested or while charging.
8. Fall back to USB debug/export for bring-up.

## Validation Plan

Bring-up checks:

- USB enumerates.
- Battery charges from USB-C.
- 3.3 V rail remains stable during Wi-Fi transmit.
- ESP32-S3 can enter and wake from low-power states.
- Both microphones produce valid I2S audio.
- microSD can sustain expected write rate.
- mark button, mute switch, LED and motor all work.
- mute state prevents audio file writes.

Field checks:

- 1 hour desk recording test.
- 4 hour carry test.
- 12 hour battery test.
- pocket/bag false trigger test.
- noisy cafe/office VAD test.
- USB export test.
- Wi-Fi sync test while charging.

## Open Engineering Decisions

- whether V1 needs a dedicated low-power audio/VAD chip
- whether microSD is acceptable for wearable reliability
- whether LED recording indication should be always visible or user-configurable
- whether secure element should be populated in Rev A
- whether to use an addressable RGB LED or discrete LEDs
- whether the board should expose a speaker/buzzer footprint
