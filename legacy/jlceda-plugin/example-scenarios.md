# 示例场景

## 场景 1：查看当前工程摘要

目标：

- 让 Codex 获取当前活动文档、工程、工作区与选区摘要

对应命令：

```json
{
  "id": "demo_read_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "project",
    "action": "get_document_summary",
    "payload": {}
  }
}
```

预期结果：

- 返回 `success`
- `result.data.document` 包含当前文档类型与 UUID
- `result.data.selection` 包含选区数量摘要

## 场景 2：放置一个原理图器件

目标：

- 在原理图上放置一个明确指定的库器件

对应命令：

```json
{
  "id": "demo_write_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "schematic",
    "action": "place_component",
    "requiresConfirmation": true,
    "payload": {
      "libraryUuid": "system-library-uuid",
      "uuid": "component-uuid",
      "position": { "x": 1200, "y": 800 },
      "rotation": 0,
      "mirror": false,
      "addIntoBom": true,
      "addIntoPcb": true
    }
  }
}
```

预期结果：

- 首次调用返回 `confirmation_required`
- 确认通过后的执行结果为 `success`
- 返回图元 ID、名称、位置等信息

## 场景 3：创建原理图导线

目标：

- 按显式点位创建一段网络导线

对应命令：

```json
{
  "id": "demo_write_002",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "schematic",
    "action": "create_wire",
    "requiresConfirmation": true,
    "payload": {
      "points": [
        { "x": 1200, "y": 800 },
        { "x": 1400, "y": 800 },
        { "x": 1400, "y": 1000 }
      ],
      "netName": "VCC_3V3"
    }
  }
}
```

预期结果：

- 首次调用返回 `confirmation_required`
- 确认通过后返回导线图元 ID 与线段坐标

## 场景 4：导出工程 BOM

目标：

- 生成一个 BOM 文件，并在需要时触发本地保存

对应命令：

```json
{
  "id": "demo_export_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "project",
    "action": "export_bom",
    "requiresConfirmation": true,
    "payload": {
      "format": "csv",
      "fileName": "demo-bom.csv",
      "saveToLocal": false
    }
  }
}
```

预期结果：

- 首次调用返回 `confirmation_required`
- 确认通过后返回文件名、文件大小、文件类型等导出元数据

## 场景 5：未实现命令的保护行为

目标：

- 验证桥接层不会静默执行未实现命令

对应命令：

```json
{
  "id": "demo_guard_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "pcb",
    "action": "place_footprint",
    "requiresConfirmation": false,
    "payload": {
      "footprintId": "fp_001",
      "position": { "x": 1000, "y": 1000 }
    }
  }
}
```

预期结果：

- 返回 `error`
- `error.code` 为 `UNSUPPORTED_ACTION`
- 错误信息明确说明命令已登记但尚未实现

## 场景 6：查看项目库存

目标：

- 获取当前工作区、团队、工程、原理图、PCB 和板子的聚合清单

对应命令：

```json
{
  "id": "demo_inventory_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "project",
    "action": "get_inventory",
    "payload": {}
  }
}
```

预期结果：

- 返回 `success`
- `result.data.current.project` 至少包含当前工程的 UUID 与友好名称
- `result.data.projectSections` 包含按团队整理的工程列表

## 场景 7：在 PCB 上放置封装

目标：

- 在 PCB 画布中明确放置一个封装图元

对应命令：

```json
{
  "id": "demo_pcb_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "pcb",
    "action": "place_footprint",
    "requiresConfirmation": false,
    "payload": {
      "libraryUuid": "footprint-library-uuid",
      "uuid": "footprint-uuid",
      "position": { "x": 1000, "y": 1000 },
      "rotation": 0,
      "layer": "top"
    }
  }
}
```

预期结果：

- 返回 `success`
- `result.data.primitiveId` 和位置信息可用于后续定位

## 场景 8：打开文档并切换分屏

目标：

- 通过编辑器控制命令打开一个文档，并把它放到指定分屏中

对应命令：

```json
{
  "id": "demo_editor_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "project",
    "action": "open_document",
    "payload": {
      "documentUuid": "schematic-001"
    }
  }
}
```

预期结果：

- 返回 `success`
- `result.data.tabId` 是新打开的标签页 ID
- 可继续调用 `project.create_split_screen`、`project.move_document_to_split_screen`、`project.activate_document`

## 场景 9：执行文档级保存与 DRC

目标：

- 对原理图或 PCB 文档执行保存、定位和 DRC 检查

对应命令：

```json
{
  "id": "demo_doc_001",
  "type": "command.request",
  "protocolVersion": "0.1.0",
  "sessionId": "demo_session",
  "command": {
    "domain": "schematic",
    "action": "check_drc",
    "requiresConfirmation": true,
    "payload": {
      "strict": true,
      "userInterface": false,
      "includeVerboseError": true
    }
  }
}
```

预期结果：

- 首次调用返回 `confirmation_required`
- 确认通过后返回 DRC 结果数组或布尔值
- 同类操作还包括 `schematic.save`、`schematic.navigate_to_coordinates`、`pcb.save`、`pcb.zoom_to_board_outline`
