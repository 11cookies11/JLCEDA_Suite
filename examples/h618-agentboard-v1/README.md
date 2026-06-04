# H618 AgentBoard V1

这是 H618 AgentBoard V1 示例项目的起始工作区。

## 项目目标

- 基于 Allwinner H618 设计一块低成本 Linux 控制板。
- 提供调试串口、MicroSD 启动、SPI NOR、以太网、USB Host 等基础能力。
- 面向 AI Agent 的硬件控制和日志采集工作流。

## 当前状态

- 需求已记录在 `docs/00_requirements.md`
- 系统架构已记录在 `docs/01_system_architecture.md`
- 电源树已记录在 `docs/02_power_tree.md`
- 启动流程已记录在 `docs/03_boot_flow.md`
- 引脚复用已记录在 `docs/04_pinmux.md`
- 原理图模块拆分已记录在 `docs/05_schematic_modules.md`
- PCB 约束已记录在 `docs/06_pcb_constraints.md`
- Bring-up 计划已记录在 `docs/07_bringup_plan.md`
- 风险清单已记录在 `docs/08_risks.md`
- 实施计划已记录在 `docs/09_implementation_plan.md`
- 拓扑完整度清单已记录在 `docs/10_topology_completeness_checklist.md`
- circuit-model 格式规范已记录在 `docs/11_circuit_model_format.md`
- 拓扑收口最后五项已记录在 `docs/12_topology_final_items.md`
- PMIC 收口方案已记录在 `docs/13_pmic_closure.md`
- DDR 收口方案已记录在 `docs/14_ddr_closure.md`
- SoC pinmap 收口方案已记录在 `docs/15_soc_pinmap_closure.md`
- 启动与恢复闭环方案已记录在 `docs/16_boot_recovery_closure.md`
- 接口收口方案已记录在 `docs/17_interface_closure.md`
- 原理图模块输入已记录在 `docs/18_schematic_module_inputs.md`
- 原理图分图元件与网络清单已记录在 `docs/19_schematic_sheet_parts_nets.md`
- 原理图捕获顺序已记录在 `docs/20_schematic_capture_order.md`
- 原理图捕获模板已记录在 `docs/21_schematic_capture_templates.md`
- ERC findings 分类已记录在 `docs/22_erc_findings_triage.md`
- 初始虚拟电路保存在 `source/circuit-model.source.json`
- 根目录 `libraries/` 已包含本项目的 EasyEDA/JLC 符号、封装和 3D 资产
- 初版原理图 pipeline 输出在 `output/v1/`
- KiCad 工程入口在 `output/v1/h618_agentboard_v1_initial/`

## 建议的推进顺序

1. 收口 `docs/00_requirements.md` 中的需求
2. 完成 `docs/01_system_architecture.md` 和 `docs/02_power_tree.md`
3. 按 `docs/09_implementation_plan.md` 继续推进
4. 用统一格式维护 `source/circuit-model.source.json`

## 相关入口

- [仓库根 README](../../README.md)
- [实施计划](docs/09_implementation_plan.md)
- [拓扑完整度清单](docs/10_topology_completeness_checklist.md)
- [circuit-model 格式规范](docs/11_circuit_model_format.md)
- [拓扑收口最后五项](docs/12_topology_final_items.md)
- [PMIC 收口方案](docs/13_pmic_closure.md)
- [DDR 收口方案](docs/14_ddr_closure.md)
- [SoC pinmap 收口方案](docs/15_soc_pinmap_closure.md)
- [启动与恢复闭环方案](docs/16_boot_recovery_closure.md)
- [接口收口方案](docs/17_interface_closure.md)
- [原理图模块输入](docs/18_schematic_module_inputs.md)
- [原理图分图元件与网络清单](docs/19_schematic_sheet_parts_nets.md)
- [原理图捕获顺序](docs/20_schematic_capture_order.md)
- [原理图捕获模板](docs/21_schematic_capture_templates.md)
- [ERC findings 分类](docs/22_erc_findings_triage.md)
- [初版 KiCad 工程](output/v1/h618_agentboard_v1_initial/)
