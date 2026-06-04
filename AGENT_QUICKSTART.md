# KiCad Agent Suite Quick Start

This package is built for agents that need to inspect, modify, validate, diagnose, and export hardware designs.

## Start Here

1. Treat `source/circuit-model.source.json` as the human-authored source of truth.
2. Treat `build/circuit-model.resolved.json` as the toolchain-derived overlay.
3. Treat `build/` and `output/` as generated.
4. Prefer the `hwtool agent` command surface.

## Standard Workflow

Run this sequence for a normal project iteration:

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

Do not run `export-kicad` if `validate-ir` reports errors.

## Directory Layout

```text
<project-root>/
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
```

## Agent Repair Loop

When something fails, use structured diagnostics instead of guessing:

```powershell
hwtool agent diagnose --project .
```

Then repair through model APIs:

```powershell
hwtool agent patch --project . --payload-json '{...}'
hwtool agent run <operation> --project . --payload-json '{...}'
```

After a repair, rerun:

```powershell
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent diagnose --project .
```

## Model Fields

- `ref`: stable schematic reference, such as `U1`, `R3`, or `C5`.
- `role`: functional purpose.
- `value`: human-readable component value or description.
- `package`: generic package, such as `C0603`, `LQFP-48`, or `SOT-223`.
- `selected_part.lcsc_id`: real LCSC identifier used for downloads.
- `selected_part.display_name`: descriptive metadata only.
- `selected_part.symbol_ref`: normally written by the resolver after download.
- `selected_part.kicad_footprint_hint`: normally written by the resolver after download.

## Practical Rules

- Do not use root-level `circuit-model.json` for new projects.
- Do not use `legacy-*` output names for new projects.
- Do not hand-edit `build/` or `output/`.
- Do not treat `display_name` as a stable export key.
- Do not hand-author `selected_part.symbol_ref` unless intentionally overriding resolver output.
- Re-run `resolve-symbols` after changing part choices.
- Re-run `build-ir` and `validate-ir` after changing the source model.
- Review `diagnose`, validation, and ERC results before shipping a design.

## If Something Looks Wrong

- Missing or wrong symbols usually mean `resolve-symbols` needs to run again.
- Missing footprints usually mean the selected part needs a better `kicad_footprint_hint`.
- `PROJECT_STATE_STALE` means the source model changed after the last recorded build.
- ERC `library_noise` usually points to imported library metadata, not necessarily a real circuit error.
- ERC `must_fix` should be repaired before proceeding.
