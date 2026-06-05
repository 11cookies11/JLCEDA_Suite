---
name: kicad-agent-suite-skill
description: Use KiCad Agent Suite to create, inspect, repair, validate, and export circuit projects through the current hwtool agent workflow. Use when an AI agent needs to edit source/circuit-model.source.json, resolve LCSC/JLC parts, generate KiCad projects, diagnose ERC/IR failures, or safely patch a hardware design without relying on legacy root-level model files.
---

# KiCad Agent Suite Skill

## Use This Skill When

Use this skill when the task is hardware-design work that should go through KiCad Agent Suite instead of ad hoc file edits.

Typical tasks:

- Create or modify a circuit model.
- Resolve real LCSC/JLC symbols and footprints.
- Generate KiCad schematic and PCB files.
- Diagnose IR validation, ERC, missing symbol, or missing footprint issues.
- Let an Agent inspect a project, patch the model, rerun checks, and decide the next repair.
- Refactor the toolchain while preserving the current agent-facing contracts.

## Current Protocol

The current source of truth is the split project layout:

```text
<project-root>/
  source/
    circuit-model.source.json
  build/
    circuit-model.resolved.json
    ir.v1.json
    ir-validation.json
    placement-plan.json
    placement-plan.md
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
- Treat `build/` as generated.
- Treat `output/` as generated evidence, not the design source of truth.
- Treat `libraries/` as project-local downloaded KiCad assets.
- Do not use root-level `circuit-model.json` for new projects.
- Do not use `legacy-*` output names for new projects.
- Do not manually edit `build/` or `output/` to fix behavior.

## Mandatory Agent Workflow

Run these stages in order for project work:

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent build-kicad-plan --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown
```

Workflow rules:

- Start with `status`, `inspect`, and `diagnose` before editing.
- Run `resolve-symbols` before the first KiCad export, or after part choices change.
- Run `build-ir` and `validate-ir` after model changes.
- Do not run `export-kicad` if `validate-ir` reports errors.
- Run `diagnose` again after repairs so the Agent can compare structured results.

## Agent Repair Loop

For automated repair, use this loop:

```text
inspect -> diagnose -> patch/run -> resolve-symbols if needed -> build-ir -> validate-ir -> build-kicad-plan -> export-kicad -> diagnose
```

Use these interfaces:

- `hwtool agent inspect --project .` for project summary and model counts.
- `hwtool agent diagnose --project .` for structured repair categories.
- `hwtool agent patch --project . --payload-json '{...}'` for JSON patch changes.
- `hwtool agent run <operation> --project . --payload-json '{...}'` for model API operations.
- `hwtool agent pins free --project . --ref U1` for available MCU pins.
- `hwtool agent pins check --project .` for pin conflicts.
- `hwtool agent jlc search "<keyword>" -n 5` before choosing unknown LCSC IDs.
- `hwtool agent jlc download --lcsc-id C8734 --project .` for a single part download.

Interpret `diagnose` categories:

- `must_fix`: real blocker. Patch the source model or selected part data before continuing.
- `review_required`: needs engineering judgement or a rerun after stale state.
- `library_noise`: likely symbol/footprint/ERC metadata noise. Do not blindly change the circuit model unless the diagnosis points to a real electrical issue.

## Circuit Model Rules

For each component:

- Use stable `ref`, such as `U1`, `R3`, `C5`, `J2`.
- Provide `role`, `value`, `package`, and `selected_part`.
- `selected_part.lcsc_id` is the stable download key.
- `selected_part.display_name` is descriptive only.
- `selected_part.symbol_ref` is normally resolver-owned output.
- `selected_part.kicad_footprint_hint` is normally resolver-owned output, unless the Agent is applying an intentional footprint override.

For each net:

- Use `name`, `kind`, and `members`.
- `kind` is `power`, `ground`, or `signal`.
- `members` are `REF.PIN` strings, such as `U1.23`.
- Power nets should use names like `+3V3`, `+5V`, `VBAT`.
- Ground nets should use `GND`, `AGND`, or `DGND`.

