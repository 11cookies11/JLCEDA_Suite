# 理论模型到命令计划（编译规则）

本文定义 `CircuitModel -> ExecutionPlan` 的统一编译规则，用于把“文本原理图理论模型”转换为 JLCEDA 封装命令序列。

## 1. 总体链路

1. 读取 `circuit-model.v1`
2. 编译组件放置命令（`schematic.place_component`）
3. 编译网络标注命令（`schematic.annotate_net` / `schematic.create_net_flag`）
4. 编译检查与保存命令（`schematic.inspect_connectivity` / `schematic.check_drc` / `schematic.save`）
5. 生成 `execution-plan.v1`

实现脚本：
- `scripts/compile_execution_plan.py`

运行命令：
- `npm run server:compile-plan`

## 2. 输入与输出

输入（二选一）：
- `BRIDGE_CIRCUIT_MODEL_JSON`
- `BRIDGE_CIRCUIT_MODEL_FILE`

输出：
- `BRIDGE_EXECUTION_PLAN_FILE`（可选，显式指定）
- 若未指定：`.where/pipeline-output/<request-id>/execution-plan.json`

## 3. 字段映射规则

### 3.1 组件 -> `place_component`

映射条件：
- `components[].selected_part.library_uuid` 非空
- `components[].selected_part.symbol_uuid` 非空

映射结果：
- `kind=place_component`
- `payload.libraryUuid = selected_part.library_uuid`
- `payload.uuid = selected_part.symbol_uuid`
- `payload.position = 自动网格坐标`
- `payload.rotation = 0`
- `payload.mirror = false`
- `on_error = stop`

### 3.2 网络 -> `annotate_net` / `create_net_flag`

对每个 `nets[].name`：
- 先生成 `annotate_net`
- 若为地网（`GND/AGND/PGND`）再生成 `create_net_flag(identification=Ground)`
- 若为电源网（`+3V3/+5V/VCC/VDD/VIN...`）再生成 `create_net_flag(identification=Power)`

### 3.3 验证尾部命令

始终追加：
- `inspect_connectivity`
- `check_drc`
- `save`

## 4. 失败码与回退策略

默认回退规则：
- `PART_UNAVAILABLE` -> `replace_with_backup_candidate_and_recompile`
- `PIN_MISSING` -> `stop_and_request_pin_verified_symbol`
- `WIRE_FAILED` -> `retry_with_labels_then_manual_review`
- `EXECUTION_FAILED` -> `collect_error_and_replan`

额外规则：
- 若没有任何可放置器件，追加 `PART_UNAVAILABLE -> stop_without_execution`

## 5. 设计边界

- 当前编译器优先输出“稳定可执行”的基础命令序列。
- 自动连线（`create_wire`）默认不强制生成，避免 pin 几何不完整时误连。
- 需要强连线时，建议先通过 pin 集合校验模块生成安全连线操作，再注入到执行计划。

## 6. 后续增强建议

- 增加分页策略：按功能块把组件分配到不同 schematic page。
- 增加布局模板：电源块、MCU 块、接口块的初始相对坐标。
- 增加连线编译器：仅在 pin 几何可验证时生成 `create_wire`。
- 增加执行反馈回写：把失败原因结构化回填到 `CircuitModel.risks`。
