# 02 Design Decisions

Status: Draft

## Decision 1: Chest Badge / Clip Form Factor

Chosen for V1.

Reasoning:

- keeps microphones close to the user's speaking position
- supports daily carry without occupying hands
- allows a larger prototype PCB than an earbud or pendant
- leaves space for battery, microSD, buttons and debug pads

Design implication:

- board outline should reserve a clip or lanyard region
- microphone ports should face outward and avoid fabric blockage

## Decision 2: Voice-Triggered Recording

Chosen for V1.

Reasoning:

- reduces storage use
- improves battery life
- makes review and transcription less noisy
- better matches an AI memory device than a continuous recorder

Design implication:

- firmware must support VAD
- audio buffering is needed so the beginning of speech is not clipped
- marked moments should retain audio before and after the button press

## Decision 3: Encryption Reserved, Not Mandatory For First Bring-Up

Chosen for V1.

Reasoning:

- security architecture matters, but first hardware bring-up should not be blocked by key provisioning
- the PCB should leave room for secure storage if required later
- firmware should avoid hard-coding a storage format that prevents encryption later

Design implication:

- reserve I2C footprint for an optional secure element
- keep audio file metadata versioned
- define storage APIs with encryption hooks

## Decision 4: USB-C + Wi-Fi Sync

Chosen for V1.

Reasoning:

- USB-C is reliable for charging, debugging and fallback export
- Wi-Fi supports larger audio uploads than BLE
- BLE can still be used for provisioning or companion control

Design implication:

- ESP32-S3 bare-chip design should route native USB D+/D- for debug and export
- antenna keep-out must be respected
- power design must tolerate Wi-Fi current bursts

## Decision 5: Battery Life First

Chosen for V1.

Reasoning:

- a memory device fails if it is not alive when needed
- audio quality can improve over revisions, but unreliable uptime breaks trust

Design implication:

- choose low-Iq regulator and charger
- avoid always-on LEDs
- allow Wi-Fi sync to run only on demand or while charging
- measure current in sleep, listening, recording and syncing modes

## Decision 6: Prototype Board First

Chosen for V1.

Reasoning:

- bring-up visibility matters more than tiny size
- microSD, test pads and debug controls reduce iteration time
- mechanical and acoustic decisions need real-world testing

Design implication:

- do not over-optimize board area in Rev A
- keep test pads accessible
- include mounting / clip experiments in the PCB outline

## Decision 7: ESP32-S3 Bare Chip Instead Of Module

Chosen for V1 after product-direction review.

Reasoning:

- better matches the final wearable product shape
- avoids carrying unused module area into the industrial design
- gives direct control over antenna placement, Flash/PSRAM size and power layout
- forces early validation of the production-relevant RF and memory design

Design implication:

- Rev A must follow Espressif hardware design guidelines closely
- the schematic must include flash, PSRAM, crystal, RF matching, antenna and boot straps
- PCB layout must reserve RF tuning space and antenna keep-out
- bring-up plan must include crystal clock, flash boot and RF checks
- module-based ESP32-S3 remains the fallback if Rev A bare-chip bring-up blocks audio/system validation
