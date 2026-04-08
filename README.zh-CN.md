# JLCEDA AIAgent

让 Codex 通过插件连接并控制嘉立创 EDA 的桥接项目。

语言：简体中文 | [English](README.md)

## 项目简介

`JLCEDA AIAgent` 的目标，是把嘉立创 EDA 的官方扩展能力封装成一个可被 Codex 调用的硬件开发能力层。

这个仓库不只是一个普通的 EDA 插件模板，而是一个连接两端的桥梁：

- 一端是部署在服务器上的 `Codex`，负责理解高层任务与生成执行方案
- 一端是本地运行的 `嘉立创 EDA`，负责实际的原理图、PCB 与工程操作
- 中间将由“公网桥接服务 + JLCEDA 插件”共同负责协议转换、能力封装、执行控制与结果回传

最终效果是让服务器端 Codex 能够在受控范围内参与硬件开发流程，例如读取工程状态、辅助放置器件、执行部分编辑操作、导出结构化结果等。

## 当前状态

当前仓库已经不只是模板整理阶段，而是已经具备了第一版可运行桥接能力，包括：

- 可构建并打包为 `.eext` 的 JLCEDA 扩展骨架
- 第一版 Codex 桥接协议与受控命令分发
- 最小可用的桥接服务端骨架，支持注册、心跳和请求路由
- 基于 `eda.sys_WebSocket` 的插件侧远程传输客户端
- 覆盖服务端到插件请求路由的本地端到端联调验证
- 工程只读查看能力
- 编辑器分屏与文档导航能力
- 原理图与 PCB 的文档级读写、定位、缩放与 DRC 能力
- 基础原理图写操作骨架
- BOM 导出能力
- 插件侧与服务端冒烟测试、排障说明和发布检查文档

当前最主要的缺口，是还没有完成公网环境联调、服务器端 Codex 接入，以及 `JLCEDA` 客户端内的实机导入与运行验证。

## 已实现命令

当前桥接层已经支持以下命令：

- `system.ping`
- `system.get_bridge_status`
- `project.get_document_summary`
- `project.get_selection_snapshot`
- `project.open_document`
- `project.open_library_document`
- `project.close_document`
- `project.get_split_screen_tree`
- `project.get_split_screen_id_by_tab_id`
- `project.get_tabs_by_split_screen_id`
- `project.create_split_screen`
- `project.move_document_to_split_screen`
- `project.activate_document`
- `project.activate_split_screen`
- `project.tile_all_documents_to_split_screen`
- `project.merge_all_documents_from_split_screen`
- `project.get_current_rendered_area_image`
- `project.zoom_to_region`
- `project.zoom_to`
- `project.zoom_to_all_primitives`
- `project.zoom_to_selected_primitives`
- `schematic.place_component`
- `schematic.create_wire`
- `project.export_bom`
- `schematic.import_changes`
- `schematic.save`
- `schematic.navigate_to_coordinates`
- `schematic.navigate_to_region`
- `schematic.get_primitive_at_point`
- `schematic.get_primitives_in_region`
- `schematic.get_current_filter_configuration`
- `schematic.auto_routing`
- `schematic.auto_layout`
- `schematic.check_drc`
- `pcb.import_changes`
- `pcb.save`
- `pcb.get_calculating_ratline_status`
- `pcb.start_calculating_ratline`
- `pcb.stop_calculating_ratline`
- `pcb.convert_canvas_origin_to_data_origin`
- `pcb.convert_data_origin_to_canvas_origin`
- `pcb.get_canvas_origin`
- `pcb.set_canvas_origin`
- `pcb.navigate_to_coordinates`
- `pcb.navigate_to_region`
- `pcb.get_primitive_at_point`
- `pcb.get_primitives_in_region`
- `pcb.zoom_to_board_outline`
- `pcb.get_current_filter_configuration`
- `pcb.clear_routing`
- `project.save_panel`

对于已登记但未实现的命令，桥接层会明确拒绝；对于高风险写操作，会先经过确认门禁。

## 验证方式

仓库内已经具备可重复执行的本地验证路径：

1. `npm run lint`
2. `npm run build`
3. `npm run smoke-test`
4. `npm run server:smoke-test`
5. `npm run remote-client:smoke-test`
6. `npm run bridge:e2e-smoke-test`
7. `npm run release:check`

如果要继续做 `JLCEDA` 内的实机验证，可以参考：

- `docs/example-scenarios.md`
- `docs/troubleshooting.md`
- `docs/release-checklist.md`

## 计划中的能力方向

项目后续计划围绕以下几类能力推进：

- 工程读取：读取当前文档、选区、器件与连接关系
- 安全执行：在明确约束下执行放置、连线、标注等操作
- 结果回传：向 Codex 返回结构化状态、执行结果与错误信息
- 远程传输：让插件主动连接公网服务端，接收服务器下发的桥接命令
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

1. 设计插件端与公网服务端的通信协议和安全策略
2. 实现服务端桥接程序与插件侧远程传输层
3. 完成服务器端 Codex 到 JLCEDA 的端到端联调
4. 在联调通过后补做 JLCEDA 实机导入验证与协议修正

## 参考资料

- 嘉立创 EDA 官方扩展开发指南：https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## 许可证

见 `LICENSE`。
