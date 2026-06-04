# DSL API 设计文档

Status: Draft

## 1. 目标

本文定义 `CircuitModel DSL` 的 API 设计，目标是把“AI agent 直接编辑 JSON”改造成“AI agent 通过受控 API 操作模型”。

这套 API 的核心任务不是单纯读写 JSON，而是把以下能力封装成稳定服务：

- 维护 `source/circuit-model.source.json` 及其版本演进
- 对器件、网络、分图、决策、风险、计算做结构化操作
- 对 schema、引用关系、电源树、pinmap、分图边界做校验
- 对后续的 netlist、KiCad execution plan、ERC、仿真计划提供编译入口
- 为 agent 提供更稳的事务、差分、回滚和诊断能力

## 2. 设计原则

- **文件仍是事实源**：最终落盘对象仍然是 `source/circuit-model.source.json` 和相关导出文件。
- **API 负责约束**：agent 不直接拼整份 JSON，而是调用有边界的操作。
- **schema 驱动**：所有对象都带 `schema_version`，并接受结构化验证。
- **先校验再落盘**：API 允许 `dry_run`、`validate`、`commit` 三种节奏。
- **可回滚**：任何批量修改都应支持事务和回滚。
- **可追踪**：所有修改都应能关联 `request_id`、`project_id`、`topology` 和 change log。
- **向后兼容优先**：新增字段优先保持兼容，再升级必填字段。

## 3. API 提供的服务

### 3.1 模型生命周期服务

负责加载、保存、克隆、比较和验证模型。

建议能力：

- `load_model`
- `save_model`
- `clone_model`
- `reset_model`
- `diff_model`
- `merge_model`
- `patch_model`
- `validate_model`
- `validate_schema`

这层是所有其他服务的基础。

### 3.2 项目元信息服务

负责维护模型顶层字段。

建议能力：

- `get_metadata`
- `set_schema_version`
- `set_request_id`
- `set_project_id`
- `set_topology`
- `update_metadata`

目标是保证跨阶段输出能稳定关联到同一个工程。

### 3.3 器件服务

负责 `components[]` 的增删改查和选型收口。

建议能力：

- `add_component`
- `update_component`
- `remove_component`
- `get_component`
- `list_components`
- `search_components`
- `set_component_ref`
- `set_component_role`
- `set_component_value`
- `set_component_notes`
- `set_component_availability`
- `set_selected_part`
- `add_candidate_part`
- `remove_candidate_part`
- `assign_component_to_sheet`
- `mark_component_resolved`
- `mark_component_needs_review`
- `mark_component_blocked`

适合管理的字段包括：

- `ref`
- `role`
- `value`
- `selected_part`
- `candidate_parts`
- `availability_status`
- `notes`

### 3.4 网络服务

负责 `nets[]` 的命名、连接和语义约束。

建议能力：

- `add_net`
- `update_net`
- `remove_net`
- `get_net`
- `list_nets`
- `search_nets`
- `connect_member`
- `connect_members`
- `disconnect_member`
- `disconnect_members`
- `rename_net`
- `merge_nets`
- `split_net`
- `set_net_kind`
- `set_net_notes`
- `set_net_aliases`
- `set_net_domain`
- `mark_net_global`
- `mark_net_power`
- `mark_net_high_speed`
- `mark_net_debug`
- `mark_net_differential_pair`
- `assign_net_to_sheet`

这层要把“网络名”与“电气约束语义”一起保存，而不是只存字符串。

### 3.5 引脚与 Pinmap 服务

负责把器件脚位与网络建立明确、可验证的映射。

建议能力：

- `set_pinmap`
- `update_pinmap`
- `remove_pinmap`
- `get_pinmap`
- `validate_pinmap`
- `connect_pin_to_net`
- `disconnect_pin_from_net`
- `set_pin_name`
- `set_pin_role`
- `set_pin_direction`
- `set_pin_no_connect`
- `add_pin_alias`
- `resolve_pin_alias`

这层对 H618 / LPDDR4 / PMIC / PHY / USB Hub 这类项目尤为关键。

### 3.6 电源树服务

负责电源域、供电关系、上电次序和电源预算。

建议能力：

- `add_power_rail`
- `update_power_rail`
- `remove_power_rail`
- `get_power_rail`
- `list_power_rails`
- `set_rail_source`
- `set_rail_sink`
- `set_rail_parent`
- `set_rail_children`
- `set_rail_voltage`
- `set_rail_current_limit`
- `set_rail_sequence_order`
- `set_rail_enable_condition`
- `add_rail_test_point`
- `bind_rail_to_test_point`
- `validate_power_tree`
- `validate_power_budget`
- `validate_sequence`

