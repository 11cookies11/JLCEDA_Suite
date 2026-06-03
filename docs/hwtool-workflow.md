# KiCad Agent Suite 工作流 / Workflow

## 概览 / Overview

```text
source/circuit-model.source.json
  -> resolve-symbols
  -> build-ir / validate-ir
  -> build/circuit-model.resolved.json
  -> export-kicad
  -> output/<topology>/
```

## 环境要求 / Requirements

- Windows
- KiCad 10.0 installed, or `KICAD_PYTHON_BIN` points to KiCad's bundled `python.exe`
- `hwtool.exe` available on PATH or via absolute path

## 第一步：创建项目 / Step 1: Create Project

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

## 第二步：编写源模型 / Step 2: Write Source Model

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

## 第三步：解析元件 / Step 3: Resolve Symbols

```powershell
hwtool agent resolve-symbols --project . --timeout 120
```

This step:

- reads each component's `selected_part.lcsc_id`
- downloads the real symbol and footprint from JLC/EasyEDA
- writes the resolved overlay to `build/circuit-model.resolved.json`
- updates `selected_part.symbol_ref` and `selected_part.kicad_footprint_hint`
- treats `selected_part.symbol_ref` as resolver-owned output, not a hand-authored source field

## 第四步：编译并验证 IR / Step 4: Build & Validate IR

```powershell
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
```

Input:

- `source/circuit-model.source.json`

Output:

- `build/ir.v1.json`

Validation failures usually include a code and a suggestion.

## 第五步：导出 KiCad / Step 5: Export KiCad

```powershell
hwtool agent export-kicad --project .
```

Generated files:

```text
output/<topology>/
├── <topology>.kicad_pro
├── <topology>.kicad_sch
├── <topology>.kicad_pcb
├── fp-lib-table
├── sym-lib-table
├── <topology>.erc.json
└── agent-report.json
```

## 常见问题 / Troubleshooting

### footprint not found

- Run `resolve-symbols` first
- Make sure `selected_part.lcsc_id` is correct
- Add `kicad_footprint_hint` when the automatic footprint mapping is ambiguous

### KiCad opens but the board is empty

- Confirm KiCad 10.0 is installed
- Confirm `KICAD_PYTHON_BIN` points to the correct Python
- Re-run `hwtool agent export-kicad`

### resolve-symbols times out

- Increase `--timeout`
- Verify network access to EasyEDA/JLC

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
