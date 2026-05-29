# KiCad Agent Suite 工作流程 / Workflow

## 概述 / Overview

```
                    ┌──────────────┐
                    │ 编写 model    │  AI agent 编写 circuit-model.json
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ resolve-     │  从 JLC/LCSC 下载符号+封装到 libraries/
                    │ symbols      │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ build-ir     │  circuit-model.json → build/ir.v1.json
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ validate-ir  │  结构化诊断 + 自动修复建议
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ export-kicad │  生成 .kicad_pro + .kicad_sch + .kicad_pcb + ERC
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ report       │  生成 build/report.json + build/report.md
                    └──────────────┘
```

## 环境要求 / Requirements

- **Windows** (toolchain 在 Windows 上开发和测试)
- **KiCad 10.0** 安装到默认路径，或设置 `KICAD_PYTHON_BIN` 指向 KiCad 自带的 python.exe
- **hwtool.exe** 位于 PATH 中或使用绝对路径

```powershell
# 如果 KiCad 安装在非默认路径，设置环境变量：
$env:KICAD_PYTHON_BIN = "D:/Program Files/KiCad/10.0/bin/python.exe"
```

## 第一步：创建项目 / Step 1: Create Project

```powershell
hwtool agent create <project_dir> --project-id "my-project" --topology "my_project"
```

这会在 `<project_dir>` 下创建 `circuit-model.json` 骨架。

## 第二步：编写 circuit-model.json / Step 2: Write Model

参考 schema：`schemas/circuit-model.v1.json`

### 核心结构

```json
{
  "schema_version": "circuit-model.v1",
  "request_id": "fresh",
  "project_id": "my-project",
  "topology": "my_project",
  "components": [...],
  "nets": [...],
  "sheets": [...],
  "pcb_layout": { "regions": {...} },
  "calculations": [],
  "design_decisions": [],
  "risks": [],
  "constraints": []
}
```

### 组件 / Components

```json
{
  "ref": "U1",
  "role": "mcu",
  "value": "ESP32-C3FH4",
  "package": "QFN-32",
  "selected_part": {
    "lcsc_id": "C2858491",
    "display_name": "ESP32-C3FH4"
  }
}
```

关键规则：
- `ref` — 唯一，按类型分（U=IC, C=电容, R=电阻, D=二极管/LED, J=连接器, SW=开关）
- `role` — 功能描述，影响符号/封装匹配。常见：`mcu`, `main_3v3_regulator`, `reset_button`, `power_led`, `usb_c_power_input`
- `package` — 通用封装名。`package` 会被合并到 `selected_part.package`（IR 编译时）
- `selected_part.lcsc_id` — LCSC 料号，用于 JLC 下载。通过 `hwtool agent jlc search` 查找

### 网络 / Nets

```json
{
  "name": "+3V3",
  "kind": "power",
  "members": ["U1.1", "U1.11", "U2.2", "C1.1"]
}
```

- `kind`: `"power"` | `"ground"` | `"signal"`
- `members`: `"REF.PIN"` 格式。PIN 编号对应 JLC 符号中的实际引脚号
- GND/AGND 自动分类为 ground；以 `+` 开头的自动分类为 power

### 原理图分页 / Sheets

```json
{
  "name": "power",
  "components": ["J1", "U2", "C6", "C7"],
  "nets": ["+5V", "+3V3", "GND"]
}
```

- 每个组件必须属于恰好一个 sheet
- sheet 的 nets 列出该页用到的网络

### PCB 布局 / PCB Layout

```json
{
  "pcb_layout": {
    "regions": {
      "power_input": { "x": 10, "y": 10, "components": ["J1"] },
      "mcu":         { "x": 10, "y": 100, "components": ["U1"] }
    }
  }
}
```

- 每个 region 定义一组组件在板上的排列位置
- 组件在 region 内从左到右自动排列，间距默认 18mm

## 第三步：下载元件库 / Step 3: Resolve Symbols

```powershell
hwtool agent resolve-symbols --project . --timeout 120
```

- 读取每个组件的 `selected_part.lcsc_id`
- 从 JLC/EasyEDA 下载符号（`.kicad_sym`）和封装（`.kicad_mod`）
- 自动更新 `selected_part.kicad_footprint_hint` 为 JLC 库中的实际封装名
- 首次运行耗时较长（~2 分钟），后续增量更新

## 第四步：编译并验证 IR / Step 4: Build & Validate IR

```powershell
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
```

如果验证失败，诊断信息包含：
```json
{
  "code": "DUPLICATE_PIN_NUMBER",
  "message": "IR.components[U1].pins: duplicate pin number '29'",
  "suggestion": {
    "action": "agent run",
    "operation": "update_pinmap",
    "payload": {"ref": "U1", "pin": "29"}
  }
}
```

## 第五步：生成 KiCad 项目 / Step 5: Export KiCad

```powershell
hwtool agent export-kicad --project .
```

生成文件：
```
output/<topology>/
├── <topology>.kicad_pro   # 项目文件
├── <topology>.kicad_sch   # 原理图（根页）
├── <topology>.kicad_pcb   # PCB 布局
├── 01_power.kicad_sch     # 分页原理图
├── 02_mcu.kicad_sch
├── 03_io.kicad_sch
├── fp-lib-table           # 封装库表
├── sym-lib-table          # 符号库表
├── <topology>.erc.json    # ERC 结果
└── agent-report.json      # Agent 可读报告
```

## 常见问题 / Troubleshooting

### "footprint not found" 警告

所有封装都报告找不到。可能原因：
- 没运行 `resolve-symbols` → 先跑一次下载
- `selected_part.lcsc_id` 写错了 → 用 `hwtool agent jlc search` 查找正确料号
- 封装名不匹配 → 在 model 中加 `kicad_footprint_hint` 手动指定

### PCB 打开后一片空白

- 确认 KiCad 10.0 已安装
- 确认 `KICAD_PYTHON_BIN` 指向 KiCad 的 python.exe
- 重新运行 `hwtool agent export-kicad`

### IR 验证失败

- 读 `build/ir-validation.json` 的 `diagnostics` 数组
- 每条诊断含 `code` + `suggestion`，按建议修复

### resolve-symbols 超时

- 增加 `--timeout 300`
- 检查网络是否能访问 easyeda.com

## 验证 PCB / Verify PCB

用 KiCad 自带 Python 验证 PCB 是否所有封装都加载成功：

```powershell
& "D:/Program Files/KiCad/10.0/bin/python.exe" -c "
import pcbnew
board = pcbnew.LoadBoard('output/<topology>/<topology>.kicad_pcb')
print(f'Footprints: {len(board.GetFootprints())}')
print(f'Nets: {board.GetNetCount()}')
"
```

封装数应等于 component 数，nets 数应匹配 model 中定义的数量。
