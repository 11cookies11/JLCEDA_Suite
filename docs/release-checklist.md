# 发布清单

## 发布前检查

1. 确认当前分支为预期发布分支
2. 执行 `npm run release:check`
3. 确认 `package.json` 与 `extension.json` 的版本号一致
4. 确认 `build/dist/jlceda-aiagent_v*.eext` 已生成
5. 在 JLCEDA 中导入最新 `.eext` 包进行实机验证
6. 确认 `npm run server:command-runner:smoke-test` 已通过

## 实机验证清单

1. 菜单 `JLCEDA AIAgent` 可以显示
2. `About` 可以正常弹窗
3. `Bridge Self Check` 可以返回 `ping`、`bridge_status`、`document_summary`、`selection_snapshot`
4. `Bridge Status` 可以正常弹窗
5. `Inspect Current Document` 可以正常返回当前文档摘要
6. `project.export_bom` 可以生成导出结果
7. `schematic.place_component` 在关闭确认门禁时可以执行
8. `schematic.create_wire` 在关闭确认门禁时可以执行
9. 将结果记录到 `docs/runtime-validation-report.md`

## 文档检查

1. `README.md` 与 `README.zh-CN.md` 已同步
2. `docs/bridge-protocol.md` 与当前实现一致
3. `docs/example-scenarios.md` 已更新
4. `docs/troubleshooting.md` 已更新
5. `docs/runtime-validation-report.md` 已更新
6. `docs/versioning.md` 已更新
7. `.where-agent-progress.md` 状态已同步

## 发布产物

当前最重要的发布产物：

- `.eext` 扩展包
- `build/dist/jlceda-bridge-flow-release.zip` skill + plugin release bundle
- 开发计划与协议文档
- 示例场景与排障文档
- 版本管理与发布清单

## 发布后建议

1. 记录本次实机验证日期和结果
2. 补充 CHANGELOG
3. 整理下一阶段待实现的 PCB 写操作和确认流程
