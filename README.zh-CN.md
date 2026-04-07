# JLCEDA AIAgent

让 Codex 通过插件连接并控制嘉立创 EDA 的桥接项目。

语言：简体中文 | [English](README.md)

## 项目简介

`JLCEDA AIAgent` 的目标，是把嘉立创 EDA 的官方扩展能力封装成一个可被 Codex 调用的硬件开发能力层。

这个仓库不只是一个普通的 EDA 插件模板，而是一个连接两端的桥梁：

- 一端是 `Codex`，负责理解高层任务与生成执行方案
- 一端是 `嘉立创 EDA`，负责实际的原理图、PCB 与工程操作
- 中间的插件负责协议转换、能力封装、执行控制与结果回传

最终效果是让 Codex 能够在受控范围内参与硬件开发流程，例如读取工程状态、辅助放置器件、执行部分编辑操作、导出结构化结果等。

## 当前状态

当前仓库已经不只是模板整理阶段，而是已经具备了第一版可运行桥接能力，包括：

- 可构建并打包为 `.eext` 的 JLCEDA 扩展骨架
- 第一版 Codex 桥接协议与受控命令分发
- 工程只读查看能力
- 基础原理图写操作骨架
- BOM 导出能力
- 冒烟测试、排障说明和发布检查文档

当前最主要的缺口，是还没有完成 `JLCEDA` 客户端内的实机导入与运行验证。

## 已实现命令

当前桥接层已经支持以下命令：

- `system.get_bridge_status`
- `project.get_document_summary`
- `project.get_selection_snapshot`
- `schematic.place_component`
- `schematic.create_wire`
- `project.export_bom`

对于已登记但未实现的命令，桥接层会明确拒绝；对于高风险写操作，会先经过确认门禁。

## 验证方式

仓库内已经具备可重复执行的本地验证路径：

1. `npm run lint`
2. `npm run build`
3. `npm run smoke-test`
4. `npm run release:check`

如果要继续做 `JLCEDA` 内的实机验证，可以参考：

- `docs/example-scenarios.md`
- `docs/troubleshooting.md`
- `docs/release-checklist.md`

## 计划中的能力方向

项目后续计划围绕以下几类能力推进：

- 工程读取：读取当前文档、选区、器件与连接关系
- 安全执行：在明确约束下执行放置、连线、标注等操作
- 结果回传：向 Codex 返回结构化状态、执行结果与错误信息
- 工作流封装：沉淀“查看工程”“放置器件”“导出 BOM”等可复用任务

## 建议架构

当前建议采用四层结构：

1. JLCEDA 扩展宿主层
2. EDA 能力适配层
3. Codex 桥接协议层
4. 硬件工作流层

这样可以把嘉立创 EDA 的底层接口细节隔离在下层，同时让上层对 Codex 暴露更稳定、更安全的能力边界。

## 开发计划

项目里已经整理了持续更新的开发计划：

- Where 看板：`.where-agent-progress.md`
- 计划说明：`.where/development-plan.md`

当前建议优先推进：

1. 将打包后的扩展导入 JLCEDA，完成实机验证
2. 核对文档查看、写操作确认门禁、BOM 导出的真实行为
3. 明确下一阶段要扩展 PCB 操作还是外部通信方式
4. 根据实机结果继续收紧协议与能力边界

## 参考资料

- 嘉立创 EDA 官方扩展开发指南：https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## 许可证

见 `LICENSE`。