### 3.7 分图与模块服务

负责将模型映射到 KiCad 分图职责边界。

建议能力：

- `add_sheet`
- `update_sheet`
- `remove_sheet`
- `get_sheet`
- `list_sheets`
- `search_sheets`
- `set_sheet_name`
- `set_sheet_inputs`
- `set_sheet_outputs`
- `set_sheet_components`
- `set_sheet_nets`
- `set_sheet_constraints`
- `set_sheet_notes`
- `validate_sheet_boundary`
- `validate_sheet_inputs_outputs`

### 3.8 计算服务

负责可追溯的工程预算与公式计算。

建议能力：

- `add_calculation`
- `update_calculation`
- `remove_calculation`
- `get_calculation`
- `list_calculations`
- `recompute_calculation`
- `set_calculation_formula`
- `set_calculation_inputs`
- `set_calculation_result`
- `set_calculation_unit`
- `link_calculation_to_component`
- `link_calculation_to_net`

### 3.9 设计决策服务

负责记录“为什么这么做”。

建议能力：

- `add_design_decision`
- `update_design_decision`
- `remove_design_decision`
- `get_design_decision`
- `list_design_decisions`
- `search_design_decisions`
- `mark_decision_proposed`
- `mark_decision_accepted`
- `mark_decision_rejected`
- `mark_decision_needs_review`
- `mark_decision_finalized`
- `link_decision_to_component`
- `link_decision_to_net`
- `link_decision_to_risk`
- `link_decision_to_sheet`

### 3.10 风险服务

负责把未定事项、待确认项和阻塞项显式化。

建议能力：

- `add_risk`
- `update_risk`
- `remove_risk`
- `get_risk`
- `list_risks`
- `search_risks`
- `mark_risk_open`
- `mark_risk_in_progress`
- `mark_risk_blocked`
- `mark_risk_resolved`
- `mark_risk_deferred`
- `set_risk_category`
- `set_risk_severity`
- `set_risk_owner`
- `set_risk_due_reason`
- `link_risk_to_component`
- `link_risk_to_net`
- `link_risk_to_decision`
- `link_risk_to_sheet`

### 3.11 约束服务

负责把工程规则从文档变成可执行约束。

建议能力：

- `add_constraint`
- `update_constraint`
- `remove_constraint`
- `get_constraint`
- `list_constraints`
- `set_constraint_type`
- `set_constraint_scope`
- `set_constraint_priority`
- `set_constraint_status`

常见约束类型包括：

- `power_sequence_constraint`
- `pinmap_constraint`
- `net_class_constraint`
- `high_speed_constraint`
- `placement_constraint`
- `sheet_boundary_constraint`
- `part_availability_constraint`

### 3.12 采购与器件选择服务

负责选型、备选和锁定。

建议能力：

- `select_part`
- `update_selected_part`
- `replace_selected_part`
- `add_candidate_part`
- `remove_candidate_part`
- `lock_selected_part`
- `unlock_selected_part`
- `validate_part_availability`
- `link_part_to_component`

### 3.13 校验服务

负责把模型变成“可以继续推进”的状态。

建议能力：

- `validate_schema`
- `validate_references`
- `validate_connectivity`
- `validate_pinmap`
- `validate_power_tree`
- `validate_sheet_boundary`
- `validate_part_availability`
- `validate_risk_consistency`
- `validate_readiness`

### 3.14 生成与导出服务

负责把模型推进到后续工具链。

建议能力：

- `compile_netlist`
- `compile_spice_netlist`
- `compile_kicad_execution_plan`
- `export_circuit_model`
- `export_kicad_project`
- `export_summary`
- `export_report`
- `run_erc`
- `run_simulation_plan`

### 3.15 查询与搜索服务

负责让 agent 少读整份 JSON。

建议能力：

- `search_components`
- `search_nets`
- `search_risks`
- `search_decisions`
- `search_sheets`
- `search_calculations`

### 3.16 事务服务

负责批量修改的原子性和可回滚性。

建议能力：

- `begin_transaction`
- `apply_operation`
- `apply_batch`
- `commit_transaction`
- `rollback_transaction`
- `dry_run`

## 4. API 返回什么

