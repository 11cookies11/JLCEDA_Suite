# JLCEDA Suite

A bridge project that lets Codex connect to and control JLCEDA through a plugin.

Language: English | [简体中文](README.zh-CN.md)

## Overview

`JLCEDA Suite` packages the JLCEDA plugin, bridge server, and agent skill flow into one toolkit for AI-assisted hardware development.

The suite is organized into three main parts:

- `JLCEDA Suite Plugin`: the JLCEDA extension and in-editor control console
- `JLCEDA Suite Server`: the bridge server and control plane for connected sessions
- `JLCEDA Suite Skill`: the reusable agent skill package for driving the server-side workflow

This repository is not just a generic EDA plugin template. It is becoming a bridge between two sides:

- `Codex` running on a server, which understands higher-level tasks and generates execution plans
- `JLCEDA` running on a local client, which performs the actual schematic, PCB, and project operations
- A middle layer made of a public bridge service plus a JLCEDA plugin, which translates protocol messages, wraps capabilities, controls execution, and returns results

The end goal is to let server-side Codex participate in hardware-development workflows within controlled boundaries, such as reading project state, assisting with component placement, executing selected editor actions, and exporting structured results.

## Current Status

The repository has moved beyond the initial template-cleanup stage. It now includes:

- A runnable JLCEDA extension skeleton with packaged `.eext` output
- A first-pass Codex bridge protocol and guarded command dispatcher
- A minimal bridge server with session registration, heartbeats, and request routing
- A plugin-side remote transport client built on `eda.sys_WebSocket`
- Local end-to-end bridge validation that exercises server-to-plugin request routing
- A local control plane and server-side project-flow runner for driving a connected bridge session
- A generic server-side command runner for executing arbitrary multi-step bridge sequences or reusable templates such as inspect, select, design, pcb, and export
- Project, schematic, PCB, and board inventory commands
- Read-only project inspection commands
- Controlled project creation/opening commands
- Editor split-screen and document navigation commands
- Schematic and PCB document operations, including save/import/navigate/zoom/DRC flows
- Shortcut, timer, and right-click callback registration commands with event queue inspection
- Basic schematic and PCB write-command scaffolding
- BOM export support
- A generic `system.api_invoke` bridge entry for expanding the callable official JLCEDA API surface
- Plugin and server smoke tests, troubleshooting, and release-check documentation
- A workflow-level skill smoke test plus a practical schematic-first usage guide

The main gaps that remain are public-network validation, server-side Codex integration, and real JLCEDA runtime verification through local import and manual execution.

## Public Server Mode

Before starting the Python server, install its runtime dependency:

```bash
python3 -m pip install -r requirements-server.txt
```

If you prefer not to install it system-wide, the server also bootstraps a cached virtual environment under `~/.cache/jlceda-suite-python-server` on first launch.

If you are hosting the bridge on a public machine, start it with the control plane enabled:

```bash
npm run server:public
```

That starts the bridge on `ws://0.0.0.0:8787` and the control plane on `http://0.0.0.0:8788`. A plugin can then connect to `ws://<server-ip>:8787`, and server-side project flows can target `http://<server-ip>:8788`.

The control plane also exposes rule profiles for schematic-first workflows:

- `GET /profiles` lists the available profiles
- `GET /profile` returns the active profile
- `POST /profile` switches the active profile by name

You can override the active profile with `BRIDGE_RULE_PROFILE`, or point the server at a custom profile file with `BRIDGE_RULE_PROFILE_FILE`.

The plugin is intended to stay relatively stable once a working baseline is established; prefer iterating on server-side profiles and orchestration before releasing plugin updates.

## Auto Update

On startup, the plugin checks the latest release of the configured GitHub repository. By default, it targets this repository, but you can point it at your own public or private repo.

In the plugin's update settings, fill in:

- Repository owner: `owner`
- Repository name: `repo`
- GitHub token: a token with `repo` read access for private repositories; leave blank for public repositories

