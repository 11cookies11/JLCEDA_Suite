# Hardware Semantic Layer v0.1

This document defines the first implementation slice for a topology-first hardware design workflow in KiCad Agent Suite.

The goal is to make the agent behave less like a schematic wiring tool and more like a hardware engineer: it must explain the purpose of every module, every IC pin, every power rail, and every external interface before KiCad export.

## Position in the existing workflow

Existing workflow:

```text
source/circuit-model.source.json
  -> resolve-symbols
  -> build-ir
  -> validate-ir
  -> export-kicad
```

New gated workflow:

```text
source/circuit-model.source.json
  -> resolve-symbols
  -> build-ir
  -> validate-ir
  -> hardware semantic gate
       -> build/net-intents.v1.json
       -> build/pin-contracts.v1.json
       -> build/hardware-erc.v1.json
       -> build/export-gate.v1.json
  -> export-kicad only when export-gate allows it
```

The first implementation is a sidecar layer. It does not require changing `circuit-model.v1` immediately.

## Why this layer exists

KiCad ERC can detect many schematic-level connection problems, but it does not know product intent. For example, it may not know that:

- a load switch with only ON connected is useless if VIN/VOUT are missing;
- a charger IC with ISET/ILIM/TS floating is not a complete charger design;
- a USB-C sink without CC Rd pulldowns may not receive VBUS;
- a connector pin marked NC may actually be a mode strap that must be fixed;
- a switched rail may have no downstream load;
- an external interface may need ESD or current limiting.

The Hardware Semantic Layer catches these design-intent failures before schematic export.

## Core artifacts

### 1. Net Intent

`build/net-intents.v1.json` explains what each net means:

- net kind;
- members;
- likely sources;
- likely loads;
- whether it is a power rail, ground reference, switched rail, or signal/configuration net.

This makes power-tree and signal-flow review machine-readable.

### 2. Pin Contract

`build/pin-contracts.v1.json` explains each important IC pin:

- pin type;
- whether it is required;
- resolved connection;
- whether NC is allowed;
- expected checks;
- engineering rationale.

A pin is not complete just because it has a wire. It is complete only when its behavior and default state are understood.

### 3. Hardware ERC

`build/hardware-erc.v1.json` contains semantic findings:

- `BLOCKER`: KiCad export must not run;
- `WARNING`: export may proceed only after review or waiver;
- `INFO`: improvement or layout/DFT note.

### 4. Export Gate

`build/export-gate.v1.json` is the single decision file:

```json
{
  "decision": "allow_export_kicad"
}
```

or:

```json
{
  "decision": "block_export_kicad"
}
```

## Agent operating principles

The agent must follow these rules:

1. Treat `source/` as the human-editable source of truth.
2. Treat `build/` and `output/` as generated artifacts.
3. Do not export KiCad when `validate-ir` or Hardware ERC has blockers.
4. Do not mark unknown pins NC without evidence.
5. Do not create power nets without source and load intent.
6. Do not leave EN, CE, MODE, BOOT, RESET, CS, ILIM, ISET, TS, or TMR behavior undefined.
7. Do not assume external interfaces are safe without ESD/TVS/current-limit review.
8. If information is missing, write an unresolved item instead of guessing.

## P0 scope

The first rule pack focuses on the components and interfaces that caused real errors in early designs:

- TPS22918-style load switches;
- BQ24074-style charger + power-path ICs;
- USB-C USB2 sink connectors;
- SPI e-paper display connectors.

The implementation is intentionally conservative. It may produce warnings that need review, but it should prevent obviously incomplete circuits from reaching KiCad export.

## Usage

Run from a project directory:

```powershell
python scripts/hardware_semantic_gate.py --project .
```

Expected outputs:

```text
build/net-intents.v1.json
build/pin-contracts.v1.json
build/hardware-erc.v1.json
build/export-gate.v1.json
```

Recommended full flow:

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
python scripts/hardware_semantic_gate.py --project .
hwtool agent export-kicad --project .
```

`hwtool agent export-kicad` runs this gate before the KiCad export step and refuses to continue when `build/export-gate.v1.json` says `block_export_kicad`. The standalone script remains useful for local diagnosis and CI-focused checks.

## Implementation roadmap

### P0

- Add sidecar schemas.
- Add a standalone semantic gate script.
- Add the first rule pack.
- Generate pin-contract, net-intent, hardware-erc, and export-gate artifacts.

### P1

- Integrate as native `hwtool agent hardware-erc` command.
- Add JSON schema validation for sidecar outputs.
- Add regression tests for TPS22918, BQ24074, USB-C sink, and e-paper connector cases.
- Include Hardware ERC status in `agent diagnose` and `agent report`.

### P2

- Promote stable fields into `circuit-model.v2` or keep sidecar as a formal extension mechanism.
- Expand rule packs for LDO/DCDC, MCU boot straps, I2C, SPI, UART, SWD/JTAG, battery connector, sensors, and NFC.
- Add waiver files for reviewed warnings.

## Design philosophy

The key phrase is:

> First prove the topology, then draw the schematic.

The agent should not ask, "Can I connect this wire?" It should ask:

- What function does this module serve?
- What energy, signal, and control flows pass through it?
- What is every pin responsible for?
- What default state exists at reset?
- What could fail during power-up, sleep, charging, hot-plug, or manufacturing test?

Only after that should the design enter KiCad.