建议每个 API 返回统一结构：

- `schema_version`
- `success`
- `request_id`
- `project_id`
- `operation`
- `result`
- `diagnostics`
- `warnings`
- `errors`
- `changed_paths`
- `before`
- `after`
- `diff`

其中：

- `result` 保存业务结果
- `diagnostics` 保存结构化校验信息
- `changed_paths` 记录改了哪些字段
- `before/after/diff` 用于审计、回滚和 agent 追踪

## 5. API 实现设计

### 5.1 总体分层

建议实现为四层：

1. **Domain 层**
   - `CircuitModel`、`Component`、`Net`、`Risk`、`Decision`、`Sheet`、`Calculation` 等数据结构

2. **Service 层**
   - 完成器件、网络、电源、风险、决策、校验等业务操作

3. **Adapter 层**
   - 把服务暴露给不同调用方，例如 agent、CLI、HTTP、MCP

4. **Storage 层**
   - 把模型写回 JSON 文件，做版本化和审计

### 5.2 推荐技术栈

主实现建议：

- **Python**
- **`dataclasses`**
- **`typing`**
- **JSON Schema**
- **少量纯函数式 service**
- **文件化存储**

可选扩展：

- **MCP / stdio JSON-RPC** 作为 agent 主入口
- **FastAPI + OpenAPI** 作为外部系统接入壳层

不建议一开始引入：

- 重数据库
- 复杂 ORM
- gRPC
- 直接 GUI 自动化依赖

### 5.3 为什么主入口优先用 MCP / stdio JSON-RPC

因为当前仓库更像一个本地工程工作台，而不是纯网络服务：

- agent 与仓库在同一工作区
- 绝大多数数据是本地文件
- 需要低摩擦、低延迟、结构化调用
- 需要天然适配“工具调用”而不是“页面点击”

因此：

- agent 通过工具调用 API
- API 通过 service 层修改模型
- service 层通过校验后写回 DSL

### 5.4 为什么 Python 适合做核心实现

当前仓库已经是 Python 主导：

- pipeline、校验、生成器都在 Python 中
- 现有结构已具备 `schema_version` 驱动习惯
- `dataclasses` 足够支撑结构化模型
- Python 便于做 JSON 读写、diff、验证和单测

### 5.5 模型对象建议

建议保留以下核心对象：

- `CircuitModel`
- `Component`
- `SelectedPart`
- `CandidatePart`
- `Net`
- `PinMap`
- `Calculation`
- `DesignDecision`
- `Risk`
- `Sheet`
- `Constraint`
- `ValidationReport`
- `OperationResult`
- `Transaction`

### 5.6 模型校验链

推荐校验顺序：

1. schema 结构校验
2. 引用完整性校验
3. net/component 连接校验
4. pinmap 校验
5. 电源树校验
6. 分图边界校验
7. 选型可用性校验
8. 风险一致性校验
9. readiness 校验

### 5.7 存储策略

建议采用：

- 单文件 DSL 持久化为主
- 操作日志和 diff 追加保存
- 导出产物单独落盘
- 需要时支持 revision tag / snapshot

原则是：

- 源模型清晰
- 派生文件可重建
- 中间态可追踪

## 6. 推荐目录结构

建议新增类似以下结构：

```text
src/kicad_suite/model_api/
  __init__.py
  service.py
  commands.py
  results.py
  validation.py
  transactions.py
  schema.py
  storage.py
  diff.py
  transport/
    __init__.py
    mcp.py
    http.py
    cli.py
```

如果后续希望进一步拆分，还可以扩展为：

```text
src/kicad_suite/model_api/
  domain/
  services/
  adapters/
  validators/
  storage/
```

## 7. 推荐调用流程

### 7.1 Agent 进行一次修改

1. agent 读取模型摘要或查询需要的对象
2. agent 调用一个或多个 API 操作
3. API 返回 `before/after/diff/diagnostics`
4. agent 根据 diagnostics 决定是否继续
5. 事务提交后保存 DSL
6. 必要时触发 `validate_model`、`compile_netlist`、`run_erc`

### 7.2 批量收口流程

1. `begin_transaction`
2. 执行多个 `apply_operation`
3. `dry_run` 预检
4. `validate_*`
5. `commit_transaction`
6. `export_*`

## 8. 与现有流水线的关系

这个 API 不是替代现有 pipeline，而是把 pipeline 前面的“模型编辑层”正规化。

建议关系如下：

