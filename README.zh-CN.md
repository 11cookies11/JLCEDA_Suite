# KiCad Agent Suite

面向 KiCad 的代理式硬件开发流水线。

语言：简体中文 | [English](README.md)

## 概览

`KiCad Agent Suite` 会把结构化硬件需求转换成可交付的 KiCad 产物。当前流程完全基于文件，不驱动 GUI 编辑器。它会生成中间设计模型、仿真输入、KiCad 原理图/工程文件，以及结构化验证摘要。

当前主链路如下：

```text
RequirementSpec
  -> CircuitModel
  -> Netlist
  -> SPICE Netlist
  -> ngspice feedback
  -> KiCadExecutionPlan
  -> .kicad_pro + .kicad_sch
  -> optional kicad-cli ERC
```

旧的 EasyEDA / JLCEDA 插件桥接已经移除。新的开发方向只面向 KiCad 工程生成，以及可复用的 KiCad / LCSC 资源。

## 架构

可以把这个仓库理解成一个小型硬件设计工厂，分成四层：

```text
kas
  -> pipeline / text-to-kicad / erc / validate-artifacts
  -> model -> netlist -> execution plan -> KiCad files
  -> kicad-cli / ngspice / JLC MCP adapters
  -> validation and summary reports
```

代码组织也围绕这个流程展开：

- `src/kicad_suite/`：可复用的流水线、适配器、CLI 和验证器逻辑
- `scripts/`：面向本地使用的薄封装和兼容入口
- `.where/`：生成的工程输出、摘要和规划记录

核心原则很简单：每个阶段都有明确输入、明确输出，以及进入下一阶段前的验证点。

## 当前能力

当前 KiCad 路径已经包含：

- 需求、CircuitModel、Netlist、SPICE Netlist、ngspice feedback、KiCad execution plan 的 JSON Schema
- Python 实现的需求到 KiCad 流水线
- 统一的 `kas` 命令入口
- 支持角色感知的原理图布局规则，以及可选 ELK 布局
- KiCad `.kicad_pro` 和 `.kicad_sch` 生成
- ngspice 导出、执行、解析和反馈产物
- 通过 `kicad-cli` 的可选 KiCad ERC
- 产物验证：摘要、ERC 输出、旧路径残留、计划一致性
- 一小组 ngspice 回归用例

## 命令

先安装 Node 依赖：

```bash
npm install
```

运行默认 KiCad 流水线：

```bash
npm run pipeline
```

底层本地入口是 `python scripts/kas.py ...`，Python 侧工作流现在统一到这一条命令面上。你也可以使用 `python -m kicad_suite ...`。

`src/kicad_suite/run_pipeline.py` 和 `src/kicad_suite/parts_pipeline.py` 仍保留为兼容壳，但它们只是过渡路径。新工作优先使用 `kas` 和新的模块布局。

包装器退场时间线：

- 现在：包装器继续保留，并转发到真实模块
- 下一步：当某个稳定模块路径已经覆盖旧入口时，先在文档和测试里标记 deprecated
- 之后：经过至少一个带回归覆盖的过渡窗口后，包装器可以收缩成最小的 shim

常用别名：

```bash
npm run kas -- --help
npm run text-to-kicad
npm run compile-plan
npm run write-project
npm run erc
npm run ngspice:regression
npm run validate:artifacts -- --summary .where/ci-nema23-run-summary.json
```

流水线既可以使用默认需求，也可以通过 `BRIDGE_REQUIREMENT_SPEC_JSON` 提供结构化需求：

```bash
BRIDGE_REQUIREMENT_SPEC_JSON='{"schema_version":"requirement-spec.v1", "...":"..."}' npm run text-to-kicad
```

PowerShell 示例：

```powershell
$env:KICAD_PROJECT_NAME = 'led_indicator'
$env:BRIDGE_REQUIREMENT_SPEC_JSON = '{ "schema_version": "requirement-spec.v1", "...": "..." }'
npm run text-to-kicad
```

## 输出

默认情况下，生成的 KiCad 产物会写入：

