# 文本到 KiCad 管线

本文描述当前 KiCad 文件级 agent 的最小闭环。它不控制 KiCad GUI，而是生成 KiCad 工程文件，并可选调用 `kicad-cli` 做 ERC。

## 入口

```bash
npm run server:text-to-kicad
```

也可以使用目标路由入口：

```bash
EDA_TARGET=kicad npm run server:text-to-eda
```

可直接使用默认需求，也可以通过环境变量传入结构化需求：

```bash
BRIDGE_REQUIREMENT_SPEC_JSON='{"schema_version":"requirement-spec.v1", ...}' npm run server:text-to-kicad
```

Windows PowerShell 可先设置环境变量：

```powershell
$env:BRIDGE_REQUIREMENT_SPEC_JSON = '{ "schema_version": "requirement-spec.v1", ... }'
$env:KICAD_PROJECT_NAME = 'led_indicator'
npm run server:text-to-kicad
```

## 输出

默认输出目录：

```text
.where/kicad-output/<project_name>/
```

主要文件：

- `requirement-spec.json`
- `circuit-model.json`
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

- `target`：工程名、输出目录、工程文件、原理图文件。
- `symbols`：引用编号、角色、值、KiCad `lib_id`、封装、坐标和引脚网络。
- `nets`：网络名、类型和成员。
- `diagnostics`：占位符符号、缺失连接等诊断信息。

schema 文件位于：

```text
server/schemas/kicad-execution-plan.v1.json
```

## ERC

默认不运行 KiCad ERC。启用方式：

```powershell
$env:KICAD_RUN_ERC = 'true'
npm run server:text-to-kicad
```

或者单独运行：

```bash
npm run server:kicad:erc
```

环境变量：

- `KICAD_CLI_BIN`：指定 `kicad-cli` 路径。
- `KICAD_SCHEMATIC_FILE`：指定 `.kicad_sch` 文件。
- `KICAD_EXECUTION_PLAN_FILE`：从计划文件读取 schematic 路径。
- `KICAD_ERC_OUTPUT_FILE`：指定 ERC 报告输出路径。

如果本机没有 `kicad-cli`，runner 会输出结构化 `KICAD_CLI_NOT_FOUND` 诊断，不阻塞工程文件生成。

Windows 下会自动尝试发现：

```text
D:\Program Files\KiCad\*\bin\kicad-cli.exe
C:\Program Files\KiCad\*\bin\kicad-cli.exe
```

## 当前支持范围

- 常见两端器件：R / C / L / LED / Diode。
- 简单 Buck regulator 占位符：`AIAgent:Buck_Regulator`。
- net label / global label 连接。
- `.kicad_pro` 与 `.kicad_sch` 生成。
- ngspice 管线复用。
- 可选 KiCad schematic ERC。

## 限制

- 复杂 IC 仍使用占位符，需要后续接入真实 KiCad symbol library 映射。
- 第一版不生成 PCB。
- 第一版不调用 KiCad GUI。
- ERC 报告解析采用保守通用计数，后续应按 KiCad 版本固定报告结构。