- API 负责更新 `CircuitModel`
- pipeline 负责把 `CircuitModel` 编译为 `Netlist`、`KiCadExecutionPlan` 和 KiCad 工程
- ERC 和仿真继续作为后续验证

也就是说：

- **API 是建模入口**
- **pipeline 是编译器**
- **KiCad / ngspice 是验证器**

## 9. 非目标

以下内容不作为第一阶段目标：

- 用数据库替代文件 DSL
- 用 GUI 自动化代替结构化 API
- 让 agent 直接生成整份 JSON
- 让 HTTP 服务暴露所有内部细节
- 一开始就做分布式协作编辑

## 10. 第一版落地建议

第一版建议先实现以下能力：

- 模型加载 / 保存 / diff / validate
- `Component` / `Net` / `Risk` / `Decision` 基本 CRUD
- `connect_member` / `set_selected_part` / `assign_component_to_sheet`
- 事务与回滚
- schema 校验与引用完整性校验
- MCP 或本地 CLI 入口

第二阶段再补：

- pinmap
- power tree
- 计算
- 约束
- 导出与外部服务接口

## 11. 结论

这套 API 应该是一个“受控的电路建模服务层”。

它的目标不是把 JSON 包装得更漂亮，而是：

- 降低 agent 直接改 DSL 的风险
- 让模型修改可追踪、可回滚、可校验
- 让后续 KiCad / ngspice / ERC 的编译链更稳定
- 保持仓库当前的 schema-driven 风格不变

如果要一句话概括：

> agent 负责提出修改意图，API 负责安全地修改 DSL，pipeline 负责把 DSL 编译成 KiCad 和验证产物。

## 12. 接口函数设计

本节把上一节的“服务”进一步落成具体函数族。这里不是代码实现，而是 API 契约设计。

### 12.1 统一请求模型

建议所有写操作都使用统一请求对象：

```text
OperationRequest
  schema_version
  request_id
  project_id
  topology
  operation
  payload
  options
```

建议字段说明：

- `schema_version`：请求体版本
- `request_id`：请求追踪 ID
- `project_id`：目标工程
- `topology`：目标拓扑名
- `operation`：操作名，例如 `add_component`
- `payload`：具体业务参数
- `options`：`dry_run`、`validate_only`、`commit`、`strict` 等开关

### 12.2 统一返回模型

建议所有 API 返回统一结果对象：

```text
OperationResult
  schema_version
  success
  request_id
  project_id
  operation
  result
  diagnostics
  warnings
  errors
  before
  after
  diff
  changed_paths
```

建议返回语义：

- `result`：业务结果，例如对象快照、文件路径、统计值
- `diagnostics`：结构化校验与分析结果
- `warnings`：可继续推进但需要注意的事项
- `errors`：不可继续推进的错误
- `before/after`：修改前后快照
- `diff`：字段差异
- `changed_paths`：实际写入路径

### 12.3 读操作函数

读操作不改模型，默认不需要事务。

- `load_model(path)`：从 JSON 载入 DSL
- `save_model(model, path)`：把 DSL 写回 JSON
- `get_metadata(model)`
- `get_component(model, ref)`
- `list_components(model, filter=None)`
- `search_components(model, query)`
- `get_net(model, name)`
- `list_nets(model, filter=None)`
- `search_nets(model, query)`
- `get_sheet(model, name)`
- `list_sheets(model)`
- `get_calculation(model, name)`
- `list_calculations(model)`
- `get_design_decision(model, title)`
- `list_design_decisions(model)`
- `get_risk(model, key_or_text)`
- `list_risks(model)`
- `get_constraint(model, name)`
- `list_constraints(model)`

### 12.4 写操作函数

写操作建议都遵循 `before -> validate -> apply -> after` 的固定流程。

#### 元信息

- `set_schema_version(model, value)`
- `set_request_id(model, value)`
- `set_project_id(model, value)`
- `set_topology(model, value)`
- `update_metadata(model, payload)`

#### 器件

- `add_component(model, payload)`
- `update_component(model, ref, patch)`
- `remove_component(model, ref)`
- `set_component_role(model, ref, role)`
- `set_component_value(model, ref, value)`
- `set_component_selected_part(model, ref, part)`
- `add_component_candidate_part(model, ref, part)`
- `remove_component_candidate_part(model, ref, part_id)`
- `set_component_availability(model, ref, status)`
- `add_component_note(model, ref, note)`

