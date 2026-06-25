# KiCad Agent Suite

面向 KiCad 的 AI agent 硬件开发流水线。

本仓库用结构化源模型描述电路，随后完成器件解析、IR 编译、验证、KiCad
工程导出和报告生成。

## 软件架构

本工具链采用分层架构。AI agent 或人工只维护结构化电路源模型，工具链负责从该源模型派生
构建产物、验证报告和 KiCad 输出。

```text
AI agent / 人工
  |
  v
CLI 与 agent 入口
  src/kicad_suite/cli.py
  src/kicad_suite/entrypoints/
  |
  v
编排层
  src/kicad_suite/orchestration/
  - workflow 模板、任务路由、流水线协调、后处理
  |
  v
应用服务层
  src/kicad_suite/application_services/
  - 项目状态、诊断、报告、器件解析、语义门禁
  |
  v
领域核心层
  src/kicad_suite/domain/core/
  - 电路模型 IO、IR 编译、IR 验证、网表、仿真计划、引脚管理、KiCad 执行计划
  |
  v
适配器层
  src/kicad_suite/adapters/
  - KiCad 文件/命令、PCB 生成、JLC/LCSC/EasyEDA、符号与封装解析
  |
  v
生成的 build/output 产物
```

### 主数据流

```text
source/circuit-model.source.json
  -> 解析器件和项目本地库
  -> build/circuit-model.resolved.json
  -> build/ir.v1.json
  -> build/ir-validation.json
  -> 硬件语义门禁产物
     build/net-intents.v1.json
     build/pin-contracts.v1.json
     build/hardware-erc.v1.json
     build/export-gate.v1.json
  -> output/<topology>/*.kicad_*
  -> ERC 分类和 agent 报告
  -> build/report.json 与 build/report.md
```

新项目中，`source/circuit-model.source.json` 是唯一权威项目模型。`build/` 和
`output/` 都是从该源模型生成出来的视图。

### Agent 入口

稳定的 agent 入口是：

```powershell
hwtool agent manifest
```

`agent` 命令组提供机器可读的生命周期操作：

- `status`、`inspect`、`explain`、`diagnose`、`report`
- `build-ir`、`validate-ir`、`resolve-symbols`、`export-kicad`
- `run` 和 `patch`：通过 Model API 受控修改模型
- `workflow`：执行模板化多步骤任务
- `pins`：检查和分配引脚资源
- `jlc`：LCSC 搜索、预览和项目本地下载
- `semantic-gates`：列出、验证、生成和接受语义门禁规则

Agent 应优先使用这些命令，不应直接修改生成产物。

### 验证与门禁层

仓库使用多层验证，每一层职责不同：

- IR validation 在 KiCad 导出前检查结构正确性。
- Circuit sanity checks 检查短路、悬空引脚和可疑无源器件。
- Hardware semantic gates 在导出前检查拓扑级错误，例如 USB-C CC 缺少下拉或电源路径接法不安全。
- KiCad ERC 在导出的 KiCad 工程上运行，并分类成 agent 可读的发现。
- Semantic gate proposals 可以从 hardware ERC 发现中生成，作为可审核的项目知识沉淀。

语义门禁文件位置：

```text
build/proposed-semantic-gates/*.gate.json   # 生成的待审核队列
source/semantic-gates/*.gate.json           # 项目已接受规则
resources/hardware-rules/builtin/           # 预留内置规则
resources/hardware-rules/promoted/          # 预留推广规则
```

### 源码目录职责

- `src/kicad_suite/cli.py`：命令行与 agent 命令分发。
- `src/kicad_suite/domain/core/`：模型编译、验证、规划、引脚和资源相关领域逻辑。
- `src/kicad_suite/application_services/`：结合领域逻辑与文件系统状态的项目级服务，包括报告、诊断和规则注册表。
- `src/kicad_suite/orchestration/`：workflow 模板、agent 任务生成、流水线事件日志和构建协调。
- `src/kicad_suite/adapters/`：KiCad 工具/文件、EasyEDA/JLC/LCSC、符号库和 PCB 写入适配。
- `schemas/`：源模型、IR、API 请求/结果、报告、语义门禁和 sidecar 产物的 JSON schema。
- `scripts/`：独立工具脚本，包括硬件语义门禁。
- `tests/`：CLI、schema、Model API、语义门禁、KiCad 生成和 fixture 行为的回归测试。

## 项目布局

新项目使用 `source/` 与 `build/` 分离的结构：

```text
project/
  source/
    circuit-model.source.json
  build/
    circuit-model.resolved.json
    ir.v1.json
    ir-validation.json
    report.json
    report.md
  libraries/
    symbols/
    footprints/
    3dmodels/
  output/
    <topology>/
      <topology>.kicad_pro
      <topology>.kicad_sch
      <topology>.kicad_pcb
      <topology>.erc.json
      <topology>.erc.classification.json
      agent-report.json
```

只编辑 `source/circuit-model.source.json`。`build/`、`output/`、日志和
`project.state.json` 都是生成物。

## 常用流程

在项目目录下运行：

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown
hwtool agent diagnose --project .
```

`validate-ir` 通过之后再导出 KiCad。

## 示例

示例项目的可编辑源模型位于 `examples/*/source/`：

- `examples/stm32f103-minimal-system/source/circuit-model.source.json`
- `examples/esp32c3-minimal-system/source/circuit-model.source.json`
- `examples/refactor-layout-demo/source/circuit-model.source.json`
- `examples/h618-agentboard-v1/source/circuit-model.source.json`

示例项目的 `build/`、`output/` 和下载到项目内的器件库不再提交到 git，需要时按上面的流程重新生成。

## 开发命令

```powershell
python scripts/kas.py --help
python -m pytest
npm run jlc:search -- STM32F103C8T6
```

仓库级 KiCad 资源位于 `resources/kicad/`。
