---
name: jlceda-suite-skill
description: Drive a connected JLCEDA Suite session through the suite server control plane, inspect the current hardware design context, and assist with component selection, schematic refinement, and PCB follow-up work.
---

# JLCEDA Suite Skill

## When to use

Use this skill when the user wants an AI agent to work together with them inside a live JLCEDA session.

The highest-value use case is schematic-first co-design:

- inspect the current project, sheet, and selected primitives before changing anything
- summarize the current design context for component selection or topology discussion
- compare candidate parts and record the rationale for the chosen component
- generate BOM-style notes and verification checklists for the selected part
- place or edit schematic content after the design intent is clear
- carry the same context forward into PCB assistance

## Default workflow

1. Confirm the JLCEDA Suite Server is running and the plugin session is connected.
2. Read `/sessions` and pick the target `clientId`.
3. Run `scripts/server-context-summary.mjs` to collect the current design context.
4. Use the summary to decide which mode you are in: `inspect`, `select`, `design`, or `export`.
5. Prefer dedicated bridge commands for common project, schematic, PCB, and system operations.
6. Use `system.api_invoke` only when the official JLCEDA API exists but has not been wrapped yet.
7. Keep the same connected session for the whole task chain so the design context stays coherent.

## Core modes

### 1. Inspect

Use this first unless the current design state is already obvious.

Goal:
- read the current bridge status, document summary, selection snapshot, and current schematic state
- identify the active project, active sheet, current selection, and immediate next design step

Primary script:
- `scripts/server-context-summary.mjs`

Output to produce:
- current document kind and project name
- current schematic name and page count
- whether the user already selected a component or net
- short list of safe next steps

### 2. Select

Use this when the user wants help choosing parts.

Goal:
- capture requirements such as voltage, current, package, cost, availability, interface, and tolerance
- compare 2-4 realistic candidates
- record why one part is the better fit for the current schematic block

Expected output:
- requirement summary
- candidate comparison table or bullet list
- selected part and rationale
- BOM note or follow-up validation note

### 3. Design

Use this when the user wants to improve the schematic.

Goal:
- identify the current function block
- propose the smallest safe schematic edit
- place parts, create wires, annotate nets, or import changes only after the design intent is agreed

Expected output:
- what will change
- why it changes the design in the right direction
- what to verify after the edit

### 4. Export

Use this when the user wants a handoff artifact.

Goal:
- export BOMs, summaries, or source snapshots for review
- leave enough context for the next schematic or PCB step

## Scripts

### `scripts/server-context-summary.mjs`

Use this as the default entry point for schematic collaboration.

Environment:
- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target

What it does:
- lists connected bridge sessions
- reads session debug information from the control plane
- requests `system.get_bridge_status`
- requests `project.get_document_summary`
- requests `project.get_selection_snapshot`
- requests `schematic.get_current_schematic_info`
- prints one structured JSON payload with suggested next steps

### `scripts/server-part-selector.mjs`

Use this when the user already has selection requirements or a short candidate list.

Environment:
- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target
- `BRIDGE_SELECTION_REQUIREMENTS_JSON`: JSON with the target role, constraints, and priorities
- `BRIDGE_SELECTION_CANDIDATES_JSON`: optional JSON array of candidate parts to compare

What it does:
- reads the current JLCEDA schematic context
- scores candidate parts against the supplied requirements
- returns a recommendation, BOM note, verification checklist, and next schematic actions
- returns a search plan when candidate parts are not supplied yet

### `scripts/server-schematic-refine.mjs`

Use this when the design intent is clear and you want to apply a small schematic edit batch.

Environment:
- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target
- `BRIDGE_SCHEMATIC_EDIT_PLAN_JSON`: ordered JSON array of edit steps
- `BRIDGE_SCHEMATIC_DECISIONS_JSON`: optional JSON array of design decisions and verification notes

What it does:
- reads the current schematic context before editing
- executes placement, wiring, labeling, and save steps in order
- reads the schematic context again after the edit batch
- returns step-level results plus a validation summary

### `scripts/server-project-flow.mjs`

Use this when you need the standard create/open/project-inspection flow.

### `scripts/server-command-runner.mjs`

Use this for arbitrary multi-step control-plane sequences against a connected session.

## Task templates

### Schematic context intake

1. Run `server-context-summary.mjs`.
2. Summarize the active document, project, selection state, and current schematic.
3. Name the next safe design action.
4. Ask for design intent only if the next step is ambiguous.

### Component selection

1. Run `server-part-selector.mjs` once the requirements and candidate list are available.
2. Restate the electrical and mechanical requirements.
3. Identify the surrounding function block in the schematic.
4. Compare realistic candidate parts.
5. Recommend one option and explain the tradeoffs.
6. Record the decision in BOM-style notes and verification checks.

### Schematic refinement

1. Run `server-schematic-refine.mjs` once the edit batch and design decisions are clear.
2. Read the current context.
3. Propose the smallest meaningful change.
4. Execute the change with dedicated bridge commands or `system.api_invoke`.
5. Re-read the document state and verify the result.

## Supported API surface

The bridge supports two layers:

1. Dedicated bridge commands for common actions.
2. `system.api_invoke` for direct access to the underlying JLCEDA API surface.

Read [references/api-surface.md](references/api-surface.md) for the family-by-family API map.
Read [references/task-sequences.md](references/task-sequences.md) for recommended call order.
Read [references/schematic-co-design.md](references/schematic-co-design.md) for the schematic-first collaboration pattern.
Read [references/component-selection.md](references/component-selection.md) for the part-selection workflow and output format.
Read [references/schematic-refinement.md](references/schematic-refinement.md) for the schematic edit-batch workflow and validation shape.

## Call strategy

- Read first, mutate second.
- Keep confirmation disabled for read-only inspection.
- Keep confirmation enabled for state-changing operations unless the user explicitly wants a test path.
- Prefer one function block at a time instead of changing the whole schematic at once.
- After every meaningful edit batch, re-read context before continuing.

## Notes

- For `system.api_invoke`, pass a dotted path like `dmt_Project.getCurrentProjectInfo` or `eda.dmt_Project.getCurrentProjectInfo`.
- For component selection, capture both circuit requirements and procurement constraints.
- For schematic work, prefer first understanding power, interfaces, control logic, and critical nets before editing primitives.