For sheets:

- Every component should appear in exactly one sheet.
- Sheet `nets` should list the boundary nets exposed by that sheet.

For PCB layout:

- Put placement intent in `pcb_layout.regions`.
- Run `hwtool agent build-kicad-plan --project .` to compile the placement plan for inspection.
- The placement plan is written to `build/placement-plan.json` and `build/placement-plan.md`.
- Use `layout-lab` for pre-export visualization and rule validation (see Layout-Lab section below).
- Let `export-kicad` generate the actual `.kicad_pcb` from the placement plan.

## Layout-Lab (Placement Sandbox)

Layout-lab is a standalone PCB placement visualization sandbox. It does NOT call KiCad — it validates placement rules visually before wiring them into the production pipeline.

### When to Use

- Before `export-kicad`, to preview and tune component placement.
- When adding or refactoring `pcb_layout.regions` in the circuit model.
- To visually explain placement decisions to the user.

### Run

```powershell
# Single scenario
python scripts/layout_lab.py --scenario examples/layout-lab/scenario.json --out tmp/layout-lab

# Batch samples + gallery
python scripts/layout_lab_batch.py
```

### Outputs

- `tmp/layout-lab/steps/*.svg` — one SVG per placement step
- `tmp/layout-lab/final.svg` — final board layout
- `tmp/layout-lab/layout-summary.json` — score breakdown for each candidate
- `tmp/layout-lab/report.md` — human-readable summary
- `tmp/layout-lab/steps.html` — step-by-step gallery

### Key Concepts

- **Grid**: 1mm x 1mm. Anchor is the lower-left corner of the occupied rectangle.
- **Patterns** (defined in `patterns.json`): `center_cluster`, `power_chain`, `clock_ring`, `usb_interface_chain`, `boot_reset_cluster`, `rf_island`, `debug_access_cluster`, `indicator_cluster`, `analog_island`, `edge_connector`, `high_current_path`, `signal_chain`, `diff_pair_adjacency`, `rf_keepout_island`.
- **Roles** (defined in `roles.json`): role defaults, slot preferences, cluster slot order, board defaults.
- **Solver**: constraint-based candidate search → filter (margin, overlap, keepout) → score → recurse with backtracking.
- **Scoring**: Each placed candidate gets a score breakdown in the summary JSON.

### Files

| File | Purpose |
|------|---------|
| `examples/layout-lab/scenario.json` | Board size, components, pattern membership |
| `examples/layout-lab/patterns.json` | Pattern summaries, colors, template defaults |
| `examples/layout-lab/roles.json` | Role defaults, slot preferences |
| `examples/layout-lab/rules.json` | Legacy combined input (kept for compatibility) |
| `scripts/layout_lab.py` | Solver + SVG renderer |
| `scripts/layout_lab_batch.py` | Batch runner for samples + gallery |

## Placement Planner (Pipeline Integration)

The placement planner (`application_services/placement_planner.py`) translates `pcb_layout.regions` into a structured placement plan consumed by `export-kicad`. It auto-generates:

- Grid-based packing within each region (sqrt-column layout by component priority).
- Component size estimation from role/package/selected_part.
- Overlap detection between regions.
- Fallback "unassigned" region for components not in any explicit region.
- Board size inference from constraints or region extents.

Output schema: `placement-plan.v1`. Written as `build/placement-plan.json`.

Key CLI entry: `hwtool agent build-kicad-plan --project .` (compiles the KiCad execution plan including the placement plan).

## Service Boundaries

When changing code, keep repair logic in the right service:

