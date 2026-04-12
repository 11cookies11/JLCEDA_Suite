# 文本到 JLCEDA 管线

该管线用于把 AI Agent 的结构化设计输入转换为可执行的原理图落图步骤。

主链路：
- `RequirementSpec`（需求层）
- `CircuitModel`（理论层）
- `ExecutionPlan`（执行层）

实现入口：
- `scripts/server_text_to_schematic.py`

## 环境变量
- `BRIDGE_REQUIREMENT_SPEC_JSON`：需求 JSON
- `BRIDGE_COMPONENT_CATALOG_JSON`：器件候选 JSON
- `BRIDGE_AUTO_SEARCH_LIB`：`true/false`，未提供候选时自动搜索库件（默认 `true`）
- `BRIDGE_ENABLE_SAFE_WIRING`：`true/false`，启用基于 pin 集合的安全连线（默认 `true`）
- `BRIDGE_EXECUTE_PLAN`：`true/false`
- `BRIDGE_CONTROL_URL`：默认 `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`：可选
- `BRIDGE_TARGET_CLIENT_ID`：可选
- `BRIDGE_PIPELINE_OUTPUT_DIR`：默认 `.where/pipeline-output`

## 回退机制
- `PART_UNAVAILABLE`
- `PIN_MISSING`
- `WIRE_FAILED`
- `EXECUTION_FAILED`

## 自动检索说明
- 管线会优先使用手工提供的 `BRIDGE_COMPONENT_CATALOG_JSON`。
- 若某个角色缺少候选且 `BRIDGE_AUTO_SEARCH_LIB=true`，将通过 `system.api_invoke` 调用库检索接口自动补全候选。
- 自动检索的结果会写入 `circuit-model.json` 的 `candidate_parts`，并在 `pipeline-summary.json` 的 `log` 中记录。
- 自动检索会执行基础质量过滤：按角色关键词加权、排除词过滤、参数近似匹配（如 22uF/4.7uH/电阻值）与 `pin_count` 优先级排序。

## 安全连线说明
- 管线会尝试读取符号文件并解析 pin 集合。
- 仅当网表两端 pin 都能匹配到具体坐标时，才生成 `create_wire` 操作。
- 当 pin 缺失或不可解析时，不强行连线，改为记录 `PIN_MISSING` 问题并保留网标策略。

## 当前已知限制
- 未提供库件映射时，只会生成占位模型并进入 dry-run 友好模式。
- pin 几何不完整时，不强行自动连线，优先输出结构化风险与下一步建议。