#### 网络

- `add_net(model, payload)`
- `update_net(model, name, patch)`
- `remove_net(model, name)`
- `connect_member(model, net, member)`
- `connect_members(model, net, members)`
- `disconnect_member(model, net, member)`
- `rename_net(model, old_name, new_name)`
- `merge_nets(model, source, target)`
- `split_net(model, name, new_names)`
- `set_net_kind(model, name, kind)`
- `add_net_note(model, name, note)`

#### Pinmap

- `set_pinmap(model, ref, pinmap)`
- `connect_pin_to_net(model, ref, pin, net)`
- `disconnect_pin_from_net(model, ref, pin, net=None)`
- `set_pin_role(model, ref, pin, role)`
- `set_pin_no_connect(model, ref, pin, enabled=True)`
- `add_pin_alias(model, ref, pin, alias)`

#### 电源

- `add_power_rail(model, payload)`
- `set_rail_source(model, name, source_net)`
- `set_rail_sink(model, name, sink_ref)`
- `set_rail_voltage(model, name, voltage_v)`
- `set_rail_current_limit(model, name, current_a)`
- `set_rail_sequence_order(model, name, order)`
- `add_rail_test_point(model, name, ref)`

#### 分图

- `add_sheet(model, payload)`
- `assign_component_to_sheet(model, ref, sheet_name)`
- `assign_net_to_sheet(model, net_name, sheet_name)`
- `set_sheet_inputs(model, sheet_name, nets)`
- `set_sheet_outputs(model, sheet_name, nets)`
- `set_sheet_constraints(model, sheet_name, constraints)`

#### 计算

- `add_calculation(model, payload)`
- `update_calculation(model, name, patch)`
- `recompute_calculation(model, name)`

#### 决策与风险

- `add_design_decision(model, payload)`
- `update_design_decision(model, title, patch)`
- `add_risk(model, payload)`
- `update_risk(model, key, patch)`
- `mark_risk_resolved(model, key)`
- `mark_risk_blocked(model, key, reason)`

#### 约束

- `add_constraint(model, payload)`
- `update_constraint(model, name, patch)`
- `remove_constraint(model, name)`

### 12.5 编排函数

编排函数负责把多个操作组合成安全工作单元。

- `begin_transaction(model)`
- `apply_operation(tx, operation_request)`
- `apply_batch(tx, operations)`
- `dry_run(tx)`
- `commit_transaction(tx)`
- `rollback_transaction(tx)`
- `diff_transaction(tx)`

建议语义：

- `dry_run` 只做校验，不写盘
- `commit_transaction` 写盘并生成审计记录
- `rollback_transaction` 恢复事务开始时快照

### 12.6 校验函数

校验函数应返回结构化诊断，而不是只抛异常。

- `validate_schema(model)`
- `validate_references(model)`
- `validate_connectivity(model)`
- `validate_pinmap(model)`
- `validate_power_tree(model)`
- `validate_sheet_boundary(model)`
- `validate_part_availability(model)`
- `validate_risk_consistency(model)`
- `validate_readiness(model)`

建议每个校验函数都返回：

- `ok`
- `errors`
- `warnings`
- `checks`
- `stats`

### 12.7 导出函数

导出函数用于把模型推进到后续流水线：

- `compile_netlist(model)`
- `compile_spice_netlist(netlist)`
- `compile_kicad_execution_plan(model, netlist)`
- `export_circuit_model(model, path)`
- `export_kicad_project(plan, path)`
- `run_erc(project_dir)`
- `run_simulation_plan(model)`

## 13. 错误模型

建议 API 使用有限的错误类别，便于 agent 稳定处理。

### 13.1 建议错误码

- `INVALID_SCHEMA`
- `INVALID_PAYLOAD`
- `NOT_FOUND`
- `ALREADY_EXISTS`
- `CONFLICT`
- `BROKEN_REFERENCE`
- `VALIDATION_FAILED`
- `TX_NOT_ACTIVE`
- `TX_ALREADY_ACTIVE`
- `IO_ERROR`
- `UNSUPPORTED_OPERATION`
- `UNSUPPORTED_SCHEMA_VERSION`

### 13.2 建议错误返回

```text
ApiError
  code
  message
  path
  details
  hint
```

建议：

- `path` 指向具体字段，例如 `components[U3].selected_part`
- `hint` 给 agent 一个可执行下一步

## 14. 实现细节设计

### 14.1 核心对象层

