# 11 circuit-model 格式规范

Status: Draft

## 目的

- 约定 `circuit-model.json` 的固定结构。
- 统一后续模型填写口径，避免同一类信息在不同文件里重复发散。
- 让 example 的虚拟电路始终保持可被流水线解析、可被人工审阅、可被后续原理图阶段承接。

## 顶层字段

`circuit-model.json` 必须包含以下顶层字段：

1. `schema_version`
- 记录模型版本。

2. `request_id`
- 记录本次建模请求或任务标识。

3. `project_id`
- 记录示例项目标识。

4. `topology`
- 描述整板功能拓扑、模块边界和主要连接关系。

5. `components`
- 记录器件、连接器、测试点、开关、晶体等对象。

6. `nets`
- 记录全局网络、模块间关键连接和约束关系。

7. `calculations`
- 记录电流预算、功耗、余量和其他可追溯计算。

8. `design_decisions`
- 记录设计取舍、保留策略和定版依据。

9. `risks`
- 记录当前模型仍需确认的风险项。

## `components` 填写规则

每个 `component` 建议包含以下信息：

- `ref`
- `role`
- `value`
- `selected_part`
- `candidate_parts`
- `availability_status`
- `notes`

### 建议原则

- `ref` 要稳定，尽量与原理图分图一致。
- `role` 要描述功能，不要只写通用封装名。
- `value` 要能让人一眼看出器件用途。
- `selected_part` 用于记录已经倾向或确认的器件。
- `candidate_parts` 用于保留备选方案。
- `availability_status` 只表达当前状态，不做最终承诺。

## `nets` 填写规则

每个 `net` 建议包含以下信息：

- `name`
- `members`
- `notes`

### 建议原则

- `name` 要能表达用途，例如电源、时钟、复位、启动、调试、外设总线。
- `members` 只放该网络应连接的端点。
- `notes` 用于补充拓扑约束、时序要求或参考设计说明。

## `calculations` 填写规则

每个 `calculation` 建议包含以下信息：

- `name`
- `formula`
- `inputs`
- `result`
- `unit`

### 建议原则

- 所有关键电源预算都应进入 `calculations`。
- 计算项要可复核，尽量写出输入和公式。
- 如果数值仍是估算，应在相关 `notes` 中说明来源。

## `design_decisions` 填写规则

每个 `design_decision` 建议包含以下信息：

- `title`
- `rationale`
- `impact`

### 建议原则

- `title` 要短，尽量是一个明确的设计判断。
- `rationale` 要写清楚为什么这样做。
- `impact` 要说明这一决定对调试、布线、风险或扩展性的影响。
- 如果仍未最终拍板，必须在 `rationale` 中明确写出 `Can continue` 或 `Need review`。

## `risks` 填写规则

`risks` 使用字符串数组，适合记录：

- 还未最终确认的参考设计依赖
- 还未落实的器件级连接
- 可能影响 bring-up 成功率的关键不确定项
- 仍需软件协同确认的 pinmux 或启动路径问题

### 建议原则

- 语言要短，不要写成长段落。
- 每条风险只描述一件事。
- 如果风险可以继续推进，就用 `Can continue` 开头。
- 如果风险必须等待确认，就用 `Need review` 开头。

## 模型组织原则

- `circuit-model.json` 保持单文件，不拆成多个物理文件。
- 文件内部按模块逻辑组织，例如：
  - 电源
  - 启动
  - DDR
  - 调试
  - 网络
  - USB
  - 扩展口
- 同一类信息不要分散在多个顶层数组里重复描述。
- 任何还没有最终确认的项，都应保留为可追溯的风险或备注，而不是假装已经定版。

## 与后续阶段的关系

- `circuit-model.json` 负责表达“要做什么”和“为什么这样做”。
- 原理图负责表达“实际怎么接”。
- PCB 负责表达“实际怎么摆、怎么布线”。
- bring-up 负责验证前面两层是否真的成立。

## 本示例的当前约定

`examples/h618-agentboard-v1/circuit-model.json` 目前已经采用这套结构，后续新增内容应继续沿用同一口径。
