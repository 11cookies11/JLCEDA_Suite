# 发布清单

## 发布前检查

1. 确认当前分支为预期发布分支
2. 执行 `npm run lint`
3. 执行 `npm run build`
4. 执行 `npm run smoke-test`
5. 确认 `build/dist/jlceda-aiagent_v0.1.0.eext` 已生成
6. 在 JLCEDA 中导入最新 `.eext` 包进行实机验证

## 实机验证清单

1. 菜单 `JLCEDA AIAgent` 可以显示
2. `About` 可以正常弹窗
3. `Bridge Status` 可以正常弹窗
4. `Inspect Current Document` 可以正常返回当前文档摘要
5. `project.export_bom` 可以生成导出结果
6. `schematic.place_component` 在关闭确认门禁时可以执行
7. `schematic.create_wire` 在关闭确认门禁时可以执行

## 文档检查

1. `README.md` 与 `README.zh-CN.md` 已同步
2. `docs/bridge-protocol.md` 与当前实现一致
3. `docs/example-scenarios.md` 已更新
4. `docs/troubleshooting.md` 已更新
5. `.where-agent-progress.md` 状态已同步

## 发布产物

当前最重要的发布产物：

- `.eext` 扩展包
- 开发计划与协议文档
- 示例场景与排障文档

## 发布后建议

1. 记录本次实机验证日期和结果
2. 补充 CHANGELOG
3. 整理下一阶段待实现的 PCB 写操作和确认流程
