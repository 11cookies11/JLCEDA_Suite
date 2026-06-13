# KiCad Agent Suite

面向 KiCad 的 AI agent 硬件开发流水线。

本仓库用结构化源模型描述电路，随后完成器件解析、IR 编译、验证、KiCad
工程导出和报告生成。

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
