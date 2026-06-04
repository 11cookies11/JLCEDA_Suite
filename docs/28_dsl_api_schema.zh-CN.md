# DSL API 请求 / 响应 Schema

Status: Draft

## 1. 目标

本文定义 `CircuitModel DSL API` 的请求 / 响应结构，作为上一版接口总表的 schema 化补充。

本文关注的不是某一种 transport，而是统一的消息结构：

- `MCP` 可以直接承载
- `HTTP` 可以映射为 JSON body
- `CLI` 可以读写同一套文件化消息

目标是让 agent 不再直接拼整份 `source/circuit-model.source.json`，而是通过结构化请求调用受控操作。

## 2. 设计原则

- **统一 envelope**：所有请求和响应共享同一外层结构。
- **payload 分域**：不同操作只负责各自的业务 payload。
- **错误结构统一**：所有错误都能被 agent 稳定解析。
- **支持事务**：复杂操作可以先预检再提交。
- **支持 diff**：返回修改前后差异，方便 agent 继续决策。
- **兼容文件式工作流**：请求和响应都可以直接落盘为 JSON 文件。

## 3. 顶层消息类型

建议定义以下基础消息类型：

- `OperationRequest`
- `OperationResult`
- `ValidationReport`
- `ApiError`
- `Transaction`
- `ModelSnapshot`

## 4. 统一请求 envelope

### 4.1 `OperationRequest`

所有写操作和大多数读操作都建议使用统一请求外壳。

```json
{
  "schema_version": "dsl-api-request.v1",
  "request_id": "h618-agentboard-v1-initial-001",
  "project_id": "h618-agentboard-v1",
  "topology": "h618_agentboard_v1_initial",
  "operation": "add_component",
  "payload": {},
  "options": {
    "dry_run": false,
    "validate_only": false,
    "commit": true,
    "strict": true
  }
}
```

### 4.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | 是 | 请求 envelope 版本 |
| `request_id` | string | 是 | 请求追踪 ID |
| `project_id` | string | 是 | 工程 ID |
| `topology` | string | 否 | 拓扑名 |
| `operation` | string | 是 | 操作名，例如 `add_component` |
| `payload` | object | 是 | 操作参数 |
| `options` | object | 否 | 运行选项 |

