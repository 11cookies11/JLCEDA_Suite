# NEXDAP 新功能验证报告

本文记录在 `examples/nexdap-fresh` 上对新增仿真能力与时间线日志的验证结果。重点不是重新验证 NEXDAP 是否能生成 KiCad 项目，而是确认以下新能力已经挂入现有流水线：

- `simulation-plan.json` 自动产出
- `pipeline-events.jsonl` 按时间记录
- `ngspice` 执行结果和反馈文件落盘
- `text-to-kicad` 与 `pipeline` 两条入口都能携带这些输出

## 验证对象

- 项目模型：`examples/nexdap-fresh/circuit-model.json`
- 仿真配置：`examples/nexdap-fresh/simulation-profile.json`
- 生成入口：`python .\scripts\kas.py pipeline ...`
- 文本入口：`python .\scripts\kas.py text-to-kicad`

## 验证 1: NEXDAP pipeline

运行命令：

```powershell
python .\scripts\kas.py pipeline examples\nexdap-fresh\circuit-model.json .where\nexdap-nexdap-test
```

主要结果：

- `simulation-profile.json` 生成成功
- `simulation-plan.json` 生成成功
- `pipeline-events.jsonl` 生成成功
- `KiCadExecutionPlan` 和 `kicad-write-summary.json` 生成成功
- `ERC` 成功完成

观察到的时间线事件：

1. `run_pipeline` started
2. `simulation-plan` generated
3. `kicad-generation` completed
4. `kicad-erc` completed
5. `run_pipeline` finished

关键事实：

- 仿真计划自动生成了 5 个场景
- 事件日志按时间追加，能够回放流水线过程
- 这条链路没有依赖终端输出来理解运行过程

输出目录：

- `.where\nexdap-nexdap-test\pipeline-events.jsonl`
- `.where\nexdap-nexdap-test\simulation-plan.json`
- `.where\nexdap-nexdap-test\simulation-profile.json`

## 验证 2: text-to-kicad

运行命令使用了一个 NEXDAP 风格的 `RequirementSpec`，并显式提供了现成的符号库路径：

```powershell
python .\scripts\kas.py text-to-kicad
```

主要结果：

- `requirement-spec.json` 生成成功
- `circuit-model.json` 生成成功
- `netlist.json` 生成成功
- `simulation-profile.json` 和 `simulation-plan.json` 生成成功
- `pipeline-events.jsonl` 生成成功
- `spice-netlist.cir` 生成成功
- `ngspice-execution.json` 生成成功，且 `success=true`
- `ngspice-feedback.json` 生成成功

观察到的时间线事件：

1. `text-to-kicad` started
2. `simulation-plan` generated
3. `kicad-erc` skipped
4. `ngspice` execution completed
5. `text-to-kicad` finished

关键事实：

- `ngspice` 已经真实执行，不是只有网表生成
- `pipeline-events.jsonl` 里能看到每个阶段的时间戳
- `text-to-kicad-summary.json` 已经汇总了仿真输出文件路径

输出目录：

- `.where\text-to-kicad-nexdap-test\nexdap-text-001\pipeline-events.jsonl`
- `.where\text-to-kicad-nexdap-test\nexdap-text-001\ngspice-execution.json`
- `.where\text-to-kicad-nexdap-test\nexdap-text-001\ngspice-feedback.json`
- `.where\text-to-kicad-nexdap-test\nexdap-text-001\text-to-kicad-summary.json`

## 结论

这次验证说明新增功能已经在 NEXDAP 场景里接入成功：

- 仿真计划不是单独工具，而是流水线的一部分
- 时间线日志能够记录关键阶段和产物路径
- `pipeline` 和 `text-to-kicad` 两条入口都能输出一致的仿真相关文件
- `ngspice` 的执行链路在当前仓库环境下可用

在后续细化后，我们又重新跑了一次真实 NEXDAP `pipeline`，仿真计划已经从 5 个场景细分为 7 个场景，分别覆盖：

- 主电源启动
- USB 输入保护
- ESP32 启动与 strap
- RP2040 调试与 BOOTSEL
- 目标电源路径
- 指示灯电流
- 接口偏置与耦合

## 当前已知限制

- `pipeline-events.jsonl` 目前只记录关键阶段，不记录完整 stdout/stderr
- `text-to-kicad` 这次验证使用的是 NEXDAP 风格 `RequirementSpec`，并非完整真实需求输入
- 对于复杂真实项目，仿真场景的覆盖程度仍取决于模型里的角色、网络和器件信息

## 后续建议

1. 继续用真实项目输出观察 `simulation-plan` 是否足够贴近设计意图
2. 如果需要更细的回溯，再考虑把每个阶段的原始日志单独落盘
3. 如果某个项目需要更准的场景推导，再补更完整的 `RequirementSpec`
