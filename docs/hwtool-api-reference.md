# hwtool API Reference

`hwtool agent` is the stable command surface for AI agents and release users.

All project commands operate on a project directory with this layout:

```text
project/
  source/circuit-model.source.json
  build/
  libraries/
  output/
```

Generated files in `build/` and `output/` should not be edited manually.

## Manifest

### `agent manifest`

```powershell
hwtool agent manifest
```

Returns the available agent commands and standard project file paths.

Important manifest fields:

- `commands`: command names and descriptions.
- `project_files.model_source`: `source/circuit-model.source.json`.
- `project_files.model_resolved`: `build/circuit-model.resolved.json`.
- `project_files.ir`: `build/ir.v1.json`.
- `project_files.ir_validation`: `build/ir-validation.json`.
- `project_files.agent_report`: `build/report.json`.
- `project_files.human_report`: `build/report.md`.

The manifest now also includes `assets`, which covers GUI-facing KiCad asset
checks and 3D model path normalization.

## Project Lifecycle

### `agent create`

```powershell
hwtool agent create <project_dir> `
  --project-id <id> `
  --topology <name> `
  [--title <title>] `
  [--source-model <path>] `
  [--overwrite] `
  [--export-ir]
```

Creates a hardware project skeleton.

As part of creation, the project model now runs a design-intent check by
default and records any missing baseline intent or placeholder markers in the
returned diagnostics and project state. This keeps new projects from silently
starting out with an empty intent trail.

Primary output:

- `source/circuit-model.source.json`

### `agent status`

```powershell
hwtool agent status --project <dir>
```

Returns lifecycle state and stale/build flags.

Typical statuses:

- `INIT`
- `DIRTY`
- `VALID`
- `INVALID`
- `BUILT`
- `BUILD_FAILED`
- `STALE`

### `agent inspect`

```powershell
hwtool agent inspect --project <dir> [--model <path>]
```

Returns structured project, source model, build, and summary information.

Use this before editing so an agent does not work from stale assumptions.

### `agent explain`

```powershell
hwtool agent explain --project <dir>
```

Returns a compact human-readable project summary.

### `agent diagnose`

```powershell
hwtool agent diagnose --project <dir> [--model <path>] [--output <path>]
```

Returns unified structured diagnostics for agent repair loops.

Top-level fields:

- `schema_version`: currently `agent-diagnostics.v1`.
- `ok`: whether there are no `must_fix` diagnostics.
- `stage`: `diagnose`.
- `project`: project id and name.
- `status`: current project lifecycle status.
- `counts`: counts for `must_fix`, `library_noise`, and `review_required`.
- `diagnostics.must_fix`: blockers that should be repaired before continuing.
- `diagnostics.library_noise`: likely imported symbol, footprint, or ERC metadata noise.
- `diagnostics.review_required`: stale state or issues requiring judgement.
- `diagnostics.suggested_actions`: commands or actions the agent can try next.
- `sources`: source state used to build the diagnosis.

Interpretation:

- Fix `must_fix` before export or release.
- Treat `library_noise` as evidence, not a reason to blindly change the source model.
- If `PROJECT_STATE_STALE` appears, rerun `build-ir` and `validate-ir`.

Readiness checks now also include a design-intent completeness gate. The gate
looks for baseline `design_decisions`, `risks`, and `constraints`, then checks
whether active domains such as power, RF, audio, storage, UI, security, and
debugging have at least some explicit evidence in those sections. The model
API also exposes a dedicated `validate_intent` operation for this gate.

### `agent assets validate`

```powershell
hwtool agent assets validate --project <dir> [--normalize]
```

Validates GUI-facing KiCad assets for a project. This checks:

- symbol libraries are sanitized
- `fp-lib-table` is present and registers `JLC-MCP`
- footprint and PCB 3D model references resolve
- model paths stay under project-local `${KIPRJMOD}/...` references

When `--normalize` is set, the command rewrites 3D model references before
checking them.

### `agent assets normalize`

```powershell
hwtool agent assets normalize --project <dir>
```

Normalizes footprint and PCB 3D model paths to project-local `${KIPRJMOD}/...`
references and reports the resulting validation status.

### `agent workflow run`

```powershell
hwtool agent workflow run --project <dir> --template lcsc_selection_v1 [--timeout 120]
```

Runs an agent-assisted workflow template. The first implemented template is
`lcsc_selection_v1`. Available initial templates:

- `full_build_v1`: main workflow; emits route tasks for agent-confirmed child workflows.
- `lcsc_selection_v1`: scans for missing `selected_part.lcsc_id` values and emits LCSC selection tasks.
- `repair_after_diagnose_v1`: emits repair/review tasks from diagnose findings.
- `unknown_task_v1`: fallback review workflow for unknown or unsupported conditions.