- Part download and selected-part overlay: `PartResolutionService`.
- Symbol injection, symbol cache sync, symbol sanitization, and pin-type normalization: `SymbolNormalizationService`.
- Footprint library sync, footprint sanitization, KiCad lib tables, and GUI asset checks: `FootprintResolutionService`.
- ERC classification: `ErcClassificationService`.
- Agent-facing structured diagnosis: `build_agent_diagnostics`.
- Project lifecycle state: `ProjectState`.
- Placement planning and region packing: `PlacementPlanner` / `build_placement_plan`.
- PCB generation with placement plan consumption: `pcb_generator`.

Do not scatter special-case ERC, symbol, or footprint fixes across CLI handlers, writers, or orchestration code.

## Common Problems

Use structured diagnostics first:

```powershell
hwtool agent diagnose --project .
```

Common interpretations:

- `footprint not found`: run `resolve-symbols`; verify `selected_part.lcsc_id`; inspect `kicad_footprint_hint`.
- `pin_to_pin` with generic or unspecified pins: often library metadata; check `library_noise` before changing nets.
- `pin_not_driven` on passives: often imported symbol pin types; check whether classification marks it as `library_noise`.
- `duplicate pin number`: real model issue; inspect net members and pinmap.
- `PROJECT_STATE_STALE`: rerun `build-ir` and `validate-ir` after source changes.

## Do Not

- Do not hand-edit `build/ir.v1.json`, `build/ir-validation.json`, `build/rule-check.json`, or `output/`.
- Do not guess LCSC IDs; search first.
- Do not restore legacy root-level model workflow.
- Do not add compatibility with obsolete file names unless the user explicitly asks for migration tooling.
- Do not fix ERC by adding one-off if/else blocks in random modules.
- Do not treat `display_name` as a stable symbol or footprint identifier.
- Do not proceed past validation errors.

## Release Package Expectations

A release package should include enough for agents and users to run `hwtool` without the repository checkout:

- `hwtool.exe`
- `AGENTS.md`
- `AGENT_QUICKSTART.md`
- `README.md`
- `README.zh-CN.md`
- `CHANGELOG.md`
- `CHANGELOG.zh-CN.md`
- `docs/`
- `schemas/`
- `config/`
- `resources/`
- `packs/`
- `skills/kicad-agent-suite-skill/`
- verified examples only

Do not include local caches, `.where/`, `.git/`, `node_modules/`, ignored project state files, backup folders, or temporary build outputs.

## Reference Map

Use the smallest relevant reference file:

- `references/requirement-clarification.md` for incomplete hardware requirements.
- `references/strap-and-bias-rules.md` for boot straps, pulls, and default states.
- `references/netlist-guidelines.md` for electrical connection truth.
- `references/simulation-guidelines.md` for ngspice-oriented checks.
- `references/decision-log-template.md` for assumptions and engineering decisions.
- `references/schematic-construction-description.md` for schematic intent.
- `references/refactoring-design-rules.md` before changing generator, resolver, validation, or service code.
- `references/text-to-schematic.md` only for older terminology; interpret it through the current `hwtool agent` workflow.
- `examples/layout-lab/README.md` for running the placement sandbox.
- `examples/layout-lab/ARCHITECTURE.md` for solver, pattern, and rendering design.

## Quick Command Reference

```powershell
# Project lifecycle
hwtool agent create <name> --board <board_name> --mcu <mcu> --topology single
hwtool agent manifest
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent explain --project .
hwtool agent diagnose --project .
hwtool agent doctor --project .

# Symbol & footprint resolution
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent jlc search "<keyword>" -n 5
hwtool agent jlc download --lcsc-id C8734 --project .

# IR build & validation
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent rule-check --project .

# KiCad generation
hwtool agent build-kicad-plan --project .
hwtool agent export-kicad --project .

# Reporting & history
hwtool agent report --project . --markdown
hwtool agent history --project .

# Model editing
hwtool agent patch --project . --payload-json '{...}'
hwtool agent run <operation> --project . --payload-json '{...}'

# Pin management
hwtool agent pins free --project . --ref U1
hwtool agent pins check --project .

# Self-test
hwtool agent self-test
```