### 4.3 `options`

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dry_run` | boolean | `false` | 只做预检，不落盘 |
| `validate_only` | boolean | `false` | 只校验，不应用修改 |
| `commit` | boolean | `true` | 是否提交变更 |
| `strict` | boolean | `true` | 是否严格失败 |
| `return_diff` | boolean | `true` | 是否返回 diff |
| `return_snapshot` | boolean | `true` | 是否返回修改后快照 |

## 5. 统一响应 envelope

### 5.1 `OperationResult`

所有 API 响应建议统一为：

```json
{
  "schema_version": "dsl-api-result.v1",
  "success": true,
  "request_id": "h618-agentboard-v1-initial-001",
  "project_id": "h618-agentboard-v1",
  "operation": "add_component",
  "result": {},
  "diagnostics": {
    "ok": true,
    "errors": [],
    "warnings": [],
    "checks": [],
    "stats": {}
  },
  "warnings": [],
  "errors": [],
  "before": {},
  "after": {},
  "diff": [],
  "changed_paths": []
}
```

### 5.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | 是 | 响应 envelope 版本 |
| `success` | boolean | 是 | 本次操作是否成功 |
| `request_id` | string | 是 | 继承请求 ID |
| `project_id` | string | 是 | 工程 ID |
| `operation` | string | 是 | 原操作名 |
| `result` | object | 否 | 业务结果 |
| `diagnostics` | `ValidationReport` | 否 | 结构化诊断 |
| `warnings` | array[string] | 否 | 额外告警 |
| `errors` | array[`ApiError`] | 否 | 结构化错误 |
| `before` | object | 否 | 修改前快照 |
| `after` | object | 否 | 修改后快照 |
| `diff` | array[object] | 否 | 字段差异 |
| `changed_paths` | array[string] | 否 | 实际修改路径 |

## 6. 统一诊断结构

### 6.1 `ValidationReport`

建议与现有 `ValidationReport` 保持同名同语义。

```json
{
  "ok": true,
  "errors": [],
  "warnings": [],
  "checks": [],
  "stats": {}
}
```

### 6.2 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean | 是否通过 |
| `errors` | array[string] | 错误列表 |
| `warnings` | array[string] | 告警列表 |
| `checks` | array[string] | 已执行检查 |
| `stats` | object | 统计值 |

## 7. 统一错误结构

### 7.1 `ApiError`

```json
{
  "code": "VALIDATION_FAILED",
  "message": "reference U3 not found",
  "path": "components[U3].selected_part",
  "details": {},
  "hint": "Create component U3 first or fix the reference."
}
```

### 7.2 字段定义

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `code` | string | 是 | 错误码 |
| `message` | string | 是 | 可读错误信息 |
| `path` | string | 否 | 出错字段路径 |
| `details` | object | 否 | 附加细节 |
| `hint` | string | 否 | 给 agent 的下一步建议 |

### 7.3 错误码建议

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

## 8. 模型快照结构

### 8.1 `ModelSnapshot`

建议把 `CircuitModel` 直接作为快照对象的主体。

```json
{
  "schema_version": "circuit-model.v1",
  "request_id": "h618-agentboard-v1-initial",
  "project_id": "h618-agentboard-v1",
  "topology": "h618_agentboard_v1_initial",
  "components": [],
  "nets": [],
  "calculations": [],
  "design_decisions": [],
  "risks": []
}
```

### 8.2 字段约定

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | 模型版本 |
| `request_id` | string | 当前模型来源请求 ID |
| `project_id` | string | 工程 ID |
| `topology` | string | 拓扑名 |
| `components` | array | 器件列表 |
| `nets` | array | 网络列表 |
| `calculations` | array | 计算项 |
| `design_decisions` | array | 决策项 |
| `risks` | array[string] | 风险列表 |

## 9. 核心对象 schema

### 9.1 `Component`

```json
{
  "ref": "U1",
  "role": "pmic_axp313a",
  "value": "AXP313A",
  "selected_part": {
    "part_id": "axp313a-pmic",
    "display_name": "AXP313A PMIC",
    "lcsc_id": "C5365290",
    "manufacturer": "X-Powers",
    "mpn": "AXP313A",
    "package": "QFN-20",
    "library_uuid": "",
    "place_uuid": "",
    "symbol_uuid": "",
    "pin_count": 0,
    "named_pin_count": 0,
    "availability_status": "available"
  },
  "candidate_parts": [],
  "availability_status": "available",
  "notes": []
}
```

### 9.2 `Net`

```json
{
  "name": "+3V3",
  "members": ["U1.VDD", "TP1.1"],
  "notes": ["Main logic rail."]
}
```

### 9.3 `Calculation`

```json
{
  "name": "3v3_budget",
  "formula": "sum(loads) + margin",
  "inputs": {
    "loads": 0.42,
    "margin": 0.1
  },
  "result": 0.52,
  "unit": "A"
}
```

### 9.4 `DesignDecision`

```json
{
  "title": "Resolve DDR topology for V1",
  "rationale": "LPDDR4 topology follows the current board revision and reference capture.",
  "impact": "Keeps DDR routing and pinmap consistent across the pipeline."
}
```

### 9.5 `Risk`

风险建议统一为对象，而不是仅字符串数组。

```json
{
  "key": "ddr-topology-review",
  "title": "LPDDR4 still requires reference review",
  "status": "blocked",
  "severity": "high",
  "category": "memory",
  "description": "DDR pinmap still needs final reference capture.",
  "owner": "agent",
  "due_reason": "Needs board-level confirmation before layout freeze."
}
```

### 9.6 `Sheet`

```json
{
  "name": "sheet_03_memory_ddr",
  "inputs": ["+1V2_DDR", "+0V9_DDR", "H618_LPDDR4_*"],
  "outputs": ["DDR data/control nets"],
  "components": ["U3", "TP9", "TP10"],
  "nets": ["+1V2_DDR", "+0V9_DDR"],
  "constraints": []
}
```

### 9.7 `Transaction`

```json
{
  "transaction_id": "tx-001",
  "request_id": "h618-agentboard-v1-initial-001",
  "status": "active",
  "base_revision": "rev-000123",
  "operations": [],
  "started_at": "2026-05-27T02:22:11+08:00"
}
```

## 10. payload 设计原则

### 10.1 payload 只承载业务输入

`payload` 不应包含：

- 请求 envelope 字段
- 通用状态字段
- 事务信息
- 诊断结果

它只应该描述本次操作本身需要的参数。

### 10.2 payload 应尽量稳定

建议 payload 采用以下风格：

- 小而明确
- 字段语义短
- 复用统一对象结构
- 避免把整个模型塞进 payload

例如：

- `add_component` 只需要组件对象
- `connect_member` 只需要 `net` 和 `member`
- `set_selected_part` 只需要 `ref` 和 `part`

## 11. patch 结构

### 11.1 推荐使用 typed patch，而不是裸 JSON Patch

对于 DSL API，推荐优先使用“类型化操作”而不是直接开放任意 JSON Patch。

原因：

- 更容易校验
- 更容易生成诊断
- 更容易做事务回滚
- 更符合 agent 的意图表达方式

### 11.2 可选的 patch 模式

必要时可支持：

- `merge_patch`
- `json_patch`

但建议仅作为高级模式，不作为默认模式。

## 12. 示例请求

### 12.1 新增器件

```json
{
  "schema_version": "dsl-api-request.v1",
  "request_id": "req-001",
  "project_id": "h618-agentboard-v1",
  "topology": "h618_agentboard_v1_initial",
  "operation": "add_component",
  "payload": {
    "ref": "TP11",
    "role": "test_point",
    "value": "+1V1_CORE",
    "selected_part": {
      "part_id": "tp-1p",
      "display_name": "Test Point",
      "package": "JLC-MCP:TP-SMD_1P"
    },
    "candidate_parts": [],
    "availability_status": "available",
    "notes": ["Core rail measurement point."]
  }
}
```

### 12.2 连接网络成员

```json
{
  "schema_version": "dsl-api-request.v1",
  "request_id": "req-002",
  "project_id": "h618-agentboard-v1",
  "operation": "connect_member",
  "payload": {
    "net": "+1V1_CORE",
    "member": "TP11.1"
  }
}
```

### 12.3 事务批量提交

```json
{
  "schema_version": "dsl-api-request.v1",
  "request_id": "req-003",
  "project_id": "h618-agentboard-v1",
  "operation": "apply_batch",
  "payload": {
    "operations": [
      {
        "operation": "add_component",
        "payload": { "ref": "R100", "role": "resistor", "value": "10k" }
      },
      {
        "operation": "connect_member",
        "payload": { "net": "H618_RESET_N", "member": "R100.1" }
      }
    ]
  },
  "options": {
    "dry_run": false,
    "validate_only": false,
    "commit": true,
    "strict": true
  }
}
```

## 13. 示例响应

### 13.1 成功响应

```json
{
  "schema_version": "dsl-api-result.v1",
  "success": true,
  "request_id": "req-001",
  "project_id": "h618-agentboard-v1",
  "operation": "add_component",
  "result": {
    "ref": "TP11"
  },
  "diagnostics": {
    "ok": true,
    "errors": [],
    "warnings": [],
    "checks": ["schema ok", "reference ok"],
    "stats": {
      "component_count": 56
    }
  },
  "warnings": [],
  "errors": [],
  "before": {},
  "after": {},
  "diff": [
    {
      "path": "components[TP11]",
      "op": "add"
    }
  ],
  "changed_paths": ["components[TP11]"]
}
```

### 13.2 失败响应

```json
{
  "schema_version": "dsl-api-result.v1",
  "success": false,
  "request_id": "req-002",
  "project_id": "h618-agentboard-v1",
  "operation": "connect_member",
  "result": {},
  "diagnostics": {
    "ok": false,
    "errors": ["net not found"],
    "warnings": [],
    "checks": ["schema ok"],
    "stats": {}
  },
  "warnings": [],
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "net +1V1_CORE not found",
      "path": "payload.net",
      "details": {},
      "hint": "Create the net before connecting members."
    }
  ],
  "before": {},
  "after": {},
  "diff": [],
  "changed_paths": []
}
```

## 14. 与现有模型字段的对齐

建议 API schema 与现有字段直接对齐：

- `components[]` 对齐器件服务
- `nets[]` 对齐网络服务
- `calculations[]` 对齐计算服务
- `design_decisions[]` 对齐决策服务
- `risks[]` 对齐风险服务
- `schema_version` 对齐版本门禁

这样可以避免引入一套和现有 DSL 不一致的新语义。

## 15. 验证规则

### 15.1 请求侧验证

请求进入 API 时，至少要校验：

- `schema_version` 是否受支持
- `request_id` 是否存在
- `project_id` 是否存在
- `operation` 是否存在
- `payload` 是否满足操作要求

### 15.2 响应侧验证

响应返回时，至少要保证：

- `success` 与 `errors` 不冲突
- 成功时 `diagnostics.ok = true`
- 失败时至少给出一条 `ApiError`
- `request_id` 前后一致

## 16. 推荐实现方式

建议把 schema 定义成三层：

1. **common envelope schema**
2. **operation payload schema**
3. **entity schema**

这样可以：

- 复用公共字段
- 给不同操作独立扩展空间
- 让 MCP / HTTP / CLI 共用同一套校验器

## 17. 与实现代码的对应关系

建议以后实现时按以下方式组织：

- `commands.py`：定义请求对象
- `results.py`：定义响应对象
- `schema.py`：定义 schema 常量与校验入口
- `validation.py`：返回 `ValidationReport`
- `transactions.py`：承载事务上下文
- `service.py`：执行具体操作

## 18. 结论

这套 request / response schema 的核心价值是：

- agent 只发意图，不直接碰 JSON 主体
- API 返回统一结构，便于自动化处理
- 功能层、校验层和导出层可以共享同一套契约
- 后续无论接 MCP、HTTP 还是 CLI，都不需要重新定义业务语义

如果要一句话总结：

> DSL API 的 schema 要像“受控命令协议”，而不是“开放式 JSON 文件编辑接口”。
