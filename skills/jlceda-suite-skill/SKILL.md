---
name: jlceda-suite-skill
description: Drive a connected JLCEDA Suite session through the suite server control plane, inspect the current hardware design context, and assist with component selection, schematic refinement, and PCB assistance work.
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
- summarize PCB hygiene, placement risks, and follow-up layout tasks

## Default workflow

1. Confirm the JLCEDA Suite Server is running and the plugin session is connected.
2. Read `/sessions` and pick the target `clientId`.
3. Run `scripts/server-context-summary.mjs` to collect the current design context.
4. Use the summary to decide which mode you are in: `inspect`, `select`, `design`, `text2schematic`, `pcb`, or `export`.
5. Prefer dedicated bridge commands for common project, schematic, PCB, and system operations.
6. Use `system.api_invoke` only when the official JLCEDA API exists but has not been wrapped yet.
7. Keep the same connected session for the whole task chain so the design context stays coherent.
8. If the user's requirement is incomplete, ambiguous, or too short to support a stable design decision, pause and perform requirement clarification before generating SCD, CircuitModel, or ExecutionPlan.

## Reference map

Use the smallest relevant set of references for the current mode:

- `references/task-sequences.md` for shortest safe bridge call sequences
- `references/schematic-co-design.md` for live schematic collaboration
- `references/component-selection.md` for part choice and candidate comparison
- `references/text-to-schematic.md` for requirement-to-schematic workflows
- `references/schematic-construction-description.md` for strict SCD structure and parsing
- `references/requirement-clarification.md` for incomplete or unstable requirements
- `references/strap-and-bias-rules.md` for mode pins, straps, pull networks, and defaults
- `references/netlist-guidelines.md` for connection truth and simulation-ready structure
- `references/simulation-guidelines.md` for ngspice-oriented validation flow
- `references/decision-log-template.md` for recording engineering decisions and assumptions
- `references/schematic-refinement.md` for small schematic edit batches
- `references/pcb-assist.md` for board review and layout follow-up
- `references/api-surface.md` for official API discovery and fallback calls

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

### 4. PCB

Use this when the user wants to continue from schematic intent into board placement or layout review.

Goal:
- read the current PCB, board summary, hygiene state, and ratline status
- identify the highest-risk placement or routing problem
- produce layout advice and the next short PCB task list

Expected output:
- board and PCB summary
- hygiene issue summary
- placement advice
- next PCB tasks

### 5. Text2Schematic

Use this when the user gives text requirements and wants a structured model plus executable schematic plan.

Goal:
- convert requirement text into a typed requirement object
- clarify incomplete requirements before synthesis when the input does not yet define enough electrical intent
- normalize the theory circuit into a strict Schematic Construction Description (SCD) before model synthesis
- synthesize a circuit model with decisions and risks
- compile an execution plan for JLCEDA
- optionally execute the plan and capture structured failure feedback

Expected output:
- requirement clarification summary when the input is underspecified
- requirement model
- SCD text with block structure, explicit nets, explicit pins, and review checks
- circuit model
- execution plan
- execution summary and fallback events

Requirement clarification gate:

- If the user gives only a short seed request, first restate what is known and what is missing.
- If the requirement intent is still moving, ask whether the requirement is already finalized before proceeding.
- Ask for the minimum electrical intent needed to continue, such as input source, output voltage, current, interface, package, or constraints.
- Do not generate SCD or CircuitModel until the key design intent is confirmed or a clearly stated assumption set is accepted.
- When assumptions are used, label them explicitly in the clarification summary and keep them visible in later outputs.

Standard clarification prompt:

- "需求现在已经定稿了吗？如果还没有，我先帮你把需求补完整，再进入原理图构建。"

Reference priorities for this mode:

- `references/requirement-clarification.md`
- `references/strap-and-bias-rules.md`
- `references/decision-log-template.md`
- `references/schematic-construction-description.md`
- `references/text-to-schematic.md`

### 6. Export

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
- candidate parts should carry pin metadata when available, especially for connectors, TVS, and other schematic symbols that must be wired immediately
- `BRIDGE_SELECTION_CANDIDATES_JSON`: optional JSON array of candidate parts to compare; each candidate should include pin information when available

What it does:
- reads the current JLCEDA schematic context
- scores candidate parts against the supplied requirements and treats verified pin geometry as a hard selection gate
- returns a recommendation, BOM note, verification checklist, and next schematic actions
- excludes candidates without usable pin information from the preferred path
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

### `scripts/server-pcb-assist.mjs`

Use this when the next step is PCB placement review, hygiene review, or routing preparation.

Environment:
- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target
- `BRIDGE_PCB_ASSIST_OPTIONS_JSON`: optional JSON with hygiene thresholds, focus areas, and board goals

What it does:
- reads the current schematic and PCB context
- requests `pcb.get_board_summary` and `pcb.get_current_pcb_info`
- requests `pcb.inspect_layout_hygiene` and `pcb.get_calculating_ratline_status`
- prints one structured JSON payload with PCB layout advice and next tasks

### `scripts/server-text-to-schematic.mjs` (wrapper)

This wrapper invokes the repository pipeline entry:
- `python3 scripts/server_text_to_schematic.py`

