# AGENTS.md

This file defines repository-specific instructions for AI coding agents (Claude Code, Codex, etc.)
using the KiCad Agent Suite hardware toolchain.

## Quick Reference — hwtool Commands

All commands operate on a project directory containing `circuit-model.json`.

```powershell
# Project lifecycle
hwtool agent status     --project .        # Show project state
hwtool agent inspect    --project .        # Detailed project summary
hwtool agent explain    --project .        # Human-readable status

# Build pipeline (run in order)
hwtool agent build-ir       --project .    # circuit-model.json → build/ir.v1.json
hwtool agent validate-ir    --project .    # Validate IR, check diagnostics
hwtool agent export-kicad   --project .    # Generate .kicad_pro + .kicad_sch + .kicad_pcb

# Part resolution
hwtool agent resolve-symbols --project . --timeout 120   # Download JLC symbols + footprints

# JLC / LCSC
hwtool agent jlc search "<keyword>" -n 5           # Search LCSC parts
hwtool agent jlc download --lcsc-id C8734 --project . # Download single part

# Reports & diagnostics
hwtool agent report    --project . --markdown       # Generate build/report.md
hwtool agent doctor    --project .                  # Environment check
hwtool agent history   --project .                  # Operation history
hwtool agent self-test                               # Run test suite

# Model manipulation
hwtool agent run <operation> --project . --payload-json '{...}'  # DSL API operations
hwtool agent patch        --project . --payload-json '{...}'     # JSON patch model

# Pin management
hwtool agent pins free  --project . --ref U1            # List free MCU pins
hwtool agent pins check --project .                     # Check pin conflicts
```

## Mandatory Workflow

**Every build MUST follow this sequence.  Never skip a step.**

### Step 1 — Understand current state

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
```

### Step 2 — Resolve parts (first build, or after model changes)

```powershell
hwtool agent resolve-symbols --project . --timeout 120
```

Downloads symbols and footprints from JLC/LCSC into `libraries/`.  This step is REQUIRED
before the first `export-kicad` — without it the PCB will have no footprints.

### Step 3 — Build and validate IR

```powershell
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
```

- If `validate-ir` returns `ok: false`, read the `diagnostics` array.
- Each diagnostic has `code`, `location`, `message`, and often a `suggestion` with the exact fix command.
- Fix ALL errors before proceeding.

### Step 4 — Export KiCad project

```powershell
hwtool agent export-kicad --project .
```

Generates:
- `output/<topology>/<topology>.kicad_pro` — project file
- `output/<topology>/<topology>.kicad_sch` — schematic
- `output/<topology>/<topology>.kicad_pcb` — PCB layout
- `output/<topology>/<topology>.erc.json` — ERC results

### Step 5 — Report

```powershell
hwtool agent report --project . --markdown
```

## circuit-model.json — Writing Guide

The AI agent writes `circuit-model.json` as the single source of truth.
The authoritative schema is at `schemas/circuit-model.v1.json` — read it for exact field definitions.

### Component rules

- Every component MUST have `ref`, `role`, `value`, `package`, `selected_part`.
- `selected_part` MUST contain `lcsc_id` (LCSC part number) and `display_name`.
- `package` contains the generic physical package (e.g. "C0603", "QFN-32", "SOT-223").
- If the JLC footprint name differs from the generic package, add `kicad_footprint_hint` inside `selected_part` with the exact JLC .kicad_mod filename.
- After running `resolve-symbols`, `kicad_footprint_hint` is populated automatically.

### Net rules

- Every net MUST have `name`, `kind`, `members`.
- `kind` is one of: `"power"`, `"ground"`, `"signal"`.
- `members` are `"REF.PIN"` strings, e.g. `"U1.23"`, `"J2.2"`.
- Net names starting with `+` are automatically classified as power; `GND` / `AGND` / `DGND` as ground.

### Sheet rules

- Every component MUST appear in exactly one sheet.
- Sheet `nets` list only the nets exposed at that sheet boundary.

### pcb_layout rules

- Place components in named `regions` with `x`, `y`, and optional `rotation` / `spacing`.
- Components placed in a region are automatically positioned left-to-right.

## Source of Truth

| File | Role |
|------|------|
| `circuit-model.json` | ✏️ Editable — the AI's source of truth |
| `schemas/circuit-model.v1.json` | Schema — read for field definitions |
| `build/ir.v1.json` | Generated — do NOT edit |
| `build/ir-validation.json` | Generated — do NOT edit |
| `build/rule-check.json` | Generated — do NOT edit |
| `output/` | Generated KiCad files — do NOT edit directly |

## Common Problems

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `footprint not found` × many | Libraries not downloaded | Run `resolve-symbols` |
| PCB is blank in KiCad 10 | Old pcb_generator format | Ensure hwtool is rebuilt with latest pcb_generator.py |
| `pin_to_pin` ERC violation | Power pin type mismatch | Check component symbol pin types |
| `duplicate pin number` | Same pin assigned to two nets | Check net members for conflicts |
| IR validation errors | Model field format issues | Read `diagnostics[].suggestion` for fix commands |

## Do Not

- Do NOT edit files under `build/` or `output/` manually.
- Do NOT skip `validate-ir` before `export-kicad`.
- Do NOT proceed to next stage if current stage has errors.
- Do NOT guess LCSC IDs — search with `hwtool agent jlc search` first.

## Example Projects

- `examples/stm32f103-minimal-system/` — STM32F103C8T6 ARM Cortex-M3 minimal system (verified PCB)
- `examples/esp32c3-minimal-system/` — ESP32-C3FH4 RISC-V minimal system (verified PCB)

Study these for `circuit-model.json` structure and `pcb_layout.regions` patterns.
