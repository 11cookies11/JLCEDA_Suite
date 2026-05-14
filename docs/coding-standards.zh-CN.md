# KiCad Suite 代码规范（v1）

本文用于统一 `scripts/`、`schemas/`、`skills/` 和文档的开发风格。

## 1. 总体原则

- 先定义契约，再写转换逻辑。
- 当前主线只面向 KiCad；EasyEDA/JLCEDA 代码只保留在 `legacy/`。
- 可读性优先于技巧。
- 一次改动一个意图，避免把重构、功能、修复混在同一提交。
- 接口字段变更必须同步更新 schema、文档和 where 记录。

## 2. 编码与命名

- 全仓库文本文件使用 UTF-8。
- Python 使用 `snake_case`。
- TypeScript/JavaScript 使用 `camelCase`。
- 常量使用 `UPPER_SNAKE_CASE`。
- 文件名与导出名应表达职责，不使用无意义缩写。
- 注释只解释必要的“为什么”，不解释显而易见的“做了什么”。

## 3. Python 规范

- 公共函数使用类型注解。
- 数据模型字段应与 `schemas/` 中的 JSON Schema 对齐。
- 解析、建模、编译、执行、反馈应尽量保持模块边界清晰。
- 错误和诊断优先返回结构化对象。
- 不要静默降级重要电气问题；用 `risks`、`warnings` 或 `unsupported` 暴露。

## 4. 模型契约

- 跨层模型统一带 `schema_version`。
- 结构变更遵循：新增可选字段 -> 消费端兼容 -> 再升级必填字段。
- `Netlist` 只表达电气连接真值，不混入布局信息。
- `KiCadExecutionPlan` 表达 KiCad 文件生成意图，不表达仿真语义。
- ngspice 反馈只作为验证证据，不替代工程判断。

## 5. KiCad 生成规则

- 优先使用真实 KiCad library symbol 和 footprint 映射。
- 使用占位符时必须写入诊断。
- 角色映射、布局规则和 symbol 尺寸要集中维护，避免散落硬编码。
- 生成文件应可重复，避免不必要的随机变化。

## 6. 日志与追踪

- 保留 `request_id`，方便跨模型追踪。
- 设计依据写入 `design_decisions[]`。
- 仿真和 ERC 结果写入结构化 summary。

## 7. 验证

提交前至少按影响范围执行：

- `python3 -m py_compile scripts/*.py` 等价检查
- `npm run text-to-kicad`
- `npm run ngspice:regression`
- `npm run erc`，如果本机有 KiCad CLI 或指定输入文件

## 8. where 同步

- 每个阶段性任务更新 `.where-agent-progress.md`。
- 阻塞项使用 `[!]` 并写清原因。
- 长期计划写入 `.where/development-plan.md`，避免进度文件过载。
