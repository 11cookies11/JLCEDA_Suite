# Agent-Assisted Workflow Design

本文档整理 agent、CLI、内部编排层如何协同工作。目标是在不破坏现有原子命令的前提下，把可重复的流程收回到软件内部，把不确定的判断交给 agent。

## 设计目标

- 软件提供 workflow template，而不是让 agent 自由串命令。
- Workflow run 可以安全重复执行，已经完成的部分跳过，未完成的部分继续推进。
- Agent 只在明确的决策点介入，例如 LCSC 选型、风险确认、诊断修复。
- Source model 是真实状态；`build/`、`libraries/`、`output/` 是生成状态和缓存。
- 第一版不做复杂 `resume`、`cursor`、`agent-decisions.json`；agent 处理后重新运行同一个 workflow。

## 分层职责

```text
Skill / AGENTS.md
  说明可用 workflow template、适用场景、决策规则和禁止事项。

Agent CLI
  提供稳定入口，例如 workflow run/status、jlc search/info、agent run set_selected_part。

Workflow Orchestration
  根据模板扫描项目状态，执行确定性步骤，生成 agent tasks，返回结构化状态。

Application Services
  提供 PartResolutionService、ModelApiService、Report/Diagnose 等原子能力。

Adapters
  封装 JLC/EasyEDA/KiCad/ngspice/filesystem 等外部系统。
```

## 通用执行模型

Workflow 不是 LCSC 专用机制。LCSC 选型、ERC 报错处理、IR validation 修复、diagnose repair loop 都应走同一套模式：

```text
workflow template
-> scan current project state
-> run deterministic steps
-> emit structured agent tasks when judgement is needed
-> agent writes source through Model API
-> rerun same workflow
```

## Workflow Stack

复杂任务使用轻量 workflow stack 管理嵌套关系。Stack 只保存 workflow 层级，不保存每个 step 的 cursor。

内部状态文件：

```text
build/agent-workflow-stack.json
```

Agent 不需要直接读取该文件。统一从下面两个入口看状态：

```powershell
hwtool agent status --project .
hwtool agent workflow status --project .
```

运行规则：

```text
没有 stack 时：用 --template 初始化主 workflow。
有 stack 时：运行栈顶 workflow。
栈顶 completed：pop。
栈顶 waiting_for_agent：停止并返回 tasks_file。
栈顶 failed：停止并返回 failed。
```

第一版已经实现 stack 状态管理，但仍然保持幂等 workflow run，不保存 step cursor。

第一版采用幂等 workflow run：

```powershell
hwtool agent workflow run --template lcsc_selection_v1 --project .
```

每次运行都从当前文件状态重新计算下一步。以 LCSC workflow 为例：

```text
读取 source/circuit-model.source.json
-> 检查每个 component 的 selected_part.lcsc_id
-> 已完成且资源存在：skip
-> 有 lcsc_id 但资源缺失：download
-> 无 lcsc_id：生成 agent task
-> 如果存在 agent task：返回 waiting_for_agent
-> 如果全部完成：返回 completed
```

Agent 看到 `waiting_for_agent` 后处理任务，直接通过 Model API 写回 source。处理完后再次运行同一个 workflow。

```powershell
hwtool agent workflow run --template lcsc_selection_v1 --project .
```

这个模型不需要保存复杂恢复点，因为 source model 已经承载了 agent 的真实决策。

同样的模型也适用于 ERC/diagnose：

```text
run diagnose
-> no must_fix/review_required: completed
-> must_fix exists: write agent repair tasks
-> review_required exists: write agent review tasks
-> agent applies patch/run operations through Model API
-> rerun same workflow
```

## 状态语义

顶层 workflow 返回值：

```json
{
  "ok": false,
  "workflow_id": "lcsc_selection_v1",
  "status": "waiting_for_agent",
  "reason": "needs_selection",
  "tasks_file": "build/agent-tasks.json",
  "rerun_after_agent": true
}
```

推荐状态：

- `completed`：当前 workflow 已完成。
- `waiting_for_agent`：未失败，但需要 agent 决策后重新运行。
- `waiting_for_user`：需要用户确认，agent 不应自行继续。
- `blocked`：缺少必要外部条件或人工信息。
- `failed`：确定性步骤失败。

`ok` 表示顶层 workflow 是否已经成功完成：

- `ok=true,status=completed` 表示完成。
- `ok=false,status=waiting_for_agent` 表示暂停等待 agent，不是失败。
- `ok=false,status=failed` 表示失败。

## Agent 接手信号

Codex 不需要后台监听文件。它运行 CLI 后，根据返回 JSON 判断是否接手：

```text
status=completed
  不接手，workflow 结束。

status=waiting_for_agent
  读取 tasks_file，执行搜索/判断/写回 source，然后重新运行同一个 workflow。

status=waiting_for_user
  停止并向用户说明需要确认。

status=failed
  根据错误进入诊断或修复流程。
```

这要求 CLI 输出明确字段，而不是让 agent 从普通日志中猜测。

## Agent Tasks

`build/agent-tasks.json` 是编排层交给 agent 的结构化任务文件。所有 workflow 共用同一个任务文件结构。

通用字段：

```json
{
  "schema_version": "agent_tasks.v1",
  "workflow_id": "lcsc_selection_v1",
  "project": ".",
  "tasks": []
}
```

LCSC 选型任务示例：

```json
{
  "schema_version": "agent_tasks.v1",
  "workflow_id": "lcsc_selection_v1",
  "tasks": [
    {
      "task_id": "select_lcsc:R1",
      "type": "agent_decision",
      "decision_schema": "select_lcsc_part_v1",
      "component": {
        "ref": "R1",
        "role": "pullup_resistor",
        "value": "10k",
        "package": "0603",
        "search_hints": ["10k resistor 0603"]
      },
      "allowed_actions": ["select", "needs_human_review", "skip"]
    }
  ]
}
```

