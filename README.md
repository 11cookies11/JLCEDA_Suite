# KiCad Suite

AI-assisted KiCad hardware development pipeline.

Language: English | [简体中文](README.zh-CN.md)

## Overview

`KiCad Suite` turns structured hardware requirements into KiCad-ready artifacts. The current workflow is file-based: it does not drive a GUI editor. Instead, it generates intermediate design models, simulation inputs, KiCad schematic/project files, and structured validation summaries.

The active pipeline is:

```text
RequirementSpec
  -> CircuitModel
  -> Netlist
  -> SPICE Netlist
  -> ngspice feedback
  -> KiCadExecutionPlan
  -> .kicad_pro + .kicad_sch
  -> optional kicad-cli ERC
```

Older EasyEDA/JLCEDA bridge code is kept under `legacy/` for reference only. New work should target KiCad.

## Current Status

The KiCad path currently includes:

- JSON schemas for requirements, circuit models, netlists, SPICE netlists, ngspice feedback, and KiCad execution plans
- a Python requirement-to-KiCad pipeline
- role-aware schematic layout rules with optional ELK layout support
- KiCad project and schematic file generation
- ngspice export, execution, parsing, and feedback artifacts
- optional KiCad ERC through `kicad-cli`
- a small ngspice regression fixture set

## Commands

Install Node dependencies first:

```bash
npm install
```

Run the default KiCad pipeline:

```bash
npm run pipeline
```

Useful aliases:

```bash
npm run text-to-kicad
npm run compile-plan
npm run write-project
npm run erc
npm run ngspice:regression
```

The pipeline can use default requirements, or read a structured requirement from `BRIDGE_REQUIREMENT_SPEC_JSON`:

```bash
BRIDGE_REQUIREMENT_SPEC_JSON='{"schema_version":"requirement-spec.v1", "...":"..."}' npm run text-to-kicad
```

PowerShell example:

```powershell
$env:KICAD_PROJECT_NAME = 'led_indicator'
$env:BRIDGE_REQUIREMENT_SPEC_JSON = '{ "schema_version": "requirement-spec.v1", "...": "..." }'
npm run text-to-kicad
```

## Outputs

By default, generated KiCad artifacts are written under:

```text
.where/kicad-output/<project_name>/
```

Typical outputs:

- `requirement-spec.json`
- `circuit-model.json`
- `netlist.json`
- `spice-netlist.cir`
- `ngspice-execution.json`
- `ngspice-feedback.json`
- `kicad-execution-plan.json`
- `<project_name>.kicad_pro`
- `<project_name>.kicad_sch`
- `kicad-write-summary.json`
- `text-to-kicad-summary.json`

## Validation

Run the lightweight checks currently available from the root package:

```bash
npm run ngspice:regression
```

Optional KiCad ERC:

```bash
npm run erc
```

Set `KICAD_RUN_ERC=true` to let the full pipeline attempt ERC after writing the schematic. If `kicad-cli` is not installed, the runner returns a structured diagnostic instead of blocking file generation.

## Repository Layout

- `scripts/`: active Python and Node pipeline scripts
- `server/schemas/`: JSON schemas for the active model contracts
- `docs/`: architecture and workflow notes
- `skills/`: agent-facing workflow references
- `legacy/`: archived EasyEDA/JLCEDA bridge implementation and historical docs
- `.where/`: local generated outputs, logs, and planning notes

## Development Direction

KiCad is now the only active EDA target. Prefer changes that improve:

- KiCad symbol and footprint mapping
- deterministic schematic generation
- netlist correctness
- ngspice coverage and feedback quality
- KiCad ERC integration
- clear model contracts and regression fixtures

Do not add new EasyEDA/JLCEDA bridge functionality outside `legacy/`.

## License

See `LICENSE`.
