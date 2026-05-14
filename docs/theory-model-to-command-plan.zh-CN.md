# CircuitModel 到 KiCadExecutionPlan

本文定义 `CircuitModel -> KiCadExecutionPlan` 的编译规则，用于把电路理论模型转换为 KiCad 文件生成计划。

## 输入

- `CircuitModel`：元件、角色、选型、设计决策、风险
- `Netlist`：网络和成员连接，是电气连接真值

## 输出

- `KiCadExecutionPlan`
- KiCad symbol 列表
- KiCad net 列表
- 生成目标文件路径
- 诊断信息

## 编译原则

- 以 `Netlist` 为连接来源，不从布局推断连接。
- 优先使用真实 KiCad `lib_id` 和 footprint。
- 缺少真实映射时可以使用 `AIAgent:*` 占位符，但必须写入 `diagnostics.unsupported`。
- 布局规则只影响可读性，不改变电气连接。
- 所有不确定性必须写入 warnings、unsupported 或 model risks。

## 当前实现

主要实现位于：

```text
src/kicad_suite/compile_kicad_execution_plan.py
src/kicad_suite/schematic_layout_rules.py
src/kicad_suite/kicad_project_writer.py
```

schema 位于：

```text
schemas/kicad-execution-plan.v1.json
```