Use this for the end-to-end pipeline:
- `RequirementSpec -> CircuitModel -> ExecutionPlan`
- optional execution against connected JLCEDA session

Environment:
- `BRIDGE_REQUIREMENT_SPEC_JSON`: JSON requirement payload
- `BRIDGE_COMPONENT_CATALOG_JSON`: JSON role->candidate part catalog, with library/symbol ids when available
- `BRIDGE_AUTO_SEARCH_LIB`: `true/false`, auto search library candidates when the role catalog is missing (default `true`)
- `BRIDGE_ENABLE_SAFE_WIRING`: `true/false`, generate wires only when pin set mapping is valid (default `true`)
- `BRIDGE_EXECUTE_PLAN`: `true/false`, execute plan when true
- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional target client id
- `BRIDGE_PIPELINE_OUTPUT_DIR`: optional output directory, default `.where/pipeline-output`

What it does:
- validates and normalizes requirement input
- synthesizes a buck-oriented circuit model with calculations and design decisions
- compiles executable operations with fallback rules
- optionally executes operations and records structured feedback
- writes requirement/model/plan/summary JSON artifacts

### `scripts/server-project-flow.mjs`

Use this when you need the standard create/open/project-inspection flow.

### `scripts/server-command-runner.mjs`

Use this for arbitrary multi-step control-plane sequences against a connected session, or for reusable workflow templates such as `inspect`, `select`, `design`, `pcb`, and `export`.

Environment:
- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target
- `BRIDGE_RUNNER_TEMPLATE`: optional template name: `inspect`, `select`, `design`, `pcb`, or `export`
- `BRIDGE_RUNNER_TEMPLATE_INPUT_JSON`: optional JSON payload for template thresholds or export settings
- `BRIDGE_COMMANDS_JSON`: inline custom command plan when not using a template
- `BRIDGE_COMMANDS_FILE`: JSON file path for a custom command plan when not using a template

What it does:
- resolves either a template plan or a custom plan
- runs the command sequence against the connected JLCEDA session
- prints one structured JSON payload with command-by-command results and a short execution summary

## Task templates

The command runner can now be used as a reusable template executor when the dedicated scripts are too specific or when you want one normalized result shape across multiple workflow modes.

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

### PCB assistance

1. Run `server-pcb-assist.mjs` after the schematic block is clear enough to carry forward into layout.
2. Read board summary, current PCB info, and hygiene status.
3. Identify the highest-value placement or routing issue.
4. Produce layout advice for the active block.
5. Keep the next PCB tasks short and verifiable.

### Command runner templates

1. Use `server-command-runner.mjs` with `BRIDGE_RUNNER_TEMPLATE` when you want a standard sequence without writing a custom request list.
2. Pick `inspect`, `select`, `design`, `pcb`, or `export` based on the current collaboration phase.
3. Pass `BRIDGE_RUNNER_TEMPLATE_INPUT_JSON` when you need inspection thresholds or export settings.
4. Review the structured summary before deciding whether to switch to a dedicated workflow script.

## Supported API surface

The bridge supports two layers:

1. Dedicated bridge commands for common actions.
2. `system.api_invoke` for direct access to the underlying JLCEDA API surface.

Read [references/api-surface.md](references/api-surface.md) for the family-by-family API map.
Read [references/task-sequences.md](references/task-sequences.md) for recommended call order.
Read [references/schematic-co-design.md](references/schematic-co-design.md) for the schematic-first collaboration pattern.
Read [references/component-selection.md](references/component-selection.md) for the part-selection workflow and output format.
Read [references/schematic-refinement.md](references/schematic-refinement.md) for the schematic edit-batch workflow and validation shape.
Read [references/pcb-assist.md](references/pcb-assist.md) for the PCB follow-up workflow and layout guidance shape.
Read [references/schematic-construction-description.md](references/schematic-construction-description.md) for the strict SCD format and validation rules.
Read [references/text-to-schematic.md](references/text-to-schematic.md) for the model-driven text-to-schematic pipeline.
Read [references/requirement-clarification.md](references/requirement-clarification.md) for the requirement gate and missing-intent workflow.
Read [references/strap-and-bias-rules.md](references/strap-and-bias-rules.md) for strap, bias, and default-connection rules.
Read [references/netlist-guidelines.md](references/netlist-guidelines.md) for the connection-truth layer and simulation-ready structure.
Read [references/simulation-guidelines.md](references/simulation-guidelines.md) for the ngspice-oriented validation flow.
Read [references/decision-log-template.md](references/decision-log-template.md) for the engineering decision record format.

## Call strategy

- Read first, mutate second.
- Keep confirmation disabled for read-only inspection.
- Keep confirmation enabled for state-changing operations unless the user explicitly wants a test path.
- Prefer one function block at a time instead of changing the whole schematic at once.
- After every meaningful edit batch, re-read context before continuing.
- When the user asks for theory schematic generation, produce SCD first, validate it, and only then synthesize `CircuitModel` or a drawing artifact.

## Notes

- For `system.api_invoke`, pass a dotted path like `dmt_Project.getCurrentProjectInfo` or `eda.dmt_Project.getCurrentProjectInfo`.
- For component selection, capture both circuit requirements and procurement constraints.
- For schematic work, prefer first understanding power, interfaces, control logic, and critical nets before editing primitives.