推荐把 `circuit_pipeline.py` 里的 dataclass 作为领域对象基础：

- `CircuitModel`
- `CircuitComponent`
- `CircuitNet`
- `CircuitCalculation`
- `DesignDecision`
- `RequirementSpec`
- `NetlistModel`
- `SpiceNetlistModel`
- `NgspiceExecutionModel`
- `NgspiceFeedbackModel`

API 层不直接操作原始字典，而是：

- 先把 JSON 反序列化成领域对象
- 再通过 service 改对象
- 最后再序列化回 JSON

### 14.2 服务层

服务层建议按职责分模块：

- `model_service.py`
- `component_service.py`
- `net_service.py`
- `pinmap_service.py`
- `power_service.py`
- `sheet_service.py`
- `calculation_service.py`
- `decision_service.py`
- `risk_service.py`
- `constraint_service.py`
- `validation_service.py`
- `export_service.py`
- `transaction_service.py`

每个 service 只做一类事，避免把所有逻辑塞进一个大类。

### 14.3 适配层

适配层负责把同一套服务暴露给不同入口：

- `CLI`：本地脚本 / 命令行
- `MCP`：agent 工具调用
- `HTTP`：以后给外部系统接入

建议内部共享同一套 service，避免“CLI 一套逻辑、HTTP 一套逻辑、agent 又一套逻辑”。

### 14.4 序列化策略

建议使用：

- `dataclasses.asdict()` 作为基础导出
- 小范围手写序列化补齐字段兼容
- `schema_version` 作为跨层兼容闸门

### 14.5 兼容性策略

建议按以下顺序演进：

1. 新增可选字段
2. 写入兼容字段
3. 更新消费端
4. 再考虑提高必填字段门槛

这和当前仓库的版本策略一致。

## 15. 第一版功能范围建议

如果要先落一个能真正用的版本，建议第一版实现：

- 模型读写
- 器件 CRUD
- 网络 CRUD 与 connect / disconnect
- selected_part 操作
- 风险 / 决策 CRUD
- 分图归属
- 事务与回滚
- schema 校验
- 引用完整性校验
- 基本导出接口

第二版再补：

- pinmap 完整支持
- power tree 完整支持
- 计算服务
- 约束服务
- MCP / HTTP 多适配层

## 16. 设计结论

这套 API 功能设计的重点不是“把 JSON 封起来”，而是把 DSL 从“人手编辑文件”变成“受控建模系统”。

最终目标是：

- agent 可以安全地修改模型
- 修改过程可验证、可回滚、可追踪
- 模型可以自然进入 pipeline、ERC 和后续 KiCad 生成
- 整个仓库继续保持 schema-first 的风格

## 17. 接口总表

本节把上面的设计压缩成便于实现的接口总表。这里使用“服务 / 函数 / 输入 / 输出 / 说明”的格式。

### 17.1 模型生命周期

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `load_model` | `path` | `CircuitModel` | 从 JSON 载入 DSL |
| `save_model` | `model`, `path` | `OperationResult` | 将 DSL 写回 JSON |
| `clone_model` | `model` | `CircuitModel` | 复制模型快照 |
| `reset_model` | `model` | `CircuitModel` | 回到初始状态 |
| `diff_model` | `before`, `after` | `diff` | 生成差分 |
| `merge_model` | `base`, `other` | `CircuitModel` | 合并两个模型 |
| `patch_model` | `model`, `patch` | `OperationResult` | 按 patch 改模型 |
| `validate_model` | `model` | `ValidationReport` | 综合校验 |
| `validate_schema` | `model` | `ValidationReport` | 结构校验 |

### 17.2 项目元信息

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `get_metadata` | `model` | `metadata` | 读取顶层元信息 |
| `set_schema_version` | `model`, `value` | `OperationResult` | 设置版本号 |
| `set_request_id` | `model`, `value` | `OperationResult` | 设置请求 ID |
| `set_project_id` | `model`, `value` | `OperationResult` | 设置工程 ID |
| `set_topology` | `model`, `value` | `OperationResult` | 设置拓扑名 |
| `update_metadata` | `model`, `payload` | `OperationResult` | 批量更新元信息 |