Possible statuses:

- `completed`: workflow target is satisfied.
- `waiting_for_agent`: read `build/agent-tasks.json`, use `jlc search` / `jlc info`,
  write source through `agent run set_selected_part`, then rerun the same workflow.
- `failed`: deterministic workflow step failed.

### `agent workflow status`

```powershell
hwtool agent workflow status --project <dir>
```

Returns the current workflow/task summary for agents. `agent status` also embeds
this workflow summary.

### `agent workflow propose`

```powershell
hwtool agent workflow propose --project <dir> --file <agent_proposed_workflow.json>
```

Validates and registers an agent-proposed workflow plan for cases not covered by
built-in templates. The first version validates schema and whitelisted step
types, saves `build/agent-proposed-workflow.json`, and marks the active stack
frame as `waiting_for_agent_execution`. It does not execute arbitrary steps.

### `agent workflow choose-route`

```powershell
hwtool agent workflow choose-route --project <dir> --workflow <template-id> [--reason <text>]
```

Replaces the active `__route_pending__` stack frame with the workflow selected
by the agent. Use this after a `choose_workflow_route_v1` task.

### `agent doctor`

```powershell
hwtool agent doctor --project <dir> [--model <path>]
```

Checks the local environment and project layout.

### `agent history`

```powershell
hwtool agent history --project <dir> [-n <limit>]
```

Returns recent project operations from `logs/operations.jsonl`.

### `agent self-test`

```powershell
hwtool agent self-test [--filter <pytest-expr>]
```

Runs the test suite and returns structured results.

## Build Pipeline

### `agent resolve-symbols`

```powershell
hwtool agent resolve-symbols --project <dir> [--model <path>] `
  [--timeout 120]
```

Legacy helper that downloads JLC/EasyEDA symbols and footprints based on
`selected_part.lcsc_id`. Components without `selected_part.lcsc_id` are reported
as `needs_selection`; the agent should select an LCSC ID with `jlc search` /
`jlc info` and write it back with `agent run set_selected_part`.

Outputs:

- project-local libraries under `libraries/`
- resolved overlay at `build/circuit-model.resolved.json`
- resolver-owned fields such as `selected_part.symbol_ref`
- resolver-owned fields such as `selected_part.kicad_footprint_hint`

Use this only when you explicitly want the legacy downloader. It is not required
as a workflow step.

## GUI Asset Workflow

The postprocess layer includes a dedicated asset workflow for KiCad GUI-facing
files. Use it after footprint/library generation or when 3D viewer paths look
stale:

```powershell
hwtool agent assets validate --project <dir>
hwtool agent assets normalize --project <dir>
```

Configuration:

- `KICAD_AGENT_3DMODEL_DIRS`: semicolon, comma, or newline separated list of
  extra 3D model search roots.
- `KICAD_3DMODEL_DIRS`: compatible alias for the same setting.
- `KICAD_AGENT_3DMODEL_DIR` / `KICAD_3DMODEL_DIR`: single-directory forms.

If no override is set, the resolver falls back to the common KiCad system 3D
model directories shipped with supported installs.

### `agent build-ir`

```powershell
hwtool agent build-ir --project <dir> [--model <path>] [--output <path>]
```

Compiles the source/resolved model into Hardware IR.

Default output:

- `build/ir.v1.json`

### `agent validate-ir`

```powershell
hwtool agent validate-ir --project <dir> [--model <path>] [--output <path>]
```

Builds and validates Hardware IR.

Default output:

- `build/ir-validation.json`

If validation fails, read `diagnostics[]`. Diagnostics usually include:

- `code`
- `location`
- `message`
- `suggestion`

### `agent rule-check`

```powershell
hwtool agent rule-check --project <dir> [--model <path>] `
  [--payload-json <json>] [--payload-file <path>] `
  [--dry-run] [--validate-only] [--no-commit]
```

Runs readiness checks for the current project model.

### `agent build-kicad-plan`

```powershell
hwtool agent build-kicad-plan --project <dir> [--model <path>] `
  [--payload-json <json>] [--payload-file <path>]
```

Compiles the KiCad execution plan from validated IR.

### `agent export-kicad`

```powershell
hwtool agent export-kicad --project <dir> `
  [--model <path>] `
  [--output-dir <path>] `
  [--project-name <name>]
