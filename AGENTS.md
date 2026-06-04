# AGENTS.md

Repository-specific instructions for AI coding agents using KiCad Agent Suite.

## Current Protocol

New projects use the split source/build layout:

```text
project/
  source/
    circuit-model.source.json
  build/
    circuit-model.resolved.json
    ir.v1.json
    ir-validation.json
    report.json
    report.md
  libraries/
    symbols/
    footprints/
    3dmodels/
  output/
    <topology>/
      <topology>.kicad_pro
      <topology>.kicad_sch
      <topology>.kicad_pcb
      <topology>.erc.json
      <topology>.erc.classification.json
      agent-report.json
```

Rules:

- Edit `source/circuit-model.source.json`.
- Treat `build/` and `output/` as generated.
- Use `libraries/` for downloaded project-local KiCad assets.
- Do not use root-level `circuit-model.json` for new projects.
- Do not use `legacy-*` output names for new projects.

## Quick Reference

All commands operate on a project directory containing `source/circuit-model.source.json`.

```powershell
# Project lifecycle
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent explain --project .
hwtool agent diagnose --project .

# Build pipeline
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown

# JLC / LCSC
hwtool agent jlc search "STM32F103C8T6" -n 5
hwtool agent jlc info C8734
hwtool agent jlc download --lcsc-id C8734 --project .

# Model manipulation
hwtool agent patch --project . --payload-json '{...}'
hwtool agent run <operation> --project . --payload-json '{...}'

# Pin management
hwtool agent pins free --project . --ref U1
hwtool agent pins assign --project . --ref U1 --pin 34 --net SWDIO
hwtool agent pins check --project .

# Maintenance
hwtool agent doctor --project .
hwtool agent history --project .
hwtool agent self-test
```

## Mandatory Workflow

Every build must follow this order:

1. Inspect current state.
2. Resolve symbols and footprints when parts changed or before first export.
3. Build and validate IR.
4. Export KiCad only after validation passes.
5. Generate report.
6. Run `diagnose` again after repairs.

Commands:

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown
hwtool agent diagnose --project .
```

## Agent Repair Loop

Use this loop for automated fixes:

```text
inspect -> diagnose -> patch/run -> resolve-symbols if needed -> build-ir -> validate-ir -> export-kicad -> diagnose
```

Interpret `diagnose` results:

- `must_fix`: real blocker; patch the model or selected part data.
- `review_required`: engineering judgement or stale-state rerun required.
- `library_noise`: likely symbol, footprint, or ERC metadata noise; do not blindly change the circuit model.

## Source Model Writing Guide

The authoritative schema is `schemas/circuit-model.v1.json`.

Component rules:

- Every component should have `ref`, `role`, `value`, `package`, and `selected_part`.
- `selected_part.lcsc_id` is the stable JLC/LCSC download key.
- `selected_part.display_name` is descriptive metadata only.
- `selected_part.symbol_ref` is normally resolver-owned output.
- `selected_part.kicad_footprint_hint` is normally resolver-owned output, unless intentionally overriding.

Net rules:

- Every net should have `name`, `kind`, and `members`.
- `kind` is `power`, `ground`, or `signal`.
- `members` are `REF.PIN` strings, such as `U1.23`.
- Names starting with `+` are power nets.
- `GND`, `AGND`, and `DGND` are ground nets.

Sheet rules:

- Every component should appear in exactly one sheet.
- Sheet `nets` lists only nets exposed at that sheet boundary.

PCB layout rules:

- Put placement intent in `pcb_layout.regions`.
- Let `export-kicad` generate the actual PCB file.

## Do Not

- Do not edit generated files under `build/` or `output/`.
- Do not skip `validate-ir` before `export-kicad`.
- Do not proceed if validation has errors.
- Do not guess LCSC IDs; use `hwtool agent jlc search`.
- Do not treat `display_name` as a symbol or footprint identifier.
- Do not add one-off ERC, symbol, or footprint repairs outside the dedicated services.

## Example Projects

- `examples/stm32f103-minimal-system/`
- `examples/esp32c3-minimal-system/`
- `examples/refactor-layout-demo/`
