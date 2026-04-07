# JLCEDA 实机验证记录模板

## 基本信息

- 验证日期：
- 验证人：
- 分支：
- 提交 SHA：
- 插件版本：
- JLCEDA 版本：
- 操作系统：

## 导入结果

- `.eext` 文件路径：
- 是否成功导入：
- 是否能在菜单中看到 `JLCEDA AIAgent`：
- 导入或加载时报错：

## 菜单与只读命令验证

### 1. About

- 结果：通过 / 失败
- 现象：
- 备注：

### 2. Bridge Status

- 结果：通过 / 失败
- 现象：
- 关键返回：

### 3. Bridge Self Check

- 结果：通过 / 失败
- `ping`：
- `bridge_status`：
- `document_summary`：
- `selection_snapshot`：
- 备注：

### 4. Inspect Current Document

- 结果：通过 / 失败
- 当前文档类型：
- 返回摘要是否合理：
- 备注：

## 写操作验证

### 5. project.export_bom

- 结果：通过 / 失败
- 是否先触发确认门禁：
- 导出格式：
- 导出文件名：
- 导出结果摘要：
- 备注：

### 6. schematic.place_component

- 结果：通过 / 失败
- 是否先触发确认门禁：
- 放置位置：
- 返回图元信息：
- 备注：

### 7. schematic.create_wire

- 结果：通过 / 失败
- 是否先触发确认门禁：
- 导线点位：
- 返回图元信息：
- 备注：

## 错误与排障

- 是否出现 `UNSUPPORTED_ACTION`：
- 是否出现 `EXECUTION_FAILED`：
- 是否出现无弹窗或无响应：
- 控制台或界面报错：
- 临时绕过方法：

## 结论

- 本轮是否通过最小实机验证：
- 阻塞问题：
- 建议下一步：