```text
.where/kicad-output/<project_name>/
```

典型输出包括：

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
- `kicad-erc.summary.json`
- `kicad-erc.json`
- `text-to-kicad-summary.json`
- 使用 `--json` 时，验证器会把 JSON 报告打印到 stdout

## 验证

当前可用的轻量检查：

```bash
npm run ngspice:regression
npm run validate:artifacts -- --summary .where/ci-nema23-run-summary.json
```

验证器可以检查 `kas pipeline` 或 `scripts/run_pipeline.py` 产出的 JSON 摘要。加上 `--strict` 可以把告警视为失败；加上 `--require-erc` 可以要求 ERC 必须启用或可用。

如果摘要里提供了 ERC 报告路径，验证器也会一并检查 ERC 结果。若本机没有 `kicad-cli`，它会记录这种状态，而不是直接阻断整条流水线。

流水线摘要还会包含顶层 `warnings`，表示结构化回退，例如 mock parts 解析、ERC 未启用、或后处理注册失败。这些告警表示流程已完成，但结果在进入生产前应该先复核。需要时使用 `--strict`，就能把这些告警直接判成失败。

如果某次改动会破坏稳定结构，就应当提升 `schema_version`，并在一段过渡期内继续兼容旧形状。实践上，`warnings` 表示“流程完成但带回退，需要复核”，而验证 `errors` 表示“硬失败”。

可选的 KiCad ERC：

```bash
npm run erc
```

设置 `KICAD_RUN_ERC=true` 时，完整流水线会在写出原理图后尝试执行 ERC。若没有安装 `kicad-cli`，runner 会返回结构化诊断，而不会阻断 KiCad 文件生成。

这些条件也会通过 summary 顶层 `warnings` 暴露出来，而不是悄悄吞掉。这样既保留兼容性，也让验证器和 agent 能看见回退路径。

## 摘要契约

运行摘要是流水线阶段、验证器和 agent 工作流之间的主要兼容面。

稳定字段：

- `files`
- `counts`
- `erc`
- `diagnostics`
- `postprocess`
- `warnings`

兼容字段：

- `output_files`
- `kicad_erc_summary`
- `kicad_erc_report`
- `execution_plan`
- `project_file`
- `schematic_file`

当摘要结构变化时，优先做增量更新，并尽量让验证器继续读取旧的稳定形式。把顶层 `warnings` 当成机器可读的回退信号，而不是可随手丢弃的日志文本。

## Schema 版本

主要 schema 版本已经在代码里集中管理，下面这些名字应视为 canonical：

- `requirement-spec.v1`
- `circuit-model.v1`
- `netlist.v1`
- `spice-netlist.v1`
- `ngspice-execution.v1`
- `ngspice-feedback.v1`
- `kicad-execution-plan.v1`
- `kicad-project-write-result.v1`
- `kicad-erc-result.v1`
- `text-to-kicad-summary.v1`
- `part-lock.v1`

如果要新增 schema 版本，先更新共享常量，再更新这份清单；若改动是破坏性的，还要补一份能覆盖旧形状和新形状的回归 fixture。

## 字段级契约

只有版本号还不够，每个主要 schema 也有一组最小字段约定。

- 运行摘要：`files`、`counts`、`erc`、`diagnostics`、`postprocess`、`warnings`
- ERC 结果：`enabled`、`attempted`、`success`、`finding_count`、`summary_file`、`output_file`、`error`、`warnings`
- 执行计划：`request_id`、`target`、`symbols`、`nets`、`diagnostics`
- part lock：`project`、`generated_at`、`parts`

兼容字段可以和稳定字段并存，但新代码应该优先依赖稳定字段。

## 兼容策略

仓库会保留兼容壳和兼容字段，但它们不是新自动化的首选入口。

