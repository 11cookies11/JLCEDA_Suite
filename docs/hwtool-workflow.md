# KiCad Agent Suite Workflow

## Overview

```text
source/circuit-model.source.json
  -> workflow run full_build_v1 / lcsc_selection_v1 / repair_after_diagnose_v1
  -> build-ir / validate-ir
  -> build/circuit-model.resolved.json
  -> export-kicad
  -> output/<topology>/
```

## Requirements

- Windows
- KiCad 10.0 installed, or `KICAD_PYTHON_BIN` points to KiCad's bundled `python.exe`
- `hwtool.exe` available on PATH or via absolute path

## Step 1: Create Project

```powershell
hwtool agent create <project_dir> --project-id "my-project" --topology "my_project"
```

This creates the project skeleton, including:

- `source/`
- `build/`
- `docs/`
- `hardware/`

If `--include-circuit-model` is passed, the scaffold also creates:

- `source/circuit-model.source.json`
- `build/circuit-model.resolved.json`

## Step 2: Write Source Model

Source model path:

- `source/circuit-model.source.json`

Typical source fields:

```json
{
  "schema_version": "circuit-model.v1",
  "request_id": "fresh",
  "project_id": "my-project",
  "topology": "my_project",
  "components": [],
  "nets": [],
  "sheets": [],
  "pcb_layout": { "regions": {} },
  "calculations": [],
  "design_decisions": [],
  "risks": [],
  "constraints": []
}
```

Recommended source-only fields:

- `ref`
- `role`
- `value`
- `notes`
- `search_hints`

## Step 3: LCSC Selection Workflow

```powershell
hwtool agent workflow run --project . --template lcsc_selection_v1 --timeout 120
hwtool agent workflow status --project .
```

This workflow:

- uses workflow orchestration as the top-level control plane
- scans the source model for components without `selected_part.lcsc_id`
- reports those components as `needs_selection`
- writes agent selection tasks to `build/agent-tasks.json`
- lets the agent choose LCSC IDs through Model API
- reruns the same workflow after the source model changes

If `needs_selection` is non-empty, the agent should use `hwtool agent jlc search`
and `hwtool agent jlc info` to choose LCSC IDs, then write them through
`hwtool agent run set_selected_part`. Then rerun the same workflow.

`resolve-symbols` is a legacy helper for downloading already-selected parts, not
the workflow's selection engine.

## Step 4: Build and Validate IR

```powershell
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
```

Input:

- `source/circuit-model.source.json`

Output:

- `build/ir.v1.json`

Validation failures usually include a code and a suggestion.

## Step 5: Export KiCad

```powershell
hwtool agent export-kicad --project .
```

Generated files:

```text
output/<topology>/
  <topology>.kicad_pro
  <topology>.kicad_sch
  <topology>.kicad_pcb
  fp-lib-table
  sym-lib-table
  <topology>.erc.json
  agent-report.json
```

## Troubleshooting

### footprint not found

- Run `hwtool agent workflow run --project . --template lcsc_selection_v1 --timeout 120` first
- Make sure `selected_part.lcsc_id` is correct
- Add `kicad_footprint_hint` when the automatic footprint mapping is ambiguous

### KiCad opens but the board is empty

- Confirm KiCad 10.0 is installed
- Confirm `KICAD_PYTHON_BIN` points to the correct Python
- Re-run `hwtool agent export-kicad`

### resolve-symbols is slow or times out

- Treat `resolve-symbols` as an optional legacy helper, not a required workflow step
- Use `hwtool agent workflow run --project . --template lcsc_selection_v1 --timeout 120`
  to drive LCSC selection through the workflow stack
- Verify network access to EasyEDA/JLC only when you intentionally use the legacy helper

## PCB Verification

Use KiCad's bundled Python to confirm footprints were generated:

```powershell
& "D:/Program Files/KiCad/10.0/bin/python.exe" -c "
import pcbnew
board = pcbnew.LoadBoard('output/<topology>/<topology>.kicad_pcb')
print(f'Footprints: {len(board.GetFootprints())}')
print(f'Nets: {board.GetNetCount()}')
"
```

Footprint count should match the number of placed components.
