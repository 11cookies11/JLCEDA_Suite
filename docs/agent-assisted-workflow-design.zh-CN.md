# Agent Assisted Workflow Design

本文档描述 KiCad Agent Suite 里 workflow、agent、CLI 和 Model API 的边界。

## 目标

- workflow 负责编排和状态推进，不负责工程判断本身。
- agent 负责选型、修复决策和人工不可替代的判断。
- CLI 负责稳定入口，不负责业务策略。
- Model API 负责把 agent 的决策写回 `source/circuit-model.source.json`。

## 核心原则

1. workflow 只做确定性步骤。
2. 需要判断时，workflow 产出结构化 task。
3. agent 读取 task，通过 Model API 修改 source。
4. 同一 workflow 重新运行，重新扫描当前 source 状态。
5. `build/` 和 `output/` 只保存生成结果，不作为真值来源。

## Workflow Stack

复杂任务使用轻量 stack 处理嵌套关系。

```text
build/agent-workflow-stack.json
```

Stack 只记录 workflow 层级，不记录每个 step 的 cursor。
推荐通过这两个入口查看状态：

```powershell
hwtool agent status --project .
hwtool agent workflow status --project .
```

常见状态：

- `completed`: 当前 workflow 结束，按 stack 继续或退出。
- `waiting_for_agent`: 已生成 task，等待 agent 处理。
- `waiting_for_user`: 需要人工确认。
- `blocked`: 缺少必要外部条件。
- `failed`: 确定性步骤失败。

## 当前模板

### `full_build_v1`

主流程模板。职责：

- 检查 source 状态
- 发现缺失 LCSC 或诊断问题
- 根据结果派生 route task
- 在子 workflow 处理完成后继续

### `lcsc_selection_v1`

LCSC 选型模板。职责：

- 扫描缺失 `selected_part.lcsc_id` 的组件
- 生成 `agent_decision` task
- 等待 agent 通过 Model API 写回 source

这个模板不再把 `resolve-symbols` 当作 workflow 必经步骤。
`resolve-symbols` 只是一个 legacy helper，用于已经选好 LCSC 的情况下下载本地库。

### `repair_after_diagnose_v1`

诊断修复模板。职责：

- 读取 `diagnose` 结果
- 把 `must_fix` 变成 `agent_repair`
- 把 `review_required` 变成 `agent_review`

### `unknown_task_v1`

兜底模板。职责：

- 让 agent 分类当前未知条件
- 选择后续 workflow
- 或者请求人工确认

## Route Decision

当主 workflow 遇到分支时，会先推入一个 route placeholder。
agent 通过 `choose-route` 选择实际模板：

```powershell
hwtool agent workflow choose-route --project . --workflow lcsc_selection_v1
```

这一步只是替换当前 route frame，不会增加额外的状态复杂度。

## 为什么不做 Resume

第一版先不做 step 级 resume，原因是：

- source 本身就是可重放的真值
- workflow 每次都从当前 source 重新扫描
- 已完成部分会自然跳过
- 未完成部分会重新产出 task

这样更容易测试，也更符合文件型工程流。

## 代码落点

- `src/kicad_suite/orchestration/agent_workflow.py`
- `src/kicad_suite/orchestration/workflow_templates.py`
- `src/kicad_suite/orchestration/agent_tasks.py`

## 实现约束

- 不要在 workflow 里写 one-off ERC 或 footprint 修复逻辑。
- 不要把 `resolve-symbols` 视为 workflow 主步骤。
- 不要把 `build/` 或 `output/` 当成 source truth。
- 所有判断都要回写到 source，然后重跑 workflow。
