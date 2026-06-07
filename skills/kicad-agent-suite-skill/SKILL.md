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

Use workflow orchestration as the primary entrypoint for project work:

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent workflow status --project .
hwtool agent workflow run --project . --template full_build_v1 --timeout 120
hwtool agent workflow status --project .
hwtool agent report --project . --markdown
```

`full_build_v1` covers: LCSC check → IR build & validate → KiCad export → ERC diagnose.
When it returns `waiting_for_agent`, resolve the task; when it returns `completed`, the
KiCad project has been generated and ERC is clean.

Workflow rules:

- Start with `status`, `inspect`, and `diagnose` before editing.
- Run workflow templates, not ad hoc atomic commands, to create and manage agent tasks.
- Use `full_build_v1` as the main workflow unless the user asks for a specific child workflow.
- Use `lcsc_selection_v1` for LCSC selection tasks.
- Use `ir_repair_v1` for IR validation repair tasks.
- Use `repair_after_diagnose_v1` for ERC/diagnose repair or review tasks.
- Use `unknown_task_v1` for unclassified workflow conditions.
- `build-ir`, `validate-ir`, and `export-kicad` remain available as diagnostic/debug atomic commands. Prefer workflow templates for normal project work.

## Agent Repair Loop

For automated repair, use this loop:

```text
inspect -> diagnose -> workflow run/status -> patch/run if task requires it -> rerun workflow
```

`full_build_v1` handles IR build, IR validation, KiCad export, and ERC diagnose
internally. The agent only needs to resolve tasks when the workflow returns
`waiting_for_agent`.

Use these interfaces:

- `hwtool agent inspect --project .` for project summary and model counts.
- `hwtool agent diagnose --project .` for structured repair categories.
- `hwtool agent workflow run --project . --template full_build_v1` for the main workflow (LCSC → IR → export → ERC).
- `hwtool agent workflow run --project . --template lcsc_selection_v1` for LCSC selection tasks.
- `hwtool agent workflow run --project . --template ir_repair_v1` for IR validation repair tasks.
- `hwtool agent workflow run --project . --template repair_after_diagnose_v1` for diagnose-driven repair/review tasks.
- `hwtool agent workflow run --project . --template unknown_task_v1` for unknown task classification.
- `hwtool agent workflow propose --project . --file <plan.json>` for a validated agent-proposed workflow when no built-in template fits.
- `hwtool agent workflow choose-route --project . --workflow <template-id>` after a `choose_workflow_route_v1` route task.
- `hwtool agent workflow status --project .` for pending workflow task summary.
- `hwtool agent status --project .` includes workflow stack/task summary for the Agent.
- `hwtool agent patch --project . --payload-json '{...}'` for JSON patch changes.
- `hwtool agent run <operation> --project . --payload-json '{...}'` for model API operations.
- `hwtool agent pins free --project . --ref U1` for available MCU pins.
- `hwtool agent pins check --project .` for pin conflicts.
- `hwtool agent jlc search "<keyword>" -n 5` before choosing unknown LCSC IDs.
- `hwtool agent jlc download --lcsc-id C8734 --project .` for a single part download.

Atomic commands such as `resolve-symbols`, `jlc search`, `jlc info`, `agent run`,
and `agent patch` are tools used inside a workflow decision. Do not use them as
the top-level plan when a workflow template can represent the task.

## LCSC Selection Loop

`lcsc_selection_v1` is the workflow for LCSC selection. It does not depend on
`resolve-symbols` as a workflow step. The workflow only scans for components
that are missing `selected_part.lcsc_id` and emits agent tasks for those parts.
`resolve-symbols` remains a legacy helper for downloading already-selected
parts, not the selection engine.

Start with:

```powershell
hwtool agent workflow run --project . --template lcsc_selection_v1 --timeout 120
hwtool agent workflow status --project .
```

When `needs_selection` is returned:

- Read the current task from `hwtool agent workflow status --project .` or from `build/agent-tasks.json`.
- Use the component `role`, `value`, `package`, sheet, nets, notes, and search hints to build a search query.
- Run `hwtool agent jlc search "<query>" -n 5`, then inspect plausible candidates with `hwtool agent jlc info <C...>`.
- Write the selected part through `hwtool agent run set_selected_part --project . --payload-json '{...}'`.
- Re-run `hwtool agent workflow run --project . --template lcsc_selection_v1 --timeout 120`.
- Write `selected_part.lcsc_id` through Model API.
- Do not treat `resolve-symbols` as the workflow's decision maker.

Example:

```powershell
hwtool agent run set_selected_part --project . --payload-json '{
  "ref": "R1",
  "part": {
    "lcsc_id": "C22843",
    "display_name": "10k 1% 0603 resistor",
    "mpn": "0603WAF1002T5E",
    "manufacturer": "UNI-ROYAL",
    "package": "0603"
  }
}'
```

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
- Let `export-kicad` generate the actual `.kicad_pcb`.

## Service Boundaries

When changing code, keep repair logic in the right service:

- Part download and selected-part overlay: `PartResolutionService`.
- Symbol injection, symbol cache sync, symbol sanitization, and pin-type normalization: `SymbolNormalizationService`.
- Footprint library sync, footprint sanitization, KiCad lib tables, and GUI asset checks: `FootprintResolutionService`.
- ERC classification: `ErcClassificationService`.
- Agent-facing structured diagnosis: `build_agent_diagnostics`.
- Project lifecycle state: `ProjectState`.

Do not scatter special-case ERC, symbol, or footprint fixes across CLI handlers, writers, or orchestration code.

## Common Problems

Use structured diagnostics first:

```powershell
hwtool agent diagnose --project .
```

Common interpretations:

- `footprint not found`: verify `selected_part.lcsc_id`; inspect `kicad_footprint_hint`; use `resolve-symbols` only as a legacy helper if you intentionally want to download selected parts.
- `pin_to_pin` with generic or unspecified pins: often library metadata; check `library_noise` before changing nets.
- `pin_not_driven` on passives: often imported symbol pin types; check whether classification marks it as `library_noise`.
- `duplicate pin number`: real model issue; inspect net members and pinmap.
- `PROJECT_STATE_STALE`: rerun `hwtool agent workflow run --template full_build_v1` after source changes.

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

## Quick Command Reference

```powershell
hwtool agent manifest
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent workflow run --project . --template full_build_v1 --timeout 120
hwtool agent workflow status --project .
hwtool agent report --project . --markdown
hwtool agent build-ir --project .       # diagnostic / debug only
hwtool agent validate-ir --project .    # diagnostic / debug only
hwtool agent export-kicad --project .   # diagnostic / debug only
hwtool agent patch --project . --payload-json '{...}'
hwtool agent run <operation> --project . --payload-json '{...}'
hwtool agent pins free --project . --ref U1
hwtool agent pins check --project .
hwtool agent jlc search "STM32F103C8T6" -n 5
```
