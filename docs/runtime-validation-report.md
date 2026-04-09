# JLCEDA 实机验证记录模板

## 基本信息

- 验证日期：2026-04-09
- 验证人：Codex
- 分支：develop
- 提交 SHA：abdc192
- 插件版本：0.1.20
- JLCEDA 版本：待实机填写
- 操作系统：待实机填写

## 导入结果

- `.eext` 文件路径：`build/dist/jlceda-suite_v0.1.20.eext`
- 是否成功导入：待实机验证
- 是否能在菜单中看到 `JLCEDA Suite`：待实机验证
- 导入或加载时报错：待实机验证

## 菜单与只读命令验证

### 1. About

- 结果：待实机验证
- 现象：待实机验证
- 备注：当前仓库内的自动化 smoke test 已通过，但这不替代 JLCEDA GUI 实机导入。

### 2. Bridge Status

- 结果：待实机验证
- 现象：待实机验证
- 关键返回：待实机验证

### 3. Bridge Self Check

- 结果：待实机验证
- `ping`：待实机验证
- `bridge_status`：待实机验证
- `document_summary`：待实机验证
- `selection_snapshot`：待实机验证
- 备注：自动化层已验证桥接协议和控制平面可用，但未在 JLCEDA GUI 中完成最终实机确认。

### 4. Inspect Current Document

- 结果：待实机验证
- 当前文档类型：待实机验证
- 返回摘要是否合理：待实机验证
- 备注：需要在 JLCEDA 中手工打开目标文档后执行。

## 写操作验证

### 5. project.export_bom

- 结果：待实机验证
- 是否先触发确认门禁：待实机验证
- 导出格式：待实机验证
- 导出文件名：待实机验证
- 导出结果摘要：待实机验证
- 备注：仓库内 smoke test 已覆盖导出链路，但未替代 GUI 实机验证。

### 6. schematic.place_component

- 结果：待实机验证
- 是否先触发确认门禁：待实机验证
- 放置位置：待实机验证
- 返回图元信息：待实机验证
- 备注：需要在 JLCEDA GUI 中执行确认门禁后再复核。

### 7. schematic.create_wire

- 结果：待实机验证
- 是否先触发确认门禁：待实机验证
- 导线点位：待实机验证
- 返回图元信息：待实机验证
- 备注：需要在 JLCEDA GUI 中执行确认门禁后再复核。

## 错误与排障

- 是否出现 `UNSUPPORTED_ACTION`：待实机验证
- 是否出现 `EXECUTION_FAILED`：待实机验证
- 是否出现无弹窗或无响应：待实机验证
- 控制台或界面报错：待实机验证
- 临时绕过方法：待实机验证

## 结论

- 本轮是否通过最小实机验证：否，当前缺少 JLCEDA GUI 内的最终导入与手工调试确认
- 阻塞问题：需要在本机 JLCEDA 中执行 `.eext` 导入并完成菜单/只读/写操作的手工复核
- 建议下一步：完成实机导入后，按清单补齐结果并同步更新 `.where-agent-progress.md`