### 17.3 器件

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_component` | `model`, `payload` | `OperationResult` | 新增器件 |
| `update_component` | `model`, `ref`, `patch` | `OperationResult` | 更新器件字段 |
| `remove_component` | `model`, `ref` | `OperationResult` | 删除器件 |
| `get_component` | `model`, `ref` | `Component` | 获取器件 |
| `list_components` | `model`, `filter` | `list[Component]` | 列出器件 |
| `search_components` | `model`, `query` | `list[Component]` | 搜索器件 |
| `set_selected_part` | `model`, `ref`, `part` | `OperationResult` | 设置选型 |
| `add_candidate_part` | `model`, `ref`, `part` | `OperationResult` | 增加备选 |
| `remove_candidate_part` | `model`, `ref`, `part_id` | `OperationResult` | 删除备选 |
| `set_component_availability` | `model`, `ref`, `status` | `OperationResult` | 设置可用性 |
| `add_component_note` | `model`, `ref`, `note` | `OperationResult` | 增加备注 |
| `assign_component_to_sheet` | `model`, `ref`, `sheet_name` | `OperationResult` | 归属分图 |

### 17.4 网络

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_net` | `model`, `payload` | `OperationResult` | 新增网络 |
| `update_net` | `model`, `name`, `patch` | `OperationResult` | 更新网络 |
| `remove_net` | `model`, `name` | `OperationResult` | 删除网络 |
| `get_net` | `model`, `name` | `Net` | 获取网络 |
| `list_nets` | `model`, `filter` | `list[Net]` | 列出网络 |
| `search_nets` | `model`, `query` | `list[Net]` | 搜索网络 |
| `connect_member` | `model`, `net`, `member` | `OperationResult` | 连接成员 |
| `disconnect_member` | `model`, `net`, `member` | `OperationResult` | 断开成员 |
| `rename_net` | `model`, `old_name`, `new_name` | `OperationResult` | 重命名网络 |
| `merge_nets` | `model`, `source`, `target` | `OperationResult` | 合并网络 |
| `split_net` | `model`, `name`, `new_names` | `OperationResult` | 拆分网络 |
| `set_net_kind` | `model`, `name`, `kind` | `OperationResult` | 设置网络类型 |
| `add_net_note` | `model`, `name`, `note` | `OperationResult` | 增加备注 |
| `assign_net_to_sheet` | `model`, `net_name`, `sheet_name` | `OperationResult` | 归属分图 |

### 17.5 Pinmap

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `set_pinmap` | `model`, `ref`, `pinmap` | `OperationResult` | 设置器件 pinmap |
| `connect_pin_to_net` | `model`, `ref`, `pin`, `net` | `OperationResult` | 引脚连网 |
| `disconnect_pin_from_net` | `model`, `ref`, `pin`, `net` | `OperationResult` | 引脚断网 |
| `set_pin_role` | `model`, `ref`, `pin`, `role` | `OperationResult` | 设置引脚角色 |
| `set_pin_no_connect` | `model`, `ref`, `pin`, `enabled` | `OperationResult` | 设置 NC |
| `add_pin_alias` | `model`, `ref`, `pin`, `alias` | `OperationResult` | 增加引脚别名 |
| `validate_pinmap` | `model` | `ValidationReport` | 校验 pinmap |

### 17.6 电源树

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_power_rail` | `model`, `payload` | `OperationResult` | 新增电源域 |
| `set_rail_source` | `model`, `name`, `source_net` | `OperationResult` | 设置来源 |
| `set_rail_sink` | `model`, `name`, `sink_ref` | `OperationResult` | 设置负载 |
| `set_rail_voltage` | `model`, `name`, `voltage_v` | `OperationResult` | 设置目标电压 |
| `set_rail_current_limit` | `model`, `name`, `current_a` | `OperationResult` | 设置限流 |
| `set_rail_sequence_order` | `model`, `name`, `order` | `OperationResult` | 设置时序 |
| `add_rail_test_point` | `model`, `name`, `ref` | `OperationResult` | 增加测试点 |
| `validate_power_tree` | `model` | `ValidationReport` | 校验电源树 |
| `validate_power_budget` | `model` | `ValidationReport` | 校验预算 |

### 17.7 分图

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_sheet` | `model`, `payload` | `OperationResult` | 新增分图 |
| `update_sheet` | `model`, `sheet_name`, `patch` | `OperationResult` | 更新分图 |
| `remove_sheet` | `model`, `sheet_name` | `OperationResult` | 删除分图 |
| `get_sheet` | `model`, `sheet_name` | `Sheet` | 获取分图 |
| `list_sheets` | `model` | `list[Sheet]` | 列出分图 |
| `set_sheet_inputs` | `model`, `sheet_name`, `nets` | `OperationResult` | 设置输入 |
| `set_sheet_outputs` | `model`, `sheet_name`, `nets` | `OperationResult` | 设置输出 |
| `set_sheet_components` | `model`, `sheet_name`, `refs` | `OperationResult` | 设置器件归属 |
| `set_sheet_nets` | `model`, `sheet_name`, `nets` | `OperationResult` | 设置网络归属 |
| `validate_sheet_boundary` | `model` | `ValidationReport` | 校验边界 |

