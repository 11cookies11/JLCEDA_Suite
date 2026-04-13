# 知乎文章素材合集（JLCEDA Suite：文本到原理图的 AI 自动化实验）

本文档用于把当前项目的关键记录与结果“all in one”整理出来，不使用链接，直接把材料内容写入文档，便于直接改写成知乎文章。内容覆盖项目背景、目标、架构、推进过程、关键难点、阶段性成果与收尾总结，并附上原始材料片段。

---

## 一、项目开头：为什么要做这件事

我们的目标不是单做一个插件，而是做一整套“AI + JLCEDA”的硬件开发闭环。核心诉求是让 AI Agent 能从自然语言需求出发，形成理论电路模型，再自动把原理图落到 JLCEDA 上；至于 PCB 的自动化规划先放在后续阶段。项目命名最终暂定为 **JLCEDA Suite**，包含：

1. 插件：负责在 JLCEDA 内执行动作。
2. Server：负责规划、推理与编排。
3. Skill：让 AI Agent 以结构化方式产出内容。

这意味着我们追求的不是“单次输出一张图”，而是可迭代、可回滚、可解释的工程流程。

---

## 二、整体架构与主线设计

### 1) 三层模型（强约束）

项目核心采用三层模型：

1. RequirementSpec：从自然语言结构化需求。
2. CircuitModel：理论电路模型（器件、网络、计算与决策）。
3. ExecutionPlan：可执行的 JLCEDA 操作序列。

设计目标是让每层输入输出清晰且可追溯，避免“插件里做设计推理”。插件只执行动作，server 负责设计与编排。

### 2) 运行方式

目前已有 dry-run 与执行模式：

```
npm run server:text-to-schematic
```

```
BRIDGE_EXECUTE_PLAN=true npm run server:text-to-schematic
```

输入/输出约定：
- 输入：
  - BRIDGE_REQUIREMENT_SPEC_JSON
  - BRIDGE_COMPONENT_CATALOG_JSON
  - BRIDGE_EXECUTE_PLAN
- 输出：
  - .where/pipeline-output/<request-id>/requirement-spec.json
  - .where/pipeline-output/<request-id>/circuit-model.json
  - .where/pipeline-output/<request-id>/execution-plan.json
  - .where/pipeline-output/<request-id>/pipeline-summary.json

---

## 三、阶段性目标与推进路径（简要版）

下面是主线计划的压缩版（来自 where 记录）：

1. 需求结构化：自然语言 -> RequirementSpec。
2. 电路模型生成：RequirementSpec -> CircuitModel。
3. 执行计划编译：CircuitModel -> ExecutionPlan。
4. JLCEDA 落图闭环：插件执行 ExecutionPlan，并回传结果。

当前阶段性里程碑（M1）已经完成：三层模型 v1 落地，最小链路打通。

---

## 四、关键实现点（可写入知乎的技术亮点）

### 1) 自动元件检索 + 质量过滤

通过 system.api_invoke 调用 JLCEDA 内部库搜索接口，将“器件选择”前置到文本阶段：

- 从库中搜索器件候选。
- 结合角色偏好词与参数近似匹配进行打分。
- 在 pin 几何有效时优先选择。

这一步缓解了“文本模型选型正确，但 JLCEDA 无法落地”的断层问题。

### 2) Pin 几何解析与安全连线

自动连线前必须拿到引脚坐标（pin geometry）。目前通过读取符号文件，解析 pin 位置，再映射到元件放置坐标，最终形成 wire 点集：

1. 符号文件解析 pin 坐标。
2. 根据旋转/镜像进行坐标变换。
3. 生成线段点集并调用 schematic.create_wire。

为了避免错误连线，默认开启安全策略：pin 缺失则跳过，并返回 PIN_MISSING。

### 3) 执行闭环 + 状态回传

执行时可选择 dry-run 或执行模式；执行结果回传 pipeline-summary.json，含：
1. 自动检索结果。
2. 线段生成数量。
3. 失败/风险列表。
4. DRC 与 connectivity 结果。

这使得每次落图都有可解释的“状态快照”。

---

## 五、典型实验结果（可直接引用的数据）

以下节选来自最近一次执行结果（requestId: f8224dc7-bcca-4ab1-9c97-367bd562d989）：

1. 自动检索成功：
   - Buck Regulator / 电感 / 电容 / 电阻均找到候选。
2. pin 解析已完成：
   - U1/L1/CIN1/COUT1/RFB1/RFB2 均解析出 pin 数量。
3. 连线生成：
   - Safe wiring 生成了 9 条连线。
4. 但仍存在连接告警：
   - inspect_connectivity 反馈多个 dangling_wire_endpoint。
   - pinCount 在 JLCEDA 返回为 0，说明工具端仍无法识别“真正连接”。

以下为该次 pipeline-summary 中的重要片段（已原样摘录）：

