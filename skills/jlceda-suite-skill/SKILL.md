---
name: kicad-suite-skill
description: Generate and validate KiCad hardware design artifacts from structured requirements using the KiCad Suite pipeline.
---

# KiCad Suite Skill

## When to use

Use this skill when the user wants an AI agent to produce or inspect KiCad-oriented hardware design artifacts.

The active workflow is KiCad-only:

- clarify electrical requirements before synthesis
- convert requirements into a typed `RequirementSpec`
- synthesize a `CircuitModel`
- derive connection truth as `Netlist`
- export a SPICE netlist and collect ngspice feedback
- compile a `KiCadExecutionPlan`
- write `.kicad_pro` and `.kicad_sch` files
- optionally run `kicad-cli` ERC

Legacy EasyEDA/JLCEDA live-session bridge flows are archived under `legacy/` and should not be used for new work.

## Default Workflow

1. Read the user's design intent and identify missing electrical constraints.
2. If the requirement is underspecified, clarify input source, outputs, current, interfaces, packages, and acceptance checks.
3. Build or normalize `BRIDGE_REQUIREMENT_SPEC_JSON`.
4. Run the KiCad pipeline with `npm run text-to-kicad`.
5. Review generated model, netlist, ngspice feedback, KiCad execution plan, and write summary.
6. Run `npm run ngspice:regression` or `npm run erc` when relevant.
7. Report generated files, diagnostics, and next KiCad mapping or validation tasks.

## Reference Map

Use the smallest relevant reference set:

- `references/requirement-clarification.md` for incomplete requirements
- `references/strap-and-bias-rules.md` for mode pins, straps, pulls, and defaults
- `references/netlist-guidelines.md` for connection truth and simulation-ready structure
- `references/simulation-guidelines.md` for ngspice validation
- `references/decision-log-template.md` for engineering decisions and assumptions
- `references/schematic-construction-description.md` for strict schematic intent structure
- `references/text-to-schematic.md` for the older text-to-schematic terminology, interpreted as text-to-KiCad in this repository

## Scripts

### Root Commands

- `npm run text-to-kicad`: end-to-end RequirementSpec to KiCad output
- `npm run pipeline`: same KiCad target through the generic entry
- `npm run compile-plan`: compile CircuitModel and Netlist into KiCadExecutionPlan
- `npm run write-project`: write KiCad project files from an execution plan
- `npm run erc`: run KiCad ERC when `kicad-cli` and input paths are available
- `npm run ngspice:regression`: run ngspice feedback regression fixtures

### `scripts/server-text-to-schematic.mjs`

Compatibility wrapper for older skill callers. It now invokes:

- `src/kicad_suite/server_text_to_kicad.py`，兼容入口保留在 `scripts/server_text_to_kicad.py`

Prefer the root command `npm run text-to-kicad` for new work.

## Output Expectations

The pipeline normally writes into:

```text
.where/kicad-output/<project_name>/
```

Expected artifacts:

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

## Call Strategy

- Keep assumptions explicit in the requirement and decision log.
- Treat `Netlist` as the source of electrical connection truth.
- Prefer real KiCad library mappings over placeholder symbols when available.
- Use ngspice feedback to surface verification risk, not to silently accept a design.
- Use KiCad ERC as an additional check after file generation.
- Keep EasyEDA/JLCEDA references confined to `legacy/`.
