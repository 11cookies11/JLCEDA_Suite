# AGENTS.md

This file defines repository-specific instructions for coding agents (including Codex).

## Where Progress Contract

- Source file: `where.sourceFile` (default: `.where-agent-progress.md`)
- Format: **Markdown only** (JSON is not allowed)
- Encoding: UTF-8

Required structure:

```md
# Plan: <title>
- [ ] <task>
- [~] <task>
- [!] <task>
- [x] <task>
```

Status mapping:

- `[ ]` -> `todo`
- `[~]` -> `in_progress`
- `[!]` -> `blocked`
- `[x]` -> `done`

## Agent Behavior

- Keep one task per line.
- Update existing tasks when status changes; avoid duplicate tasks.
- Keep task titles short and actionable.
- For blocked tasks, include blocker reason in the title.
- Do not output JSON for progress data.
- Do not add unrelated long prose in the progress file.

## Hardware Toolchain Workflow

This repository is a hardware toolchain that converts `circuit-model.json` into Hardware IR and KiCad project output.

Agents must prefer `python -m kicad_suite.cli agent ...` commands over direct file edits.

### Mandatory Agent Workflow

**Step 1 — Understand state (always run first):**

```powershell
$env:PYTHONPATH="src"
python -m kicad_suite.cli agent status --project .
python -m kicad_suite.cli agent inspect --project .
python -m kicad_suite.cli agent explain --project .
```

**Step 2 — Build and validate IR:**

```powershell
python -m kicad_suite.cli agent build-ir --project .
python -m kicad_suite.cli agent validate-ir --project .
```

- If `validate-ir` returns errors, read the `diagnostics` array for specific error codes and suggested fixes.
- Use `agent run <operation>` with the suggested payload to fix each error.
- Do NOT proceed to `build-kicad` until `ok: true`.

**Step 3 — Rule check:**

```powershell
python -m kicad_suite.cli agent rule-check --project .
```

**Step 4 — Build KiCad plan and output:**

```powershell
python -m kicad_suite.cli agent build-kicad-plan --project .
python -m kicad_suite.cli agent build-kicad --project .
```

**Step 5 — Report:**

```powershell
python -m kicad_suite.cli agent report --project . --markdown
```

### Fixing Errors

Validation diagnostics include structured `code`, `location`, and `suggestion` fields:

```json
{
  "level": "error",
  "code": "DUPLICATE_NET_NAME",
  "location": "VCC",
  "message": "IR.nets: duplicate net name 'VCC'",
  "suggestion": {
    "action": "agent run",
    "operation": "merge_nets",
    "payload": {"source": "VCC"},
    "hint": "Merge duplicate net 'VCC' with the original."
  }
}
```

Apply the suggestion:

```powershell
python -m kicad_suite.cli agent run merge_nets --project . --payload-json '{"source":"VCC"}'
```

### Modifying Projects

Use `agent patch` to apply JSON patches to circuit-model.json:

```powershell
python -m kicad_suite.cli agent patch --project . --payload-json '{"components":[{"ref":"U1","role":"mcu"}]}'
```

Or use `agent run` for specific model API operations:

```powershell
python -m kicad_suite.cli agent run add_component --project . --payload-json '{"ref":"U1","role":"mcu","value":"ESP32-S3"}'
python -m kicad_suite.cli agent run add_net --project . --payload-json '{"name":"+3V3","kind":"power"}'
python -m kicad_suite.cli agent run connect_member --project . --payload-json '{"net":"+3V3","ref":"U1","pin":"1"}'
```

### Pin Management

```powershell
# List free GPIO pins on an MCU
python -m kicad_suite.cli agent pins free --project . --ref U1 --mcu-family ESP32-S3

# Assign a pin to a net
python -m kicad_suite.cli agent pins assign --project . --ref U1 --pin GPIO17 --net LCD_BL

# Check for pin conflicts
python -m kicad_suite.cli agent pins check --project .
```

### Self-Test

```powershell
python -m kicad_suite.cli agent self-test
python -m kicad_suite.cli agent self-test -k "test_agent"
```

### Doctor

```powershell
python -m kicad_suite.cli agent doctor --project .
```

## Source Of Truth

- `circuit-model.json` is the editable source model.
- `build/ir.v1.json` is generated — **do not edit**.
- `build/ir-validation.json` is generated — **do not edit**.
- `build/rule-check.json` is generated — **do not edit**.
- `build/kicad-execution-plan.v1.json` is generated — **do not edit**.
- `build/report.json` is generated for agents — **do not edit**.
- `build/report.md` is generated for humans — **do not edit**.
- `output/` contains generated KiCad artifacts — **do not edit**.

## Do Not

- Do not edit generated files under `build/` manually.
- Do not edit generated KiCad files directly unless explicitly requested.
- Prefer `python -m kicad_suite.cli agent run ...` over manually editing `circuit-model.json`.
- Do not bypass `validate-ir` and `rule-check` before `build-kicad`.
- Do not proceed to the next stage if the current stage has errors.

## Reference

- Detailed spec: `docs/AGENT_PROGRESS_SPEC.zh-CN.md`
