# KiCad Agent Suite

Agent 辅助 KiCad 硬件开发流水线。

语言：简体中文 | [English](README.md)

## 项目简介

`KiCad Agent Suite` 的目标是把结构化硬件需求转换成可检查、可仿真、可交付给 KiCad 的工程文件。当前主线是文件生成流水线，不控制 GUI 编辑器。

当前链路：

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

旧 EasyEDA/JLCEDA 插件桥接代码已经移除。新的开发只面向 KiCad 工程生成以及可复用的 KiCad/LCSC 资源。

## 当前能力

- 需求、CircuitModel、Netlist、SPICE、ngspice feedback、KiCad execution plan 的 JSON Schema
- Python 端文本/需求到 KiCad 的主流水线
- 角色感知的原理图布局规则，并可选接入 ELK layout
- KiCad `.kicad_pro` 与 `.kicad_sch` 生成
- ngspice 网表导出、执行、日志解析和结构化反馈
- 可选 `kicad-cli` ERC
- ngspice 最小回归样例

## 运行命令

先安装 Node 依赖：

```bash
npm install
```

运行默认 KiCad 流水线：

```bash
npm run pipeline
```

常用命令：

```bash
npm run text-to-kicad
npm run compile-plan
npm run write-project
npm run erc
npm run ngspice:regression
```

可以直接使用默认需求，也可以通过 `BRIDGE_REQUIREMENT_SPEC_JSON` 传入结构化需求：

```bash
BRIDGE_REQUIREMENT_SPEC_JSON='{"schema_version":"requirement-spec.v1", "...":"..."}' npm run text-to-kicad
```

PowerShell 示例：

```powershell
$env:KICAD_PROJECT_NAME = 'led_indicator'
$env:BRIDGE_REQUIREMENT_SPEC_JSON = '{ "schema_version": "requirement-spec.v1", "...": "..." }'
npm run text-to-kicad
```

## 输出文件

默认输出目录：

```text
.where/kicad-output/<project_name>/
```

主要输出：

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

## 验证

当前根包可运行的轻量检查：

```bash
npm run ngspice:regression
```

单独运行 KiCad ERC：

```bash
npm run erc
```

如果希望完整流水线在写出原理图后尝试 ERC，可设置：

```bash
KICAD_RUN_ERC=true npm run text-to-kicad
```

如果本机没有 `kicad-cli`，ERC runner 会输出结构化诊断，不阻塞 KiCad 文件生成。

## 仓库结构

- `scripts/`：当前主线 Python/Node 流水线脚本
- `schemas/`：当前模型契约的 JSON Schema
- `docs/`：架构与工作流说明
- `skills/`：面向 agent 的工作流参考
- `.where/`：本地生成输出、日志和计划记录

## 开发方向

KiCad 现在是唯一活跃 EDA 目标。后续优先投入：

- KiCad symbol/footprint 映射
- 可重复的原理图生成
- Netlist 正确性
- ngspice 覆盖率与反馈质量
- KiCad ERC 集成
- 清晰的模型契约与回归样例

不要新增 EasyEDA/JLCEDA GUI 桥接能力。EasyEDA 相关引用应仅限于 `easyeda2kicad` 等库资源导入工具。

## License

见 `LICENSE`。
