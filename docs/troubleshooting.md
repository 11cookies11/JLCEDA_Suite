# 日志与排障说明

## 快速检查顺序

遇到插件行为异常时，建议按下面顺序检查：

1. 先执行 `npm run lint`
2. 再执行 `npm run build`
3. 再执行 `npm run smoke-test`
4. 最后在 JLCEDA 中导入 `.eext` 包做实机验证

如果前三步失败，优先在本地修复，不要直接跳到 JLCEDA 里排查。

## 当前可用命令

目前桥接层已经登记并实现的命令：

- `system.get_bridge_status`
- `project.get_document_summary`
- `project.get_selection_snapshot`
- `project.export_bom`
- `schematic.place_component`
- `schematic.create_wire`

当前已登记但未实现的命令会返回：

- `error.status = "error"`
- `error.code = "UNSUPPORTED_ACTION"`

这是预期保护行为，不是静默失败。

## 常见问题

### 1. `npm run build` 通过，但在 JLCEDA 中没有反应

可能原因：

- 还没有在 JLCEDA 中重新导入最新的 `.eext` 包
- `extension.json` 的菜单入口与导出函数不匹配
- JLCEDA 运行时对某个 API 调用报错，但构建阶段无法发现

建议排查：

1. 确认使用的是最新文件：`build/dist/jlceda-aiagent_v0.1.0.eext`
2. 打开扩展菜单，先点击 `Bridge Status`
3. 再点击 `Inspect Current Document`
4. 如果无弹窗，检查菜单注册函数名称与 `src/index.ts` 导出是否一致

### 2. 写操作命令返回 `confirmation_required`

这是当前设计的一部分，不是错误。

当前以下类型命令默认需要确认：

- `project.export_bom`
- `schematic.place_component`
- `schematic.create_wire`
- 其它未来的写操作命令

如果需要在自动化测试里直接执行，可以显式传：

```json
{
  "requiresConfirmation": false
}
```

注意：

- 这只适合测试环境或明确受控环境
- 在真实用户环境里，默认仍建议保留确认门禁

### 3. 返回 `UNSUPPORTED_ACTION`

说明：

- 命令未在注册表中登记，或者
- 命令已登记但尚未实现

排查位置：

- 注册表：`src/bridge/registry.ts`
- 分发逻辑：`src/bridge/handlers.ts`

### 4. `smoke-test` 失败，但 `build` 正常

说明：

- `build` 主要验证打包链路
- `smoke-test` 还会验证桥接命令的类型收窄和本地模拟执行路径

这通常意味着：

- 命令 payload 类型定义不够严格
- `handlers` 中的分发逻辑与协议类型不一致
- 新增适配层依赖了未声明的运行时全局

重点检查：

- `src/bridge/protocol.ts`
- `src/bridge/handlers.ts`
- `src/eda-runtime.d.ts`
- `scripts/smoke-test.ts`

### 5. 导出 BOM 失败

可能原因：

- 当前工程不在原理图上下文
- JLCEDA 生产资料接口没有返回文件
- 在本地保存时缺少环境支持

排查建议：

1. 先调用 `project.get_document_summary`
2. 确认当前文档类型是原理图相关
3. 再调用 `project.export_bom`
4. 如果只是想验证桥接逻辑，先用 `saveToLocal: false`

## 推荐日志关注点

当前仓库还没有完整日志面板集成，所以建议先关注这些信息：

- `Bridge Status` 菜单弹窗内容
- 命令响应中的 `status`
- 错误响应中的 `error.code`
- 错误响应中的 `error.message`
- 冒烟测试输出中的 `PASS` / 失败堆栈

## 建议的实机验证顺序

在 JLCEDA 里建议按下面顺序验证：

1. `Bridge Status`
2. `Inspect Current Document`
3. `project.export_bom`
4. `schematic.place_component`
5. `schematic.create_wire`

这样可以先确认只读路径和环境状态，再验证写操作。

## 当前已知限制

- 还没有真正的确认令牌二次提交流程
- 还没有 GUI 内部日志面板集成
- PCB 写操作尚未实现
- JLCEDA 实机导入与调试还没有在仓库里正式标记完成
