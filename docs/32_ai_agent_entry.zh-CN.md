# AI Agent 使用入口

本文说明外部仓库以 submodule 引用 KiCad Agent Suite 后，AI agent 如何调用 toolchain。

## 入口命令

优先使用统一入口：

```powershell
$env:PYTHONPATH="path/to/KiCadAgentSuite/src"
python -m kicad_suite.cli agent manifest
```

如果调用环境已经安装了 `kas` 命令，也可以直接使用：

```powershell
kas agent manifest
```

## 能力发现

```powershell
python -m kicad_suite.cli agent manifest
```

输出 `kas-agent-entry.v1`，用于让 agent 发现当前可用入口、项目文件约定和 DSL API schema。

## 标准工作流

Agent 每次接手项目时，建议先跑：

```powershell
python -m kicad_suite.cli agent status --project .
python -m kicad_suite.cli agent inspect --project .
python -m kicad_suite.cli agent report --project .
```

生成 KiCad 前，建议固定使用：

```powershell
python -m kicad_suite.cli agent build-ir --project .
python -m kicad_suite.cli agent validate-ir --project .
python -m kicad_suite.cli agent rule-check --project .
python -m kicad_suite.cli agent build-kicad --project .
python -m kicad_suite.cli agent report --project . --markdown
```

这条链路对应：

```text
status -> inspect -> build-ir -> validate-ir -> rule-check -> build-kicad -> report -> fix
```

## 新建硬件项目

```powershell
python -m kicad_suite.cli agent create examples/my-board-v1 `
  --project-id my-board-v1 `
  --topology my_board_v1 `
  --source-model seed/source/circuit-model.source.json `
  --export-ir
```

该命令会调用 `create_hardware_project`，生成标准项目目录、`source/circuit-model.source.json`、`project.state.json`，并可选导出 `build/ir.json`。

## 调用 DSL 操作

```powershell
python -m kicad_suite.cli agent run add_net `
  --project examples/my-board-v1 `
  --payload-json '{ "name": "+3V3", "members": [] }'
```

复杂 payload 可以放到文件中：

```powershell
python -m kicad_suite.cli agent run add_component `
  --project examples/my-board-v1 `
  --payload-file requests/add-component.json
```

## 导出 KiCad 工程

```powershell
python -m kicad_suite.cli agent export-kicad `
  --project examples/my-board-v1 `
  --project-name my_board_v1
```

默认读取项目下的 `source/circuit-model.source.json`，输出到项目下的 `output/`。

`build-kicad` 是同一能力的工作流别名：

```powershell
python -m kicad_suite.cli agent build-kicad --project examples/my-board-v1
```

## 结构化报告

```powershell
python -m kicad_suite.cli agent report --project examples/my-board-v1 --markdown
```

默认写入：

- `build/report.json`: 给 AI agent 使用。
- `build/report.md`: 给人阅读。

## Toolchain Doctor

```powershell
python -m kicad_suite.cli agent doctor --project examples/my-board-v1
```

该命令检查 Python、项目目录、`source/circuit-model.source.json`、schema、KiCad 资源目录和 ngspice 环境，并返回结构化 JSON。

## 常用控制参数

- `--dry-run`: 只试运行，不写回模型和状态。
- `--validate-only`: 只执行校验语义。
- `--no-commit`: 不提交模型变更。
- `--no-diff`: 不返回 diff。
- `--no-snapshot`: 不返回 before/after snapshot。
- `--config`: 注入外部工具配置，如 KiCad/ngspice 路径。

## Submodule 调用建议

父仓库建议保留自己的硬件项目文件，把 toolchain 放在固定目录，例如：

```text
hardware-project/
  source/circuit-model.source.json
  project.state.json
  toolchains/KiCadAgentSuite/
```

调用时设置：

```powershell
$env:PYTHONPATH="toolchains/KiCadAgentSuite/src"
python -m kicad_suite.cli agent export-kicad --project .
```

这样父仓库可以固定 submodule commit，同时让 agent 使用稳定的 toolchain 入口。