```
REQ parsed goal: Design a buck power stage from 5V to 3.3V at 2A
MODEL synthesized topology: buck
PLAN compiled operations: 25
LAYOUT engine requested: elk
WIRING mode: full
EXEC mode: execute
Auto-search resolved 4 candidates for role buck_regulator (raw=30, strict=8, relaxed=0, mode=strict).
Auto-search resolved 4 candidates for role inductor (raw=30, strict=8, relaxed=0, mode=strict).
Auto-search resolved 4 candidates for role input_capacitor (raw=30, strict=8, relaxed=0, mode=strict).
Auto-search resolved 4 candidates for role output_capacitor (raw=30, strict=8, relaxed=0, mode=strict).
Auto-search resolved 4 candidates for role feedback_resistor_top (raw=30, strict=8, relaxed=0, mode=strict).
Auto-search resolved 4 candidates for role feedback_resistor_bottom (raw=30, strict=8, relaxed=0, mode=strict).
Pin map resolved for U1: 6 pins.
Pin map resolved for L1: 2 pins.
Pin map resolved for CIN1: 2 pins.
Pin map resolved for COUT1: 2 pins.
Pin map resolved for RFB1: 2 pins.
Pin map resolved for RFB2: 2 pins.
Safe wiring generated 9 wire operations.
```

以及自动连线后 connectivity 的问题提示（节选）：

```
dangling_wire_endpoint: Wire endpoint at (682, -422) is not connected.
dangling_wire_endpoint: Wire endpoint at (672, -422) is not connected.
dangling_wire_endpoint: Wire endpoint at (407, -281) is not connected.
dangling_wire_endpoint: Wire endpoint at (1172, -232) is not connected.
dangling_wire_endpoint: Wire endpoint at (698, -272) is not connected.
dangling_wire_endpoint: Wire endpoint at (1422, -272) is not connected.
dangling_wire_endpoint: Wire endpoint at (407, -271) is not connected.
dangling_wire_endpoint: Wire endpoint at (407, -291) is not connected.
dangling_wire_endpoint: Wire endpoint at (1192, -232) is not connected.
dangling_wire_endpoint: Wire endpoint at (1442, -272) is not connected.
zero_length_segment: Wire contains a zero-length segment.
```

---

## 六、最大的技术难点

1. pinName 缺失  
   - 库件符号往往没有 pinName，仅有坐标与 pinNumber。  
   - 这导致网络无法与语义 pin 对齐，连线“看上去连了”，但工具不认。  

2. inspect_connectivity pinCount 为 0  
   - JLCEDA 返回 pinCount=0，使得自动验证失真。  
   - 这让“线是否真正接入 pin”难以自动判断。  

3. 没有 pin-to-pin 直连 API  
   - 只能通过坐标线段连接，无法直接“按 pin 引用连接”。  
   - 必须依赖 pin 几何计算，任何偏差都可能导致连接悬空。  

4. 自动布局与实际布局差距  
   - 自动布局能把元件放在合理区域，但连接逻辑仍不稳定。  
   - 需要在“电路语义与图纸布局”之间建立更强的映射。  

---

## 七、当前状态与里程碑结尾

已完成：
1. 三层模型与执行流程完整落地。
2. 可从文本生成理论电路模型与执行计划。
3. 自动元件检索、pin 几何解析、基础安全连线策略已实现。
4. 输出日志与执行结果形成闭环记录。

仍在攻克：
1. pinName 缺失导致自动连线不可验证。
2. JLCEDA 端连接检测与自动验证不一致。
3. 需要更强的“符号语义映射”或替换更标准化的库件。

---

## 八、收尾与展望（知乎文章结尾可用）

这几天的投入让我们验证了一件事：文本到原理图并不是“把 AI 输出翻译成命令”那么简单。真正的难点在于“模型层到执行层”的语义断层，特别是元件库的 pin 信息与工具端验证机制。  

目前我们已经跑通了理论模型、自动检索、执行闭环，并能在 JLCEDA 内生成实际图纸。但连接准确性仍是关键瓶颈。下一步的方向是：

1. 优先使用“具备完整 pinName 的标准库件”。  
2. 或建立 pinName 映射层，补齐语义。  
3. 在自动连线失败时保持可回退、可追踪的策略。  

对外呈现的价值是：我们搭建了一个可持续迭代的“AI + EDA”工程框架，而不只是一次性 Demo。  

---

## 八点五、问题与解决过程（开发纪要版）

这一段把真实踩坑与解决过程也写进来，便于知乎写作时体现“过程感”和可信度。

1) 插件与服务端连接的问题  
最初插件显示“连接中”，但没有注册/心跳。后来确认服务端需要正常启动并开放本地控制端口，连接状态才稳定显示。  
过程要点：确认服务端运行、控制地址正确、插件已配置本地 ws/http 地址后，连接恢复。

2) 插件名称与定位反复讨论  
项目定位不是单插件，而是“插件 + server + skill”。命名从 “JLCEDA AI Bridge” 逐步收敛到 **JLCEDA Suite**，强调完整套件形态。  
最终在文档、插件信息、仓库命名中统一为 JLCEDA Suite。

3) 插件介绍页与图标缺失  
在插件详情页中发现没有介绍文案与图标，导致用户很难理解插件用途。  
对应调整：补充简介、图标资源与展示信息，保证首次使用可理解。

