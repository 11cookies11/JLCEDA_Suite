# Codex Bridge Protocol v0

## 目标

定义 AI agent 与 `JLCEDA Suite` 插件之间的第一版桥接协议，使两端可以通过结构化消息完成读取、执行、确认与错误回传。

本版本优先解决三件事：

1. 安全地表达 EDA 操作命令
2. 稳定地返回工程状态与执行结果
3. 对高风险操作提供确认与失败语义

## 设计原则

- 插件只接收结构化命令，不直接执行自然语言
- 命令必须声明目标编辑域，例如 `project`、`schematic`、`pcb`
- 任何写操作都必须有明确参数，不能依赖模糊推断
- 插件返回结构化结果，供 Codex 继续规划或解释
- 高风险操作支持确认门禁，避免模型直接执行不可逆操作

## 协议结构

### 请求包

```json
{
  "id": "req_20260407_0001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "session_local_demo",
  "command": {
    "domain": "schematic",
    "action": "place_component",
    "requiresConfirmation": true,
    "payload": {
      "libraryId": "C12345",
      "position": { "x": 1200, "y": 800 },
      "rotation": 0
    }
  }
}
```

字段说明：

- `id`：请求唯一标识，用于关联响应
- `type`：当前固定为 `command.request`
- `protocolVersion`：协议版本
- `sessionId`：当前插件会话标识
- `command`：具体命令对象

### 响应包

```json
{
  "id": "req_20260407_0001",
  "type": "command.response",
  "protocolVersion": "0.1.0",
  "status": "success",
  "result": {
    "summary": "component placed",
    "data": {
      "instanceId": "R_12",
      "position": { "x": 1200, "y": 800 }
    }
  }
}
```

字段说明：

- `status`：`success`、`error`、`confirmation_required`
- `result`：成功时返回的摘要与结构化数据
- `error`：失败时返回的错误对象
- `confirmation`：需要用户确认时返回的确认对象

## 命令模型

### 域

- `project`
- `schematic`
- `pcb`
- `system`

### 初版动作集合

#### `project`

- `get_document_summary`
- `get_selection_snapshot`
- `export_bom`

#### `schematic`

- `place_component`
- `create_wire`
- `annotate_net`
- `inspect_connectivity`

#### `pcb`

- `get_board_summary`
- `place_footprint`

#### `system`

- `ping`
- `get_bridge_status`

## 请求载荷约定

### 只读查询

只读查询应当优先返回摘要和必要细节，避免把整个工程原样倾倒给模型。

推荐返回：

- 当前文档类型
- 当前页面或工作区标识
- 选中对象数量
- 元件清单摘要
- 网络连接摘要
- 坐标范围与基本统计

### 写操作

写操作至少应当包含：

- 明确动作类型
- 目标对象标识
- 必需参数
- 操作范围
- 是否要求确认

不允许：

- 只给自然语言，不给结构化参数
- 未声明目标位置或对象
- 用不完整数据触发批量编辑

## 结果模型

成功结果建议包含：

- `summary`：给人看的简短结果
- `data`：给模型继续推理的结构化数据
- `artifacts`：可选，记录导出文件、对象 ID、截图引用等
- `warnings`：可选，记录降级执行或潜在风险

示例：

```json
{
  "summary": "selection snapshot collected",
  "data": {
    "documentType": "schematic",
    "selectionCount": 3,
    "components": [
      { "id": "U1", "name": "STM32F103C8T6" }
    ]
  },
  "warnings": []
}
```

## 错误模型

错误包统一使用：

```json
{
  "code": "UNSUPPORTED_ACTION",
  "message": "pcb.place_footprint is not available in current adapter",
  "retryable": false,
  "details": {
    "domain": "pcb",
    "action": "place_footprint"
  }
}
```

建议错误码：

- `INVALID_REQUEST`
- `UNSUPPORTED_DOMAIN`
- `UNSUPPORTED_ACTION`
- `INVALID_PAYLOAD`
- `DOCUMENT_NOT_READY`
- `SELECTION_REQUIRED`
- `CONFIRMATION_REQUIRED`
- `EXECUTION_FAILED`
- `INTERNAL_ERROR`

## 确认门禁

以下操作建议默认要求确认：

- 批量放置或批量删除
- 连线可能覆盖现有网络关系
- 会修改大量对象的自动整理或自动标注
- 导出到外部路径或覆盖已有文件

确认响应示例：

```json
{
  "id": "req_20260407_0001",
  "type": "command.response",
  "protocolVersion": "0.1.0",
  "status": "confirmation_required",
  "confirmation": {
    "reason": "placing component will modify the current schematic",
    "riskLevel": "medium",
    "token": "confirm_req_20260407_0001"
  }
}
```

Codex 在收到后，不应自动假定确认已通过，而应等待显式确认流程。

## 建议执行流程

1. Codex 发送结构化请求
2. 插件做域检查、动作检查、参数检查
3. 如需确认，返回 `confirmation_required`
4. 如可执行，调用内部能力适配层
5. 返回成功结果或错误对象

## 与后续实现的关系

这一版协议对应后续两个实现方向：

- `src/bridge/`：协议类型、命令注册、校验与路由
- `src/adapters/`：JLCEDA 能力封装层

首个建议落地命令：

1. `system.ping`
2. `system.get_bridge_status`
3. `project.get_document_summary`
4. `project.get_selection_snapshot`

这样可以先把桥接探活和只读链路打通，再逐步引入写操作。
