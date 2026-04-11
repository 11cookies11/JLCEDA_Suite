# JLCEDA Suite Workflow Guide

This guide describes the practical schematic-first collaboration flow for JLCEDA Suite.

## Goal

Use Codex together with JLCEDA to improve a target schematic, make part-selection decisions, and carry the confirmed design intent into PCB follow-up work.

## Recommended flow

### 1. Inspect the current context

Start by reading the active project and sheet state.

Run:

```bash
node skills/jlceda-suite-skill/scripts/server-context-summary.mjs
```

What to look for:

- active project and document kind
- active schematic name and page count
- current selection state
- safe suggested next steps

### 2. Compare candidate parts

Once the block intent is clear, evaluate realistic component options.

Run:

```bash
$env:BRIDGE_SELECTION_REQUIREMENTS_JSON='{"role":"buck regulator","functionBlock":"power-input"}'
node skills/jlceda-suite-skill/scripts/server-part-selector.mjs
```

What to look for:

- structured requirement summary
- candidate comparison and ranking
- selected part rationale
- BOM note and verification checklist

### 3. Apply a small schematic edit batch

Use the schematic refinement script only after the edit intent is clear.

Run:

```bash
$env:BRIDGE_SCHEMATIC_EDIT_PLAN_JSON='[...]'
node skills/jlceda-suite-skill/scripts/server-schematic-refine.mjs
```

What to look for:

- before and after context snapshots
- per-step execution results
- design decision log
- validation summary

### 4. Continue into PCB assistance

Carry the confirmed schematic block into the board stage.

Run:

```bash
$env:BRIDGE_PCB_ASSIST_OPTIONS_JSON='{"focusAreas":["power-input"]}'
node skills/jlceda-suite-skill/scripts/server-pcb-assist.mjs
```

What to look for:

- board and PCB summary
- hygiene issue count and issue-type summary
- placement advice for the active block
- short next-task list for the next PCB pass

### 5. Use command-runner templates when you need a normalized entry point

If you want one generic entry point instead of dedicated scripts, use the template-based runner.

Run:

```bash
$env:BRIDGE_RUNNER_TEMPLATE='inspect'
node skills/jlceda-suite-skill/scripts/server-command-runner.mjs
```

Supported templates:

- `inspect`
- `select`
- `design`
- `pcb`
- `export`

## Validation

The repository includes a workflow-level smoke test that exercises the skill entrypoints in sequence.

Run:

```bash
npm run workflow:skill:e2e:smoke-test
```

This test verifies that the server-side skill chain can:

- collect current context
- produce a part recommendation
- execute a schematic refinement batch
- produce PCB assistance output

## Notes

- Keep human review in the loop before any non-trivial schematic or PCB mutation.
- Prefer small edit batches over large one-shot transformations.
- Re-read context after every meaningful change so later guidance stays grounded in the real JLCEDA state.
