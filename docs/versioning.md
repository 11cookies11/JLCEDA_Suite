# 版本管理策略

## 版本号约定

当前仓库使用语义化版本号（SemVer），格式为 `MAJOR.MINOR.PATCH`。

- `MAJOR`：模型契约、运行方式或生成文件结构出现不兼容变更
- `MINOR`：新增向后兼容的 KiCad 生成、仿真、ERC 或工作流能力
- `PATCH`：修复缺陷、完善文档、补充测试或修正非破坏性实现细节

## 版本同步位置

发布前至少同步：

1. `package.json` 中的 `version`
2. `pyproject.toml` 中的 `version`

如果后续发布独立 skill 包，也应同步 skill 元数据版本。

## 当前阶段建议

当前仓库处于 KiCad-only 主线收敛和能力验证阶段，建议继续使用 `0.x.y` 版本段。

进入 `1.0.0` 前应满足：

- RequirementSpec/CircuitModel/Netlist/KiCadExecutionPlan 契约稳定
- KiCad schematic 生成可重复
- 常见元件有可用 symbol/footprint 映射
- ngspice 回归覆盖基础成功与失败路径
- KiCad ERC 流程可稳定运行或明确降级

## 发布前核验

按当前根包能力，优先执行：

```bash
npm run text-to-kicad
npm run ngspice:regression
```

如果本机配置了 KiCad CLI 和输入文件，再执行：

```bash
npm run erc
```
