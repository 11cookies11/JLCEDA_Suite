# LCSC Selection Workflow

本文档定义 `lcsc_selection_v1` 的行为边界。

## 定位

`lcsc_selection_v1` 是一个 agent-assisted workflow template，不是自动下载器。

它只做两件事：

1. 扫描 `source/circuit-model.source.json`
2. 找出缺少 `selected_part.lcsc_id` 的组件并生成 task

## 输入与输出

输入：

- `source/circuit-model.source.json`
- 当前 workflow stack

输出：

- `build/agent-tasks.json`
- workflow status = `waiting_for_agent` 或 `completed`

## agent 处理方式

当 workflow 返回 `needs_selection` 时，agent 应该：

1. 读取 `build/agent-tasks.json`
2. 用 `hwtool agent jlc search` 搜索候选 LCSC
3. 用 `hwtool agent jlc info` 核对封装、库存和描述
4. 通过 `hwtool agent run set_selected_part` 写回 source
5. 重新运行 `hwtool agent workflow run --template lcsc_selection_v1`

## 约束

- 不要把 `display_name` 当成下载 key。
- 下载 key 只有 `selected_part.lcsc_id`。
- 不要在 workflow 里直接改 `build/` 或 `output/`。
- 不要把 `resolve-symbols` 当成这个 workflow 的主步骤。

## Legacy helper

`resolve-symbols` 可以保留为 legacy helper，用于：

- 已经有 `selected_part.lcsc_id` 的部件下载库文件
- 单独验证某个已选器件的本地库可用性

它不再负责 workflow 里的选型决策。
