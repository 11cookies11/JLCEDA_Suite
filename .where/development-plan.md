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

## ngspice 仿真开发计划

### 目标
- 以 `ngspice` 作为第一阶段仿真主力，打通 `CircuitModel -> Netlist -> SPICE -> 仿真结果` 的最小闭环。
- 让仿真结果可结构化回写到模型与规则层，作为 AI 重新生成和审查的依据。

### 当前范围
- 第一阶段只覆盖中小规模模拟电路的基础验证。
- 先支持 `.op`、`.tran`、`.ac` 三类分析。
- 先把“连接真值”和“仿真输入”分层，不把布局信息混进 netlist。

### 后续子任务
- 定义仓库内部 `Netlist` schema。
- 编写 `Netlist -> SPICE` 导出器。
- 封装 `ngspice` 命令行执行与结果解析。
- 把仿真失败原因回写到 `CircuitModel.risks`。
- 补充最小回归样例。

## skill reference tree plan

### Goal
- Split the skill reference material into small, independently usable documents.
- Let each mode load only the references it needs.

### Current scope
- Add five companion docs: requirement clarification, strap and bias rules, netlist guidelines, simulation guidelines, and decision log template.
- Map them from `SKILL.md`.
- Reference them from `text-to-schematic.md`.

### Next tasks
- Add examples and anti-examples for each new reference.
- Keep the skill workflow and where status in sync.

## ngspice netlist handoff

- `server/schemas/netlist.v1.json` is landed.
- `scripts/server_text_to_schematic.py` now emits `netlist.json` in the pipeline output bundle.
- `server/schemas/spice-netlist.v1.json` is landed.
- `scripts/server_text_to_schematic.py` now emits `spice-netlist.cir` and `spice-netlist.json`.
- `server/schemas/ngspice-execution.v1.json` is landed.
- `server/schemas/ngspice-feedback.v1.json` is landed.
- `scripts/server_text_to_schematic.py` now emits `ngspice-execution.json`, `ngspice-execution.log`, and `ngspice-feedback.json`.
- ngspice execution, parsing, and feedback backwrite are landed in `scripts/server_text_to_schematic.py`.
- `tests/fixtures/ngspice/regression-samples.json` is landed.
- `scripts/ngspice-regression-test.py` is landed and exposed as `npm run server:ngspice:regression-test`.

