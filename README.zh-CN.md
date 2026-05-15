# KiCad Agent Suite

面向 KiCad 的代理协作硬件开发流水线。

语言：简体中文 | [English](README.md)

## 概览

`KiCad Agent Suite` 的目标，是把结构化硬件需求转换成可交付的 KiCad 产物。当前流程完全基于文件，不驱动 GUI 编辑器，而是生成中间设计模型、仿真输入、KiCad 原理图/工程文件，以及结构化的验证摘要。

当前主链路是：

```text
RequirementSpec
  -> CircuitModel
  -> Netlist
  -> SPICE Netlist
  -> ngspice feedback
  -> KiCadExecutionPlan
  -> .kicad_pro + .kicad_sch
  -> 可选 kicad-cli ERC
```

旧的 EasyEDA/JLCEDA 插件桥接已经移除。新的开发方向只面向 KiCad 工程生成，以及可复用的 KiCad/LCSC 资源。

## 架构

可以把这个仓库理解成一个小型硬件设计工厂，分成四层：

```text
kas
  -> pipeline / text-to-kicad / erc / validate-artifacts
  -> model -> netlist -> execution plan -> KiCad files
  -> kicad-cli / ngspice / JLC MCP adapters
  -> validation and summary reports
```

代码组织也按这个流程来：

- `src/kicad_suite/`：可复用的流水线、适配器和验证器逻辑
- `scripts/`：本地使用和兼容性的薄封装命令
- `.where/`：生成产物、摘要和规划记录

核心原则很简单：每一步都有清晰输入、清晰输出，以及进入下一步之前的验证点。

## 当前能力

KiCad 路径目前包括：

- 需求、CircuitModel、Netlist、SPICE Netlist、ngspice feedback、KiCad execution plan 的 JSON Schema
- Python 实现的需求到 KiCad 流水线
- 统一的 `kas` 命令入口
- 支持角色感知的原理图布局规则，并可选 ELK layout
- KiCad `.kicad_pro` 和 `.kicad_sch` 生成
- ngspice 导出、执行、解析和反馈产物
- 通过 `kicad-cli` 的可选 KiCad ERC
- 产物验证：摘要、ERC 输出、旧路径残留、计划一致性
- 一个小型 ngspice 回归用例集

## 命令

先安装 Node 依赖：

```bash
npm install
```

运行默认 KiCad 流水线：

```bash
npm run pipeline
```

底层本地入口是 `python scripts/kas.py ...`，这样 Python 侧的工作流就收束到一条命令线上了。你也可以直接用 `python -m kicad_suite ...`。

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

流水线可以使用默认需求，也可以通过 `BRIDGE_REQUIREMENT_SPEC_JSON` 传入结构化需求：

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

默认生成产物写在：

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
- 当使用 `--json` 时，验证器会把 JSON 报告打印到 stdout

## 验证

运行当前仓库可用的轻量检查：

```bash
npm run ngspice:regression
npm run validate:artifacts -- --summary .where/ci-nema23-run-summary.json
```

验证器可以检查 `kas pipeline` 或 `scripts/run_pipeline.py` 输出的 JSON 摘要；加上 `--strict` 可以把告警视为失败，加上 `--require-erc` 可以要求 ERC 必须启用或可用。

如果摘要里提供了 ERC 报告路径，验证器会连同 ERC 结果一起检查。若本机没有 `kicad-cli`，它会记录这个状态，而不会直接阻塞整条流水线。

可选的 KiCad ERC：

```bash
npm run erc
```

设置 `KICAD_RUN_ERC=true` 时，完整流水线会在写出原理图后尝试执行 ERC。若没有安装 `kicad-cli`，runner 会返回结构化诊断，而不会阻断 KiCad 文件生成。

## 在线 LCSC 搜索

parts resolver 集成了 `@jlcpcb/mcp`，用于在线 LCSC/JLCPCB 搜索和 KiCad 库安装。安装完依赖后，这些命令可以直接使用，不需要 Claude Code 专用 MCP 配置：

```powershell
npm run jlc:list-tools
node scripts\jlc_mcp_bridge.mjs search --query "STM32G431" --source lcsc --limit 3 --in-stock
node scripts\jlc_mcp_bridge.mjs install --id C529355 --project-path .where\nema23-industrial-stepper-driver-v0.1 --include-3d
```

Python resolver 命令默认也走这个桥接：

```powershell
python scripts\resolve_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json --output .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json
python scripts\install_jlc_mcp_parts.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --include-3d
python scripts\write_jlc_mcp_part_lock.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --install-report .where\nema23-industrial-stepper-driver-v0.1\jlc-mcp-install-report.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1
```

当 JLC MCP 安装报告指出符号有问题时，应该先修复再接受锁定文件。例如，NEMA23 场景中的 LM393 比较器可以这样修：

```powershell
python scripts\fix_lm393_jlc_mcp_symbol.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --id C5252905
python scripts\install_jlc_mcp_parts.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --register-only
```

设置 `KICAD_DISABLE_JLC_MCP=1` 可以绕过 MCP 桥接。若已配置凭据，resolver 也可以直接使用 LCSC 官方 OpenAPI：

```powershell
$env:LCSC_API_KEY = '<your-api-key>'
$env:LCSC_API_SECRET = '<your-api-secret>'
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
```

可选配置：

- `LCSC_OPENAPI_BASE_URL` 默认是 `https://ips.lcsc.com`
- `LCSC_OPENAPI_TIMEOUT_SEC` 默认是 `15.0`
- `LCSC_OPENAPI_CURRENCY` 默认是 `USD`
- `LCSC_MCP_BASE_URL` 只用于旧的本地 `/api/search` 后端
- `JLC_MCP_COMMAND` 和 `JLC_MCP_ARGS` 可以覆盖桥接器如何启动 MCP server
- `JLC_MCP_DEBUG=1` 会在调试时打印 MCP server 的 stderr
- `JLC_MCP_INSTALL_TIMEOUT_SEC` 和 `JLC_MCP_INSTALL_RETRIES` 用于调节批量安装行为

如果没有 MCP 包、OpenAPI 凭据或本地 MCP HTTP server，resolver 会返回简短的结构化错误，而不会卡死在 `localhost:3847`。

## 仓库结构

- `src/kicad_suite/`：可复用的流水线、适配器、CLI 和验证器代码
- `scripts/`：用于本地和兼容性的薄 Python/Node 包装器
- `schemas/`：当前模型契约的 JSON Schema
- `docs/`：架构与工作流说明
- `skills/`：面向 agent 的工作流参考
- `.where/`：本地生成输出、日志和规划记录

## 开发方向

KiCad 现在是唯一 सक्रिय 的 EDA 目标。后续优先改进：

- KiCad symbol / footprint 映射
- 原理图生成的确定性
- Netlist 正确性
- ngspice 覆盖率和反馈质量
- KiCad ERC 集成
- 统一命令入口
- 产物验证和可复现摘要
- 清晰的模型契约和回归用例

不要新增 EasyEDA/JLCEDA GUI 桥接功能。EasyEDA 相关引用只应保留在类似 `easyeda2kicad` 这样的库资源导入工具中。

## License

见 `LICENSE`。