- 稳定入口：`scripts/kas.py`、`src/kicad_suite/cli.py` 以及当前的子模块
- 过渡包装器：`src/kicad_suite/run_pipeline.py`、`src/kicad_suite/parts_pipeline.py` 和其他薄的旧壳
- 稳定摘要字段：`files`、`counts`、`erc`、`diagnostics`、`postprocess`、`warnings`
- 兼容摘要字段：`output_files`、直接文件路径字段，以及旧的嵌套形状
- 破坏性 schema 变更：提升 `schema_version`，在过渡期内保留旧形状可读，并补一份旧形状回归 fixture

兼容壳只负责迁移，不是新增行为的地方。如果某个改动必须经过 wrapper，优先把真实实现改到新模块里，再让旧壳转发过去。

## 在线 LCSC 搜索

parts resolver 集成了 `@jlcpcb/mcp`，用于在线 LCSC/JLCPCB 搜索和 KiCad 库安装。安装依赖后，下面这些命令可以直接使用，不需要 Claude Code 专用 MCP 配置：

```powershell
npm run jlc:list-tools
node scripts\jlc_mcp_bridge.mjs search --query "STM32G431" --source lcsc --limit 3 --in-stock
node scripts\jlc_mcp_bridge.mjs install --id C529355 --project-path .where\nema23-industrial-stepper-driver-v0.1 --include-3d
```

Python resolver 默认也会走这条桥接：

```powershell
python scripts\resolve_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json --output .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json
python scripts\install_jlc_mcp_parts.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --include-3d
python scripts\write_jlc_mcp_part_lock.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --install-report .where\nema23-industrial-stepper-driver-v0.1\jlc-mcp-install-report.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1
```

如果 JLC MCP 安装报告里发现符号损坏，应该先修复再接受锁定文件。例如 NEMA23 场景里的 LM393 比较器可以这样修：

```powershell
python scripts\fix_lm393_jlc_mcp_symbol.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --id C5252905
python scripts\install_jlc_mcp_parts.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --register-only
```

设置 `KICAD_DISABLE_JLC_MCP=1` 可以绕过 MCP 桥接。如果已经配置了凭据，resolver 也可以直接使用 LCSC 官方 OpenAPI：

```powershell
$env:LCSC_API_KEY = '<your-api-key>'
$env:LCSC_API_SECRET = '<your-api-secret>'
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
```

可选配置：

- `LCSC_OPENAPI_BASE_URL` 默认是 `https://ips.lcsc.com`
- `LCSC_OPENAPI_TIMEOUT_SEC` 默认是 `15.0`
- `LCSC_OPENAPI_CURRENCY` 默认是 `USD`
- `LCSC_MCP_BASE_URL` 仅用于旧的本地 `/api/search` 后端
- `JLC_MCP_COMMAND` 和 `JLC_MCP_ARGS` 可以覆盖桥接器如何启动 MCP server
- `JLC_MCP_DEBUG=1` 会在调试时打印 MCP server 的 stderr
- `JLC_MCP_INSTALL_TIMEOUT_SEC` 和 `JLC_MCP_INSTALL_RETRIES` 用于调节批量安装行为

如果没有 MCP 包、OpenAPI 凭据或本地 MCP HTTP server，resolver 会返回简短的结构化错误，而不会卡在 `localhost:3847`。

## 仓库结构

- `src/kicad_suite/`：可复用的流水线、适配器、CLI 和验证器代码
- `scripts/`：用于本地和兼容场景的薄 Python / Node 封装器
- `schemas/`：当前模型契约的 JSON Schema
- `docs/`：架构与工作流说明
- `skills/`：面向 agent 的工作流参考
- `.where/`：本地生成输出、日志和规划记录

## 开发方向

现在 KiCad 是唯一的 EDA 目标。后续优先改进：

- KiCad symbol / footprint 映射
- 原理图生成的确定性
- Netlist 正确性
- ngspice 覆盖率和反馈质量
- KiCad ERC 集成
- 统一命令入口
- 产物验证和可复现摘要
- 清晰的模型契约和回归用例

不要新增 EasyEDA / JLCEDA GUI 桥接功能。EasyEDA 相关引用只应保留在类似 `easyeda2kicad` 这样的库资源导入工具里。

## 许可证

见 `LICENSE`。