If you leave the GitHub token blank, the plugin keeps the previously saved token. If you leave the repository fields blank, it falls back to the default repository `11cookies11/JLCEDA_Suite`.

Example:

```text
Repository owner: my-org
Repository name: my-private-plugin
GitHub token: ghp_xxxxxxxxxxxxxxxxxxxx
```

After saving the settings, you can use:

- `Check Updates`
- `Open Release Page`

The plugin will then read the latest release from the GitHub repo you configured and prompt you when a newer `.eext` package is available.

## Implemented Commands

The current bridge implementation supports these commands:

- `system.ping`
- `system.get_bridge_status`
- `system.get_environment`
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
- `project.get_inventory`
- `project.get_document_summary`
- `project.get_selection_snapshot`
- `project.list_workspaces`
- `project.list_teams`
- `project.list_involved_teams`
- `project.list_projects`
- `project.get_project_info`
- `project.open_project`
- `project.create_project`
- `project.list_schematics`
- `project.list_schematic_pages`
- `project.list_boards`
- `project.list_pcbs`
- `project.get_board_summary`
- `project.create_board`
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
- `schematic.annotate_net`
- `schematic.get_current_schematic_info`
- `schematic.create_schematic`
- `schematic.create_schematic_page`
- `schematic.create_net_flag`
- `schematic.create_net_port`
- `schematic.create_short_circuit_flag`
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
- `pcb.get_board_summary`
- `pcb.get_current_pcb_info`
- `pcb.list_pcbs`
- `pcb.create_pcb`
- `pcb.place_footprint`
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
- `project.export_bom`

Unsupported but registered commands are rejected explicitly, and high-risk write operations are gated by confirmation rules.

## Validation

The repository already includes a repeatable local validation path:

1. `npm run lint`
2. `npm run build`
3. `npm run smoke-test`
4. `npm run server:smoke-test`
5. `npm run remote-client:smoke-test`
6. `npm run bridge:e2e-smoke-test`
7. `npm run release:check`
8. Start the bridge server with `npm run server:public` and run `npm run server:project-flow`
9. For arbitrary control-plane sequences, run `npm run server:command-runner`

For runtime verification inside JLCEDA, see:

- `docs/example-scenarios.md`
- `docs/api-invoke-cheatsheet.md`
- `docs/troubleshooting.md`
- `docs/release-checklist.md`

## Planned Capability Areas

The roadmap currently focuses on these capability areas:

- Project inspection: read the current document, selection, components, and connectivity
- Safe execution: perform placement, wiring, annotation, and similar actions under explicit constraints
- Result reporting: return structured state, execution results, and error details back to Codex
- Remote transport: let the plugin connect outward to a public bridge service and receive remote commands
- Workflow packaging: provide reusable tasks such as "inspect project", "place component", and "export BOM"

## Suggested Architecture

The current recommended structure has four layers:

1. JLCEDA extension host layer
2. EDA capability adapter layer
3. Codex bridge/protocol layer
4. Hardware workflow layer

This keeps official JLCEDA API details isolated in lower layers while giving Codex a safer and more stable capability boundary.

## Development Plan

The working plan is tracked inside the repository:

- Where board: `.where-agent-progress.md`
- Plan notes: `.where/development-plan.md`

Current next steps:

1. Design the communication and security model between the plugin and the public bridge service
2. Implement the server-side bridge service and the plugin-side transport layer
3. Complete an end-to-end flow from server-side Codex to a running JLCEDA client
4. Follow up with real runtime validation and tighten the command contract where needed

## Reference

- Official JLCEDA extension guide: https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## License

See `LICENSE`.

## Workflow Guide

Read [docs/workflow-guide.md](docs/workflow-guide.md) for the recommended inspect -> select -> design -> pcb collaboration flow and the workflow-level smoke test entrypoint.
