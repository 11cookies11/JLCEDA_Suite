# Agent LCSC Selection Workflow

本文档定义 agent 如何处理 `resolve-symbols` 返回的 `needs_selection`，并把 LCSC 选型集成到现有工程流中。

## 核心边界

`resolve-symbols` 是确定性的下载器，不是自动选型器。

- 输入：`source/circuit-model.source.json` 中每个组件的 `selected_part.lcsc_id`。
- 输出：项目本地 `libraries/`、`build/circuit-model.resolved.json`、resolver-owned 字段。
- 缺少 `selected_part.lcsc_id` 时：返回 `needs_selection`，不猜测、不占位、不自动搜索。

Agent 是选型决策层。

- 读取工程上下文、组件角色、网络、封装、已有候选和诊断结果。
- 使用 `hwtool agent jlc search` 与 `hwtool agent jlc info` 查询候选。
- 根据工程约束选择 LCSC ID。
- 通过 Model API 写回 `selected_part`，不要直接编辑 generated 文件。

## 推荐流程

从工程根目录执行：

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent resolve-symbols --project . --timeout 120
```

如果 `resolve-symbols` 返回 `needs_selection`：

1. 收集缺少 `selected_part.lcsc_id` 的组件。
2. 从 `source/circuit-model.source.json`、sheet、net、role、value、package、notes、search_hints 中提取选型上下文。
3. 对每个组件执行 `hwtool agent jlc search "<query>" -n 5`。
4. 对候选执行 `hwtool agent jlc info <C...>`，确认 MPN、封装、库存/状态、描述和风险。
5. 通过 `set_selected_part` 写回 source model。
6. 重新运行 `resolve-symbols`。
7. 继续 `build-ir -> validate-ir -> export-kicad -> report -> diagnose`。

写回示例：

```powershell
hwtool agent run set_selected_part --project . --payload-json '{
  "ref": "R1",
  "part": {
    "lcsc_id": "C22843",
    "display_name": "10k 1% 0603 resistor",
    "mpn": "0603WAF1002T5E",
    "manufacturer": "UNI-ROYAL",
    "package": "0603"
  }
}'
```

## 选型规则

Agent 选择 LCSC ID 时必须遵守以下规则：

- 不根据 `display_name` 当作可下载标识；下载 key 只能是 `selected_part.lcsc_id`。
- 不盲选搜索结果第一项；至少检查封装、值、角色和描述。
- 组件已有明确 MPN 时，优先搜索 MPN 并匹配精确结果。
- 电阻、电容等被工程规则指定为 0603 时，候选封装必须与 0603 规则一致。
- MCU、连接器、天线、晶振、ESD、稳压器、电感、保险丝等高风险器件，缺少确定匹配时标记为需要人工确认，而不是强行写入。
- 选型后不要手写 `selected_part.symbol_ref` 和 `selected_part.kicad_footprint_hint`，这些字段由 resolver 维护。

## 数据所有权

Source-owned 字段由 agent 或用户维护：

- `selected_part.lcsc_id`
- `selected_part.display_name`
- `selected_part.mpn`
- `selected_part.manufacturer`
- `selected_part.package`
- `selected_part.notes`
- `selected_part_locked`

Resolver-owned 字段由 `resolve-symbols` 维护：

- `selected_part.symbol_ref`
- `selected_part.kicad_footprint_hint`
- downloaded library references under `libraries/`
- resolved overlay under `build/circuit-model.resolved.json`

Generated 文件不要作为选型写入点：

- 不编辑 `build/`
- 不编辑 `output/`
- 不把 root-level `circuit-model.json` 用作新项目入口

## 架构位置

当前软件边界应保持如下：

- Agent / Skill：理解工程意图、搜索 LCSC、判断候选、发起 Model API 操作。
- CLI：暴露 `jlc search`、`jlc info`、`agent run`、`resolve-symbols` 等稳定命令。
- Model API：通过 `set_selected_part`、`add_candidate_part`、`lock_selected_part` 等操作安全修改 source model。
- Part Resolution Service：读取已选 LCSC ID，调用 JLC/EasyEDA 下载器，写 resolved overlay。
- IR / Validation / Export：只消费 source + resolved overlay，不参与选型决策。

这个设计避免两个问题：

- Resolver 自动猜器件会把不确定选择伪装成“已解析”，后续 KiCad 导出看起来成功但硬件可能错误。
- Agent 直接改 generated 文件会破坏可重复构建，下一次 pipeline 运行会覆盖这些修改。

## 后续编排入口

建议把 LCSC 选型流程接入 agent-assisted workflow，而不是让 agent 手工串所有命令。第一版入口：

```powershell
hwtool agent workflow run --template lcsc_selection_v1 --project .
```

该 workflow 每次从当前 source/build/libraries 状态重新计算下一步：

- 已经有 LCSC 且资源有效的组件跳过。
- 有 LCSC 但资源缺失的组件继续下载。
- 缺少 LCSC 的组件写入 `build/agent-tasks.json` 并返回 `waiting_for_agent`。
- Agent 根据 tasks 搜索 LCSC，通过 `set_selected_part` 写回 source 后，再次运行同一个 workflow。

第一版不需要 `resume`、`cursor` 或 `agent-decisions.json`。真实决策保存在 `source/circuit-model.source.json`，workflow run 保持幂等。
Workflow stack 状态由 `hwtool agent status` 和 `hwtool agent workflow status` 暴露，用于告诉 agent 当前活动 workflow 和 pending task。
