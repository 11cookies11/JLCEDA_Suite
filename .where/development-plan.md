# JLCEDA Suite 开发计划说明（文本 -> JLCEDA）

## 已完成主线
- `RequirementSpec -> CircuitModel -> ExecutionPlan` 三层模型已落地。
- 三层模型 JSON Schema 已落地到 `server/schemas/`。
- Python 自动化管线已落地到 `scripts/server_text_to_schematic.py`。
- Skill 已增加 `text2schematic` 模式与参考文档。
- 代码规范文档已落地到 `docs/coding-standards.zh-CN.md`。

## 运行方式
- dry-run：
```bash
npm run server:text-to-schematic
```
- 执行模式（连接到本地控制面）：
```bash
BRIDGE_EXECUTE_PLAN=true npm run server:text-to-schematic
```

## 输入输出约定
- 输入：
- `BRIDGE_REQUIREMENT_SPEC_JSON`
- `BRIDGE_COMPONENT_CATALOG_JSON`
- `BRIDGE_EXECUTE_PLAN`
- 输出：
- `.where/pipeline-output/<request-id>/requirement-spec.json`
- `.where/pipeline-output/<request-id>/circuit-model.json`
- `.where/pipeline-output/<request-id>/execution-plan.json`
- `.where/pipeline-output/<request-id>/pipeline-summary.json`

## 后续问题（不阻塞）
- 用真实可放置库件替换占位器件，补全 `library_uuid/symbol_uuid`。
- 在 pin 几何齐全后补齐自动连线策略。
- 增加自动化测试与回归样例（当前阶段按计划暂不做）。
