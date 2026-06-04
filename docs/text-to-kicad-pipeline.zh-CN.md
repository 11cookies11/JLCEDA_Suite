# 文本到 KiCad 流水线

本文描述当前 KiCad-only 主线。流水线不控制 KiCad GUI，而是生成 KiCad 工程文件，并可选调用 `kicad-cli` 做 ERC。

## 入口

```bash
npm run text-to-kicad
```

兼容别名：

```bash
npm run pipeline
npm run server:text-to-kicad
EDA_TARGET=kicad npm run server:text-to-eda
```

可以使用默认需求，也可以通过环境变量传入结构化需求：

```bash
BRIDGE_REQUIREMENT_SPEC_JSON='{"schema_version":"requirement-spec.v1", "...":"..."}' npm run text-to-kicad
```

PowerShell：

```powershell
$env:BRIDGE_REQUIREMENT_SPEC_JSON = '{ "schema_version": "requirement-spec.v1", "...": "..." }'
$env:KICAD_PROJECT_NAME = 'led_indicator'
npm run text-to-kicad
```

## 数据链路

```text
RequirementSpec
  -> CircuitModel
  -> Netlist
  -> SPICE Netlist
  -> ngspice feedback
  -> KiCadExecutionPlan
  -> KiCad project files
```

## 输出

默认输出目录：

```text
.where/kicad-output/<project_name>/
```

主要文件：

- `requirement-spec.json`
- `source/circuit-model.source.json`
- `netlist.json`
- `spice-netlist.cir`
- `ngspice-execution.json`
- `ngspice-feedback.json`
- `kicad-execution-plan.json`
- `<project_name>.kicad_pro`
- `<project_name>.kicad_sch`
- `kicad-write-summary.json`
- `text-to-kicad-summary.json`

## KiCad 执行计划

`kicad-execution-plan.v1` 是 KiCad 后端的中间层，定义：

- `target`：工程名、输出目录、工程文件、原理图文件
- `symbols`：引用编号、角色、值、KiCad `lib_id`、封装、坐标和引脚网络
- `nets`：网络名、类型和成员
- `diagnostics`：占位符符号、缺失连接等诊断信息

schema 文件：

```text
schemas/kicad-execution-plan.v1.json
```

## ERC

默认不运行 KiCad ERC。启用方式：

```bash
KICAD_RUN_ERC=true npm run text-to-kicad
```

或单独运行：

```bash
npm run erc
```

可用环境变量：

- `KICAD_CLI_BIN`：指定 `kicad-cli` 路径
- `KICAD_SCHEMATIC_FILE`：指定 `.kicad_sch` 文件
- `KICAD_EXECUTION_PLAN_FILE`：从执行计划读取 schematic 路径
- `KICAD_ERC_OUTPUT_FILE`：指定 ERC 报告输出路径

如果本机没有 `kicad-cli`，runner 会输出结构化 `KICAD_CLI_NOT_FOUND` 诊断，不阻塞工程文件生成。

Windows 下会自动尝试发现：

```text
D:\Program Files\KiCad\*\bin\kicad-cli.exe
C:\Program Files\KiCad\*\bin\kicad-cli.exe
```

## 当前支持范围

- 常见两端器件：R / C / L / LED / Diode
- 简单 Buck regulator 占位符：`AIAgent:Buck_Regulator`
- 部分 MCU、连接器、LDO 的 KiCad symbol 映射
- net label / global label 连接
- `.kicad_pro` 与 `.kicad_sch` 生成
- ngspice 流水线复用
- 可选 KiCad schematic ERC

## 限制

- 复杂 IC 仍可能使用占位符，需要继续补真实 KiCad symbol library 映射
- 当前重点是原理图生成，不生成 PCB
- 当前不调用 KiCad GUI
- ERC 报告解析仍偏保守，后续应按 KiCad 版本固定报告结构