Agent 处理 task 时不直接编辑 generated 文件，而是调用：

```powershell
hwtool agent jlc search "10k resistor 0603" -n 5
hwtool agent jlc info C22843
hwtool agent run set_selected_part --project . --payload-json '{...}'
```

ERC/diagnose 修复任务示例：

```json
{
  "schema_version": "agent_tasks.v1",
  "workflow_id": "repair_after_diagnose_v1",
  "tasks": [
    {
      "task_id": "repair:erc:POWER_INPUT_NOT_DRIVEN:U1",
      "type": "agent_repair",
      "decision_schema": "repair_diagnostic_v1",
      "diagnostic": {
        "source": "erc",
        "bucket": "must_fix",
        "code": "POWER_INPUT_NOT_DRIVEN",
        "message": "Power input pin is not driven.",
        "refs": ["U1"],
        "nets": ["+3V3"]
      },
      "allowed_actions": [
        "apply_model_operation",
        "needs_human_review",
        "mark_library_noise"
      ],
      "allowed_operations": [
        "connect_member",
        "set_net_kind",
        "update_component",
        "set_selected_part"
      ]
    }
  ]
}
```

Agent 修复时仍然通过受控入口写 source：

```powershell
hwtool agent run connect_member --project . --payload-json '{...}'
hwtool agent run update_component --project . --payload-json '{...}'
hwtool agent patch --project . --payload-json '{...}'
```

编排层不直接写特殊 ERC 修复逻辑；它只把诊断结果转成结构化 agent task。

## Template 切入点

模板提前声明可能出现的 agent 切入类型，运行时由编排层按结果生成具体任务。

- `agent_decision`：多个候选中选择，例如 LCSC 选型。
- `agent_review`：流程能继续但有风险，需要判断是否继续。
- `agent_repair`：validate/diagnose 失败，需要生成修复操作。

第一版可以只实现 `agent_decision` 中的 `select_lcsc_part_v1`，但文件结构和 service API 必须按通用任务设计，避免后续 ERC/diagnose 再另起一套机制。

## Template 目录

建议把模板注册成稳定 ID：

```text
lcsc_selection_v1
  补齐 selected_part.lcsc_id 并下载本地库。

repair_after_diagnose_v1
  读取 diagnose 输出，把 must_fix/review_required 转为 agent_repair/agent_review task。

full_build_v1
  status -> inspect -> diagnose -> lcsc_selection -> build-ir -> validate-ir -> export-kicad -> report -> diagnose。
```

第一版实现 `lcsc_selection_v1` 时，`workflow_templates.py` 仍应保留这些模板 metadata 的位置：

```text
id
description
supported_task_types
deterministic_steps
agent_cut_points
```

## LCSC Selection v1

`lcsc_selection_v1` 目标是补齐 `selected_part.lcsc_id` 并下载项目本地库。

确定性步骤：

```text
load_source_model
scan_components
resolve_existing_lcsc_parts
build_needs_selection_tasks
write_agent_tasks
return completed or waiting_for_agent
```

Agent 决策步骤：

```text
read build/agent-tasks.json
jlc search/info
agent run set_selected_part
rerun workflow
```

完成条件：

```text
没有 needs_selection
没有 failed downloads
已有 LCSC 的组件均已解析到 project-local libraries / resolved overlay
```

## Repair After Diagnose v1

该模板后续用于 ERC/IR/diagnose 修复，不在第一版强制实现，但代码设计必须兼容。

确定性步骤：

```text
run diagnose
read diagnostics.must_fix / diagnostics.review_required / diagnostics.library_noise
if no must_fix and no review_required: completed
if must_fix: emit agent_repair tasks
if review_required: emit agent_review tasks
return waiting_for_agent or waiting_for_user
```

Agent 处理方式：

```text
read build/agent-tasks.json
decide repair operation
call hwtool agent run/patch
rerun workflow
```

关键边界：

- `library_noise` 默认不让 agent 修改 source，除非诊断明确指出真实电气问题。
- ERC pin type、symbol normalization、footprint repair 等一类问题应进入专门 service，不在 workflow 中写一堆 if/else。
- Workflow 只负责任务生成和状态推进，不负责具体修复策略。

## 为什么第一版不做 Resume

完整 resume 需要保存 cursor、step graph、decision 文件和恢复逻辑。当前需求可以用更简单的方式满足：

```text
source 保存真实决策
workflow run 每次重新扫描 source
已完成项跳过
未完成项继续生成 task
```

这样实现更快、更容易测试，也符合文件式工程架构。后续如果重跑成本过高，再引入：

```text
build/agent-workflow-state.json
build/agent-decisions.json
hwtool agent workflow resume
```

## 代码落点

建议新增：

```text
src/kicad_suite/orchestration/agent_workflow.py
src/kicad_suite/orchestration/workflow_templates.py
src/kicad_suite/orchestration/agent_tasks.py
```

建议新增 CLI：

```powershell
hwtool agent workflow run --template lcsc_selection_v1 --project .
hwtool agent workflow status --project .
```

第一版不实现：

```powershell
hwtool agent workflow resume --project .
```

后续再扩展：

```text
full_build_v1
repair_after_diagnose_v1
agent_review
agent_repair
workflow cache / state
```

实现约束：

- `cli.py` 只解析参数并调用 orchestration service。
- `jlc_installer.py` 只负责按 LCSC 下载，不参与 agent task 生成。
- `agent_diagnostics.py` / `ErcClassificationService` 继续负责诊断分类。
- `ModelApiService` 继续作为 source 写入入口。
- 不在 workflow 中散落 one-off ERC/symbol/footprint 修复逻辑。
