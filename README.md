# KiCad Agent Suite

这是一个面向硬件设计与自动化协作的 KiCad 工作流仓库。

## 当前重点

- 以 `circuit-model.json` 作为统一输入，驱动器件选择、原理图生成和后续验证流程。
- 为新的 example 硬件提供标准化目录、文档和可复用骨架。
- 通过 `where` 进度文件跟踪托管实施状态。

## H618 示例

当前正在推进的示例是 `examples/h618-agentboard-v1`，目标是一块面向 AI Agent 工作流的 H618 Linux 控制开发板。

### 目录入口

- [示例总览](examples/h618-agentboard-v1/README.md)
- [需求说明](examples/h618-agentboard-v1/docs/00_requirements.md)
- [系统架构](examples/h618-agentboard-v1/docs/01_system_architecture.md)
- [电源树](examples/h618-agentboard-v1/docs/02_power_tree.md)
- [启动流程](examples/h618-agentboard-v1/docs/03_boot_flow.md)
- [引脚复用](examples/h618-agentboard-v1/docs/04_pinmux.md)
- [原理图模块拆分](examples/h618-agentboard-v1/docs/05_schematic_modules.md)
- [PCB 约束](examples/h618-agentboard-v1/docs/06_pcb_constraints.md)
- [Bring-up 计划](examples/h618-agentboard-v1/docs/07_bringup_plan.md)
- [风险清单](examples/h618-agentboard-v1/docs/08_risks.md)
- [实施计划](examples/h618-agentboard-v1/docs/09_implementation_plan.md)
- [拓扑完整度清单](examples/h618-agentboard-v1/docs/10_topology_completeness_checklist.md)
- [circuit-model 格式规范](examples/h618-agentboard-v1/docs/11_circuit_model_format.md)
- [拓扑收口最后五项](examples/h618-agentboard-v1/docs/12_topology_final_items.md)
- [PMIC 收口方案](examples/h618-agentboard-v1/docs/13_pmic_closure.md)
- [DDR 收口方案](examples/h618-agentboard-v1/docs/14_ddr_closure.md)
- [SoC pinmap 收口方案](examples/h618-agentboard-v1/docs/15_soc_pinmap_closure.md)
- [启动与恢复闭环方案](examples/h618-agentboard-v1/docs/16_boot_recovery_closure.md)
- [接口收口方案](examples/h618-agentboard-v1/docs/17_interface_closure.md)
- [原理图模块输入](examples/h618-agentboard-v1/docs/18_schematic_module_inputs.md)
- [原理图分图元件与网络清单](examples/h618-agentboard-v1/docs/19_schematic_sheet_parts_nets.md)
- [原理图捕获顺序](examples/h618-agentboard-v1/docs/20_schematic_capture_order.md)
- [原理图捕获模板](examples/h618-agentboard-v1/docs/21_schematic_capture_templates.md)
- [初版原理图工程](examples/h618-agentboard-v1/output/v1/h618_agentboard_v1_initial/)

## 常用命令

- `npm run scaffold:example -- demo-board --title "Demo Board"`
- `python scripts/kas.py pipeline examples/h618-agentboard-v1/circuit-model.json examples/h618-agentboard-v1/output/v1`

## 进度跟踪

当前进度记录在 [`.where-agent-progress.md`](.where-agent-progress.md)。
