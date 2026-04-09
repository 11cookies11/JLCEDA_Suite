# JLCEDA Suite

让 Codex 通过插件连接并控制嘉立创 EDA 的桥接项目。

语言：简体中文 | [English](README.md)

## 项目简介

`JLCEDA Suite` 将 JLCEDA 插件、bridge server 和 agent skill 包装成一套用于 AI 辅助硬件开发的工具集。

这套系统主要由三部分组成：

- `JLCEDA Suite Plugin`：JLCEDA 扩展与编辑器内控制台
- `JLCEDA Suite Server`：负责会话连接、控制平面与请求路由的 bridge server
- `JLCEDA Suite Skill`：供 AI agent 复用的服务端工作流 skill 包

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
- 本地控制平面与服务器端项目流脚本，可驱动已连接的桥接会话
- 通用服务器侧命令运行器，可对已连接会话执行任意多步桥接序列
- 工程只读查看能力
- 编辑器分屏与文档导航能力
- 原理图与 PCB 的文档级读写、定位、缩放与 DRC 能力
- 快捷键、定时器和右键菜单回调注册能力，以及回调事件队列查看能力
- 文件系统、存储、对比工具和菜单工具能力
- 基础原理图写操作骨架
- BOM 导出能力
- 一个用于扩展官方 JLCEDA API 可调用面的 `system.api_invoke` 通用入口
- 插件侧与服务端冒烟测试、排障说明和发布检查文档

当前最主要的缺口，是还没有完成公网环境联调、服务器端 Codex 接入，以及 `JLCEDA` 客户端内的实机导入与运行验证。

## 公网服务模式

在启动 Python 服务端之前，先安装运行时依赖：

```bash
python3 -m pip install -r requirements-server.txt
```

如果你不想装到系统环境里，服务启动时也会在 `~/.cache/jlceda-suite-python-server` 下自动创建缓存虚拟环境并安装依赖。

如果你要在公网机器上部署桥接服务，建议直接用控制平面一起启动：

```bash
npm run server:public
```

这样会把桥接服务监听在 `ws://0.0.0.0:8787`，控制平面监听在 `http://0.0.0.0:8788`。插件可以连接到 `ws://<server-ip>:8787`，服务器侧项目流则可以直接打到 `http://<server-ip>:8788`。

控制平面还提供了原理图优先工作流使用的规则 profile：

- `GET /profiles`：列出可用 profile
- `GET /profile`：读取当前 active profile
- `POST /profile`：按名称切换 active profile

你可以通过 `BRIDGE_RULE_PROFILE` 覆盖当前 active profile，也可以用 `BRIDGE_RULE_PROFILE_FILE` 指向自定义 profile 配置文件。

插件在形成可用基线后应尽量保持稳定，后续优先通过 server 侧的 profile 和编排调整策略，减少频繁更新插件的次数。

## 自动更新

插件启动时会自动检查对应 GitHub 仓库的最新 release。默认目标仓库是本仓库，但你也可以改成自己的公开或私有仓库。

在插件的“更新配置”里填写：

- 仓库所有者：`owner`
- 仓库名：`repo`
- GitHub Token：私有仓库时填写有 `repo` 读取权限的 token，公开仓库可以留空

如果 GitHub Token 留空，插件会保留你之前保存的 token；如果仓库地址留空，则继续使用默认仓库 `11cookies11/JLCEDA_Suite`。

示例：

```text
仓库所有者：my-org
仓库名：my-private-plugin
GitHub Token：ghp_xxxxxxxxxxxxxxxxxxxx
```

配置保存后，你可以在插件里点击：

- `检查更新`
- `打开更新页`

这样插件就会从你指定的 GitHub Release 里读取最新版本，并在必要时提示你下载新的 `.eext` 包。

## 已实现命令

当前桥接层已经支持以下命令：

- `system.ping`
- `system.get_bridge_status`
- `system.log_add`
- `system.log_clear`
- `system.log_export`
- `system.log_sort`
- `system.log_find`
- `system.panel_open_left`
- `system.panel_close_left`
- `system.panel_toggle_left_lock`
- `system.panel_is_left_locked`
- `system.panel_open_right`
- `system.panel_close_right`
- `system.panel_toggle_right_lock`
- `system.panel_is_right_locked`
- `system.panel_open_bottom`
- `system.panel_close_bottom`
- `system.panel_toggle_bottom_lock`
- `system.panel_is_bottom_locked`
- `system.window_open`
- `system.window_open_ui`
- `system.window_get_current_theme`
- `system.window_get_url_param`
- `system.window_get_url_anchor`
- `system.show_toast_message`
- `system.show_follow_mouse_tip`
- `system.remove_follow_mouse_tip`
- `system.show_information_message`
- `system.show_confirmation_message`
- `system.shortcut_get_shortcuts`
- `system.shortcut_register`
- `system.shortcut_unregister`
- `system.shortcut_list_registered`
- `system.timer_set_interval`
- `system.timer_clear_interval`
- `system.timer_set_timeout`
- `system.timer_clear_timeout`
- `system.right_click_change_menu`
- `system.callback_events_list`
- `system.callback_events_drain`
- `system.file_system_get_extension_file`
- `system.file_system_save_file`
- `system.file_system_save_file_to_file_system`
- `system.file_system_list_files`
- `system.file_system_delete_file`
- `system.file_system_get_eda_path`
- `system.file_system_get_documents_path`
- `system.file_system_get_libraries_paths`
- `system.file_system_get_projects_paths`
- `system.file_manager_get_project_file`
- `system.file_manager_get_document_file`
- `system.file_manager_get_document_source`
- `system.file_manager_get_document_footprint_sources`
- `system.file_manager_set_document_source`
- `system.file_manager_get_project_file_by_project_uuid`
- `system.file_manager_get_device_file_by_device_uuid`
- `system.file_manager_get_symbol_file_by_symbol_uuid`
- `system.storage_get_all_user_configs`
- `system.storage_set_all_user_configs`
- `system.storage_clear_all_user_configs`
- `system.storage_get_user_config`
- `system.storage_set_user_config`
- `system.storage_delete_user_config`
- `system.tool_netlist_comparison`
- `system.tool_schematic_comparison`
- `system.tool_pcb_comparison`
- `system.header_menu_replace`
- `system.header_menu_insert`
- `system.header_menu_remove`
- `system.header_menu_insert_system_item`
- `system.header_menu_remove_system_item`
- `system.format_conversion_ad_single`
- `system.format_conversion_ad_multi`
- `system.format_conversion_disa_single`
- `system.format_conversion_disa_multi`
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
- `schematic.inspect_layout_hygiene`
- `schematic.inspect_label_hygiene`
- `schematic.suggest_power_block_layout`
- `schematic.check_drc`
- `pcb.import_changes`
- `pcb.save`
- `pcb.inspect_layout_hygiene`
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
8. 启动 `npm run server:public` 后，运行 `npm run server:project-flow`
9. 如果要执行任意控制平面序列，运行 `npm run server:command-runner`

如果要继续做 `JLCEDA` 内的实机验证，可以参考：

- `docs/example-scenarios.md`
- `docs/api-invoke-cheatsheet.md`
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
5. 若需要服务器侧批量验证，先以 `BRIDGE_SERVER_CONTROL_PORT` 启动控制入口，再运行 `npm run server:project-flow`

## 参考资料

- 嘉立创 EDA 官方扩展开发指南：https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## 许可证

见 `LICENSE`。