```

Runs the KiCad export pipeline.

Outputs:

- `output/<topology>/<topology>.kicad_pro`
- `output/<topology>/<topology>.kicad_sch`
- `output/<topology>/<topology>.kicad_pcb`
- `output/<topology>/<topology>.erc.json`
- `output/<topology>/<topology>.erc.classification.json`
- `output/<topology>/agent-report.json`

Do not run this if `validate-ir` reports errors.

### `agent build-kicad`

```powershell
hwtool agent build-kicad --project <dir> [--model <path>]
```

Compatibility alias for KiCad project generation. Prefer `export-kicad` in new docs and agent workflows.

### `agent report`

```powershell
hwtool agent report --project <dir> `
  [--output-json <path>] [--output-md <path>] [--markdown]
```

Generates machine-readable and human-readable reports.

Default outputs:

- `build/report.json`
- `build/report.md`

## JLC / LCSC Commands

### `agent jlc search`

```powershell
hwtool agent jlc search <query> [-n <limit>]
```

Searches LCSC/JLC parts.

Typical result fields:

- `lcsc_id`
- `name`
- `package`
- `stock`
- `price`
- `is_basic`

### `agent jlc info`

```powershell
hwtool agent jlc info <lcsc_id>
```

Returns part metadata without downloading assets.

### `agent jlc download`

```powershell
hwtool agent jlc download --project <dir> --lcsc-id <id>
hwtool agent jlc download --project <dir> --query <keyword> [--auto] [-n <limit>]
```

Downloads one component's symbol and footprint into project-local libraries.

## Pin Management

### `agent pins free`

```powershell
hwtool agent pins free --project <dir> --ref <ref> [--mcu-family <family>] [--model <path>]
```

Lists available pins for a component, usually an MCU.

### `agent pins assign`

```powershell
hwtool agent pins assign --project <dir> `
  --ref <ref> --pin <pin> --net <net> `
  [--role <role>]
```

Assigns a component pin to a net through the model API.

### `agent pins check`

```powershell
hwtool agent pins check --project <dir> [--mcu-family <family>] [--model <path>]
```

Checks pin conflicts and pin assignment consistency.

## Direct Model Manipulation

### `agent patch`

```powershell
hwtool agent patch --project <dir> `
  [--model <path>] `
  --payload-json '<json-patch>'
```

Applies a JSON patch to `source/circuit-model.source.json`.

Use this for precise automated edits.

### `agent run`

```powershell
hwtool agent run <operation> --project <dir> `
  [--model <path>] `
  --payload-json '<json>'
```

Runs one DSL Model API operation.

Common operations:

- `load_model`
- `save_model`
- `patch_model`
- `validate_model`
- `validate_schema`
- `validate_references`
- `validate_connectivity`
- `validate_ir`
- `add_component`
- `update_component`
- `remove_component`
- `add_net`
- `update_net`
- `connect_member`
- `connect_members`
- `disconnect_member`
- `rename_net`
- `set_pinmap`
- `update_pinmap`
- `connect_pin_to_net`
- `add_sheet`
- `update_sheet`
- `add_calculation`
- `add_design_decision`
- `add_risk`
- `add_constraint`
- `select_part`
- `set_selected_part`
- `update_selected_part`
- `replace_selected_part`
- `validate_readiness`
- `export_kicad_project`
- `run_erc`

For the complete operation contract, inspect the schema files:

- `schemas/dsl-api-request.v1.json`
- `schemas/dsl-api-result.v1.json`

## Environment Variables

Common variables:

- `KICAD_PYTHON_BIN`: KiCad bundled Python path.
- `KICAD_CLI`: `kicad-cli` path.
- `KICAD_OUTPUT_DIR`: override output root.
- `KICAD_PROJECT_NAME`: override KiCad project name.
- `KICAD_SOURCE_PROJECT_DIR`: source project root for library sync.
- `KICAD_GENERATE_PCB`: whether PCB generation is enabled.
- `KICAD_FOOTPRINT_DIR`: extra footprint root.
- `KICAD_EXTRA_FOOTPRINT_DIR`: additional footprint roots.
- `KICAD_LAYOUT_PROFILES_FILE`: layout profile config.

## Recommended Agent Loop

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent patch --project . --payload-json '{...}'
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent diagnose --project .
```

Stop and repair if:

- `validate-ir` reports errors.
- `diagnose.counts.must_fix` is greater than zero.
- `pins check` reports conflicts for assigned MCU pins.

## Do Not

- Do not hand-edit `build/` or `output/`.
- Do not use root-level `circuit-model.json` for new projects.
- Do not use `legacy-*` output names for new projects.
- Do not skip `validate-ir` before `export-kicad`.
- Do not guess LCSC IDs.