4) 自动更新不可用  
更新检查曾出现 “Fetch API is not available” 的错误。  
解决思路是补齐运行环境依赖，使更新检查可用，并最终能拉到 release 下载包。

5) 原理图自动放置出框与重复放置  
早期自动放置时，元件会落到框外、并出现重复放置。  
问题原因：多次执行落图时没有切换到新页面，导致同页叠加。  
解决：执行前创建新页并切换到新页执行，从而避免重复叠加。

6) 元件连线不生效、pinCount 为 0  
即使成功画线，JLCEDA 端 inspect_connectivity 返回 pinCount 为 0，提示线端悬空。  
这暴露出核心问题：库件符号 pinName 与几何信息不完整，无法可靠映射 pin。  
解决策略：  
 - 加入 pin 几何解析与坐标变换  
 - pin 缺失时跳过自动连线并返回 PIN_MISSING  
 - 后续尝试“具名 pin 的标准器件”或“pinName 映射层”

7) 连接方式的多次迭代  
连接从 labels-only -> hybrid -> full 多次调整：  
 - labels-only：稳定但不真正连线  
 - hybrid：尝试在同 block 内连线  
 - full：直接按 pin 几何连线  
目前能产生连线，但验证仍依赖 pinName 是否完整。

---

## 九、原始材料内容（where 记录原文）

### 1) where 计划记录（原文）

```
# Plan: JLCEDA Suite（主线：文本 -> JLCEDA）
- [x] L1 主线目标：建立 文本需求 -> 理论电路模型 -> JLCEDA 原理图执行
    - [x] L1.1 自然语言可转结构化需求
    - [x] L1.2 需求可转理论可行电路模型
    - [x] L1.3 电路模型可稳定落图到 JLCEDA（支持 dry-run 与可选执行）
    - [x] L1.4 失败可结构化回传并重规划

- [x] L2 架构分工：server 设计中枢，plugin 仅执行动作，skill 负责编排
    - [x] L2.1 固化三层模型：RequirementSpec / CircuitModel / ExecutionPlan
    - [x] L2.2 固化边界：插件不承担设计推理
    - [x] L2.3 固化原则：仅用可识别 pin 信息器件，不用 fallback pin heuristics

- [x] L3 阶段 A（需求结构化）
    - [x] L3.A1 文本解析为 RequirementSpec
    - [x] L3.A2 约束与验收标准标准化
    - [x] L3.A3 输出统一对象供下游消费
    - [x] L3.A4 记录待确认项并保持可迭代

- [x] L4 阶段 B（理论电路生成）
    - [x] L4.B1 RequirementSpec -> CircuitModel
    - [x] L4.B2 功能块拆分：输入保护/功率级/反馈/输出滤波
    - [x] L4.B3 参数计算与假设记录
    - [x] L4.B4 形成主选/备选器件集合

- [x] L5 阶段 C（执行计划编译）
    - [x] L5.C1 CircuitModel -> ExecutionPlan
    - [x] L5.C2 执行动作拆分：放置/连线/标注/检查
    - [x] L5.C3 错误回传字段定义：器件不可用/pin 缺失/连线失败

- [x] L6 阶段 D（JLCEDA 落图闭环）
    - [x] L6.D1 插件执行 ExecutionPlan（可选执行）
    - [x] L6.D2 server 吸收执行结果并更新模型
    - [x] L6.D3 失败回退并重编译下一版计划（规则已内置）

- [x] L7 当前里程碑：M1 三层模型 v1 落地
    - [x] L7.M1.1 完成 v1 字段定义（Python 主导）
    - [x] L7.M1.2 打通 文本 -> CircuitModel 最小链路
    - [x] L7.M1.3 明确每层输入输出契约

- [x] L8 代码规范：统一并执行编码约定
    - [x] L8.1 新增规范文档 docs/coding-standards.zh-CN.md
    - [x] L8.2 规范映射到 server/plugin/skill 目录约束
    - [x] L8.3 规范映射到错误码、日志、契约版本机制
    - [x] L8.4 后续提交按规范执行并持续更新 where

- [ ] L9 暂不做：测试体系建设（后续单独阶段）
- [ ] L10 暂不做：PCB 自动化

- [~] L11 后续问题清单（不阻塞当前推进）
    - [x] L11.1 自动库检索已接入（system.api_invoke + LIB 搜索）
    - [~] L11.2 基于 pin 集合的安全连线已接入（pin 缺失时自动跳过并输出 PIN_MISSING）
    - [ ] L11.3 增加端到端自动化测试与回归样例
    - [x] L11.4 自动检索质量基础过滤已落地（角色打分/排除词/参数近似匹配）
```

### 2) development-plan 原文（原样）

```
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
```

---

## 十、知乎文章标题建议（备用）

1. 做了几天后，我终于看清“AI 自动画原理图”的真正难点  
2. 从文本到原理图：JLCEDA + AI 的一次工程化实验  
3. 自动连线为什么难：一个“文本到原理图”的实战记录  