### 17.8 计算、决策与风险

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_calculation` | `model`, `payload` | `OperationResult` | 新增计算项 |
| `recompute_calculation` | `model`, `name` | `OperationResult` | 重新计算 |
| `add_design_decision` | `model`, `payload` | `OperationResult` | 新增决策 |
| `update_design_decision` | `model`, `title`, `patch` | `OperationResult` | 更新决策 |
| `add_risk` | `model`, `payload` | `OperationResult` | 新增风险 |
| `update_risk` | `model`, `key`, `patch` | `OperationResult` | 更新风险 |
| `mark_risk_resolved` | `model`, `key` | `OperationResult` | 标记已解决 |
| `mark_risk_blocked` | `model`, `key`, `reason` | `OperationResult` | 标记阻塞 |

### 17.9 约束与采购

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `add_constraint` | `model`, `payload` | `OperationResult` | 新增约束 |
| `update_constraint` | `model`, `name`, `patch` | `OperationResult` | 更新约束 |
| `remove_constraint` | `model`, `name` | `OperationResult` | 删除约束 |
| `select_part` | `model`, `ref`, `part` | `OperationResult` | 选型 |
| `replace_selected_part` | `model`, `ref`, `part` | `OperationResult` | 替换选型 |
| `lock_selected_part` | `model`, `ref` | `OperationResult` | 锁定器件 |
| `validate_part_availability` | `model` | `ValidationReport` | 校验器件可用性 |

### 17.10 编排与导出

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `begin_transaction` | `model` | `Transaction` | 开始事务 |
| `apply_operation` | `tx`, `operation_request` | `OperationResult` | 执行单次操作 |
| `apply_batch` | `tx`, `operations` | `OperationResult` | 批量执行 |
| `dry_run` | `tx` | `ValidationReport` | 仅预检 |
| `commit_transaction` | `tx` | `OperationResult` | 提交事务 |
| `rollback_transaction` | `tx` | `OperationResult` | 回滚事务 |
| `compile_netlist` | `model` | `NetlistModel` | 编译网表 |
| `compile_kicad_execution_plan` | `model`, `netlist` | `KiCadExecutionPlan` | 编译 KiCad 计划 |
| `run_erc` | `project_dir` | `OperationResult` | 运行 ERC |
| `run_simulation_plan` | `model` | `OperationResult` | 生成并运行仿真计划 |

### 17.11 错误码速查

| 错误码 | 场景 |
| --- | --- |
| `INVALID_SCHEMA` | 输入结构不符合 schema |
| `INVALID_PAYLOAD` | 业务参数缺字段或类型错误 |
| `NOT_FOUND` | 目标对象不存在 |
| `ALREADY_EXISTS` | 重复创建同名对象 |
| `CONFLICT` | 修改与当前状态冲突 |
| `BROKEN_REFERENCE` | 引用断裂 |
| `VALIDATION_FAILED` | 校验未通过 |
| `TX_NOT_ACTIVE` | 事务未开启 |
| `TX_ALREADY_ACTIVE` | 事务重复开启 |
| `IO_ERROR` | 文件读写失败 |
| `UNSUPPORTED_OPERATION` | 当前实现不支持该操作 |
| `UNSUPPORTED_SCHEMA_VERSION` | 不支持当前 schema 版本 |

## 18. 适合实现的最小切片

如果先实现一个可用切片，建议先落这几个接口族：

- `load_model` / `save_model`
- `add_component` / `update_component` / `set_selected_part`
- `add_net` / `connect_member` / `disconnect_member`
- `add_risk` / `add_design_decision`
- `begin_transaction` / `apply_batch` / `commit_transaction`
- `validate_model` / `validate_connectivity` / `validate_schema`
- `compile_netlist` / `compile_kicad_execution_plan`

这组接口足以支撑 agent 从“编辑 JSON”过渡到“通过 API 操作 DSL”。
