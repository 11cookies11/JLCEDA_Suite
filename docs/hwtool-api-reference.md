# hwtool API 参考 / API Reference

## CLI 命令 / CLI Commands

### agent manifest

```powershell
hwtool agent manifest
```

返回所有可用命令和项目文件路径的 JSON 描述。

### agent status

```powershell
hwtool agent status --project <dir>
```

返回项目状态：`{ "status": "VALID", "stale": false }`。
状态值：`INIT` → `DIRTY` → `VALID` | `INVALID` → `BUILT` | `BUILD_FAILED`

### agent inspect

```powershell
hwtool agent inspect --project <dir> [--model <path>]
```

返回项目详情：状态、DSL 摘要、构建信息、源模型统计。

### agent explain

```powershell
hwtool agent explain --project <dir>
```

返回人类可读的项目说明文本。

### agent doctor

```powershell
hwtool agent doctor --project <dir> [--model <path>]
```

检查环境：Python 版本、项目目录、circuit-model.json、资源路径、ngspice。

### agent history

```powershell
hwtool agent history --project <dir> [-n <limit>]
```

返回操作历史 JSON 数组。

### agent self-test

```powershell
hwtool agent self-test [--filter <pytest-expr>]
```

运行测试套件。`--filter` 支持 pytest `-k` 表达式。

---

## 项目生命周期 / Project Lifecycle

### agent create

```powershell
hwtool agent create <project_dir> \
  [--project-id <id>] \
  [--topology <name>] \
  [--title <title>] \
  [--source-model <path>] \
  [--overwrite] \
  [--export-ir]
```

创建新硬件项目，包含 `circuit-model.json` 骨架。可指定源模型模板。

### agent build-ir

```powershell
hwtool agent build-ir --project <dir> [--model <path>] [--output <path>]
```

`circuit-model.json` → `build/ir.v1.json`

### agent validate-ir

```powershell
hwtool agent validate-ir --project <dir> [--model <path>] [--output <path>]
```

编译并验证 IR。返回诊断数组，每条包含 `code`、`message`、`location`、`suggestion`。

### agent rule-check

```powershell
hwtool agent rule-check --project <dir> [--model <path>] \
  [--payload-json <json>] [--payload-file <path>] \
  [--dry-run] [--validate-only] [--no-commit]
```

运行项目就绪检查。

### agent build-kicad-plan

```powershell
hwtool agent build-kicad-plan --project <dir> [--model <path>] \
  [--payload-json <json>] [--payload-file <path>]
```

从 IR 编译 KiCad 执行计划。

### agent export-kicad / agent build-kicad

```powershell
hwtool agent export-kicad --project <dir> \
  [--model <path>] \
  [--output-dir <path>] \
  [--project-name <name>]
```

完整流水线：编译 IR → 原理图 → PCB → ERC → 报告。

### agent resolve-symbols

```powershell
hwtool agent resolve-symbols --project <dir> [--model <path>] \
  [--timeout 120] [--delay 0.8]
```

根据 `selected_part.lcsc_id` 从 JLC/EasyEDA 下载符号和封装到 `libraries/`。自动更新 `kicad_footprint_hint`。

### agent report

```powershell
hwtool agent report --project <dir> \
  [--output-json <path>] [--output-md <path>] [--markdown]
```

生成 `build/report.json` 和 `build/report.md`。

---

## JLC / LCSC 元件 / JLC Commands

### agent jlc search

```powershell
hwtool agent jlc search <query> [-n <limit>]
```

搜索 LCSC 元件。返回：`lcsc_id`, `name`, `package`, `stock`, `price`, `is_basic`。

### agent jlc info

```powershell
hwtool agent jlc info <lcsc_id>
```

预览元件信息（不下载文件）。返回：`title`, `package`, `pin_count`, `shape_count`。

### agent jlc download

```powershell
hwtool agent jlc download --project <dir> --lcsc-id <id>
hwtool agent jlc download --project <dir> --query <keyword> [--auto] [-n <limit>]
```

下载单个元件的符号 + 封装。

---

## 引脚管理 / Pin Management

### agent pins free

```powershell
hwtool agent pins free --project <dir> --ref <ref> [--mcu-family <family>] [--model <path>]
```

列出指定 MCU 的空闲 GPIO。

### agent pins assign

```powershell
hwtool agent pins assign --project <dir> \
  --ref <ref> --pin <pin> --net <net> \
  [--role <role>]
```

连接引脚到网络。

### agent pins check

```powershell
hwtool agent pins check --project <dir> [--mcu-family <family>] [--model <path>]
```

检查引脚冲突。

---

## 直接模型操作 / Direct Model Manipulation

### agent patch

```powershell
hwtool agent patch --project <dir> \
  [--model <path>] \
  --payload-json '<json-patch>'
```

对 `circuit-model.json` 应用 JSON patch。配合 `agent build-ir` 使用可增量修改模型。

### agent run

```powershell
hwtool agent run <operation> --project <dir> \
  [--model <path>] \
  --payload-json '<json>'
```

执行单个 DSL API 操作。所有支持的操作如下：

#### 模型管理 / Model Management

| Operation | 说明 | Payload |
|-----------|------|---------|
| `load_model` | 加载模型 | `{}` |
| `save_model` | 保存模型 | `{}` |
| `clone_model` | 克隆模型 | `{"source":"path"}` |
| `reset_model` | 重置模型 | `{}` |
| `diff_model` | 模型差异 | `{"other":"path"}` |
| `merge_model` | 合并模型 | `{"source":"path"}` |
| `patch_model` | JSON patch | `{"patch":[...]}` |
| `validate_model` | 验证模型 | `{}` |
| `validate_schema` | 验证 schema | `{}` |
| `validate_references` | 验证引用完整性 | `{}` |
| `validate_connectivity` | 验证连接 | `{}` |
| `validate_ir` | 验证 IR | `{}` |

#### 元数据 / Metadata

| Operation | Payload |
|-----------|---------|
| `get_metadata` | `{}` |
| `update_metadata` | `{"key":"value",...}` |
| `set_schema_version` | `{"value":"circuit-model.v1"}` |
| `set_request_id` | `{"value":"id"}` |
| `set_project_id` | `{"value":"id"}` |
| `set_topology` | `{"value":"name"}` |

#### 组件 / Components

| Operation | Payload |
|-----------|---------|
| `add_component` | `{"ref":"U1","role":"mcu","value":"ESP32-C3","package":"QFN-32"}` |
| `update_component` | `{"ref":"U1","role":"mcu","value":"..."}` |
| `remove_component` | `{"ref":"U1"}` |
| `get_component` | `{"ref":"U1"}` |
| `list_components` | `{}` |
| `search_components` | `{"query":"mcu"}` |
| `set_component_ref` | `{"ref":"U1","value":"U2"}` |
| `set_component_role` | `{"ref":"U1","value":"mcu"}` |
| `set_component_value` | `{"ref":"U1","value":"100nF"}` |
| `set_component_notes` | `{"ref":"U1","notes":["..."]}` |
| `set_component_availability` | `{"ref":"U1","value":"available"}` |
| `set_component_search_hints` | `{"ref":"U1","hints":["esp32"]}` |
| `assign_component_to_sheet` | `{"ref":"U1","sheet":"power"}` |
| `mark_component_resolved` | `{"ref":"U1"}` |
| `mark_component_needs_review` | `{"ref":"U1"}` |
| `mark_component_blocked` | `{"ref":"U1"}` |

#### 网络 / Nets

| Operation | Payload |
|-----------|---------|
| `add_net` | `{"name":"+3V3","kind":"power"}` |
| `update_net` | `{"name":"+3V3","kind":"power"}` |
| `remove_net` | `{"name":"+3V3"}` |
| `get_net` | `{"name":"+3V3"}` |
| `list_nets` | `{}` |
| `search_nets` | `{"query":"3V3"}` |
| `connect_member` | `{"net":"+3V3","member":"U1.1"}` |
| `connect_members` | `{"net":"+3V3","members":["U1.1","C1.1"]}` |
| `disconnect_member` | `{"net":"+3V3","member":"U1.1"}` |
| `disconnect_members` | `{"net":"+3V3","members":["U1.1"]}` |
| `rename_net` | `{"name":"VCC","value":"+3V3"}` |
| `merge_nets` | `{"source":"VCC","target":"+3V3"}` |
| `split_net` | `{"source":"+3V3","members":["U1.1"],"new_name":"VDD_ANA"}` |
| `set_net_kind` | `{"name":"LED","value":"signal"}` |
| `set_net_notes` | `{"name":"LED","notes":["..."]}` |
| `set_net_aliases` | `{"name":"+3V3","aliases":["VCC"]}` |
| `set_net_domain` | `{"name":"+3V3","domain":"analog"}` |
| `mark_net_global` | `{"name":"GND"}` |
| `mark_net_power` | `{"name":"+3V3"}` |
| `mark_net_high_speed` | `{"name":"USB_DP"}` |
| `mark_net_debug` | `{"name":"SWCLK"}` |
| `mark_net_differential_pair` | `{"name":"USB_DP","pair":"USB_DN"}` |
| `assign_net_to_sheet` | `{"name":"+3V3","sheet":"power"}` |

#### 引脚映射 / Pinmap

| Operation | Payload |
|-----------|---------|
| `set_pinmap` | `{"ref":"U1","pinmap":{"1":"+3V3","2":"GND"}}` |
| `update_pinmap` | `{"ref":"U1","pin":"1","net":"+3V3"}` |
| `remove_pinmap` | `{"ref":"U1"}` |
| `get_pinmap` | `{"ref":"U1"}` |
| `validate_pinmap` | `{"ref":"U1"}` |
| `connect_pin_to_net` | `{"ref":"U1","pin":"1","net":"+3V3"}` |
| `disconnect_pin_from_net` | `{"ref":"U1","pin":"1"}` |
| `set_pin_name` | `{"ref":"U1","pin":"1","value":"VDD"}` |
| `set_pin_role` | `{"ref":"U1","pin":"1","value":"power"}` |
| `set_pin_direction` | `{"ref":"U1","pin":"1","value":"input"}` |
| `set_pin_no_connect` | `{"ref":"U1","pin":"5"}` |
| `add_pin_alias` | `{"ref":"U1","pin":"1","alias":"GPIO0"}` |
| `resolve_pin_alias` | `{"ref":"U1","alias":"GPIO0"}` |

#### 电源轨 / Power Rails

| Operation | Payload |
|-----------|---------|
| `add_power_rail` | `{"name":"+3V3","source_net":"+3V3","voltage":3.3}` |
| `update_power_rail` | `{"name":"+3V3","voltage":3.3}` |
| `remove_power_rail` | `{"name":"+3V3"}` |
| `get_power_rail` | `{"name":"+3V3"}` |
| `list_power_rails` | `{}` |
| `set_rail_source` | `{"name":"+3V3","source_net":"+3V3"}` |
| `set_rail_sink` | `{"name":"+3V3","sink":"U1"}` |
| `set_rail_parent` | `{"name":"+3V3","parent":"+5V"}` |
| `set_rail_children` | `{"name":"+5V","children":["+3V3","+1V8"]}` |
| `set_rail_voltage` | `{"name":"+3V3","voltage":3.3}` |
| `set_rail_current_limit` | `{"name":"+3V3","limit":0.5}` |
| `set_rail_sequence_order` | `{"name":"+3V3","order":2}` |
| `set_rail_enable_condition` | `{"name":"+3V3","condition":"+5V > 4.5"}` |
| `add_rail_test_point` | `{"rail":"+3V3","tp":"TP1"}` |
| `bind_rail_to_test_point` | `{"rail":"+3V3","tp":"TP1"}` |
| `validate_power_tree` | `{}` |
| `validate_power_budget` | `{}` |
| `validate_sequence` | `{}` |

#### 原理图分页 / Sheets

| Operation | Payload |
|-----------|---------|
| `add_sheet` | `{"name":"power","components":["U2"],"nets":["+3V3"]}` |
| `update_sheet` | `{"name":"power","components":["U2","C1"]}` |
| `remove_sheet` | `{"name":"power"}` |
| `get_sheet` | `{"name":"power"}` |
| `list_sheets` | `{}` |
| `search_sheets` | `{"query":"power"}` |
| `set_sheet_name` | `{"name":"power","value":"power_supply"}` |
| `set_sheet_inputs` | `{"name":"power","inputs":["+5V"]}` |
| `set_sheet_outputs` | `{"name":"power","outputs":["+3V3"]}` |
| `set_sheet_components` | `{"name":"power","components":["U2"]}` |
| `set_sheet_nets` | `{"name":"power","nets":["+3V3"]}` |
| `set_sheet_constraints` | `{"name":"power","constraints":["..."]}` |
| `set_sheet_notes` | `{"name":"power","notes":["..."]}` |
| `validate_sheet_boundary` | `{"name":"power"}` |
| `validate_sheet_inputs_outputs` | `{"name":"power"}` |

#### 计算 / Calculations

| Operation | Payload |
|-----------|---------|
| `add_calculation` | `{"name":"i_led","formula":"(V-Vf)/R","inputs":{"V":3.3,"Vf":2.0,"R":1000},"unit":"A"}` |
| `update_calculation` | `{"name":"i_led","formula":"..."}` |
| `remove_calculation` | `{"name":"i_led"}` |
| `get_calculation` | `{"name":"i_led"}` |
| `list_calculations` | `{}` |
| `search_calculations` | `{"query":"led"}` |
| `recompute_calculation` | `{"name":"i_led"}` |
| `set_calculation_formula` | `{"name":"i_led","formula":"V/R"}` |
| `set_calculation_inputs` | `{"name":"i_led","inputs":{"V":3.3,"R":1000}}` |
| `set_calculation_result` | `{"name":"i_led","result":0.0033}` |
| `set_calculation_unit` | `{"name":"i_led","unit":"A"}` |
| `link_calculation_to_component` | `{"name":"i_led","component":"R3"}` |
| `link_calculation_to_net` | `{"name":"i_led","net":"LED"}` |

#### 设计决策 / Design Decisions

| Operation | Payload |
|-----------|---------|
| `add_design_decision` | `{"title":"Use 8MHz crystal","rationale":"Better USB accuracy"}` |
| `update_design_decision` | `{"title":"...","rationale":"..."}` |
| `remove_design_decision` | `{"title":"..."}` |
| `get_design_decision` | `{"title":"..."}` |
| `list_design_decisions` | `{}` |
| `search_design_decisions` | `{"query":"crystal"}` |
| `mark_decision_proposed` | `{"title":"..."}` |
| `mark_decision_accepted` | `{"title":"..."}` |
| `mark_decision_rejected` | `{"title":"..."}` |
| `mark_decision_needs_review` | `{"title":"..."}` |
| `mark_decision_finalized` | `{"title":"..."}` |
| `link_decision_to_component` | `{"title":"...","component":"U1"}` |
| `link_decision_to_net` | `{"title":"...","net":"+3V3"}` |
| `link_decision_to_risk` | `{"title":"...","risk":"..."}` |
| `link_decision_to_sheet` | `{"title":"...","sheet":"mcu"}` |

#### 风险 / Risks

| Operation | Payload |
|-----------|---------|
| `add_risk` | `{"title":"Power sequencing issue"}` |
| `update_risk` | `{"title":"...","description":"..."}` |
| `remove_risk` | `{"title":"..."}` |
| `get_risk` | `{"title":"..."}` |
| `list_risks` | `{}` |
| `search_risks` | `{"query":"power"}` |
| `mark_risk_open` | `{"title":"..."}` |
| `mark_risk_in_progress` | `{"title":"..."}` |
| `mark_risk_blocked` | `{"title":"..."}` |
| `mark_risk_resolved` | `{"title":"..."}` |
| `mark_risk_deferred` | `{"title":"..."}` |
| `set_risk_category` | `{"title":"...","category":"power"}` |
| `set_risk_severity` | `{"title":"...","severity":"high"}` |
| `set_risk_owner` | `{"title":"...","owner":"hardware"}` |
| `set_risk_due_reason` | `{"title":"...","due":"2026-06-01","reason":"..."}` |
| `link_risk_to_component` | `{"title":"...","component":"U1"}` |
| `link_risk_to_net` | `{"title":"...","net":"+3V3"}` |
| `link_risk_to_decision` | `{"title":"...","decision":"..."}` |
| `link_risk_to_sheet` | `{"title":"...","sheet":"mcu"}` |
| `validate_risk_consistency` | `{}` |

#### 约束 / Constraints

| Operation | Payload |
|-----------|---------|
| `add_constraint` | `{"name":"trace_width","type":"pcb","scope":"+3V3","rules":["min_width:0.25mm"]}` |
| `update_constraint` | `{"name":"trace_width","rules":["..."]}` |
| `remove_constraint` | `{"name":"trace_width"}` |
| `get_constraint` | `{"name":"trace_width"}` |
| `list_constraints` | `{}` |
| `set_constraint_type` | `{"name":"...","type":"pcb"}` |
| `set_constraint_scope` | `{"name":"...","scope":"+3V3"}` |
| `set_constraint_priority` | `{"name":"...","priority":"high"}` |
| `set_constraint_status` | `{"name":"...","status":"active"}` |

#### 元件选型 / Part Selection

| Operation | Payload |
|-----------|---------|
| `select_part` | `{"ref":"U1","lcsc_id":"C8734"}` |
| `set_selected_part` | `{"ref":"U1","lcsc_id":"C8734","display_name":"STM32F103"}` |
| `update_selected_part` | `{"ref":"U1","lcsc_id":"C8734"}` |
| `replace_selected_part` | `{"ref":"U1","lcsc_id":"C8735"}` |
| `add_candidate_part` | `{"ref":"U1","lcsc_id":"C8735","display_name":"..."}` |
| `remove_candidate_part` | `{"ref":"U1","lcsc_id":"C8735"}` |
| `lock_selected_part` | `{"ref":"U1"}` |
| `unlock_selected_part` | `{"ref":"U1"}` |
| `validate_part_availability` | `{"ref":"U1"}` |
| `validate_readiness` | `{}` |

#### 事务 / Transactions

| Operation | Payload | 说明 |
|-----------|---------|------|
| `begin_transaction` | `{}` | 开始事务 |
| `apply_operation` | `{"operation":"add_component","payload":{...}}` | 事务内应用操作 |
| `apply_batch` | `{"operations":[{...},{...}]}` | 批量应用 |
| `dry_run` | `{"operations":[{...}]}` | 试运行 |
| `commit_transaction` | `{}` | 提交事务 |
| `rollback_transaction` | `{}` | 回滚事务 |
| `diff_transaction` | `{}` | 事务差异 |

#### 导出 / Export

| Operation | Payload |
|-----------|---------|
| `build_ir` | `{}` |
| `compile_netlist` | `{}` |
| `compile_spice_netlist` | `{}` |
| `compile_kicad_execution_plan` | `{}` |
| `create_project_template` | `{"project_id":"...","topology":"..."}` |
| `create_hardware_project` | `{"project_dir":".","project_id":"...","topology":"..."}` |
| `export_circuit_model` | `{"output_path":"..."}` |
| `export_ir` | `{"output_path":"..."}` |
| `export_kicad_project` | `{"output_dir":"./output","project_name":"..."}` |
| `export_summary` | `{}` |
| `export_report` | `{}` |
| `run_erc` | `{}` |
| `run_simulation_plan` | `{"output_dir":"./sim"}` |

---

## 环境变量 / Environment Variables

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KICAD_PYTHON_BIN` | KiCad 自带的 python.exe | 自动检测 |
| `KICAD_CLI` | kicad-cli.exe 路径 | 自动检测 |
| `KICAD_OUTPUT_DIR` | 输出根目录 | plan 决定 |
| `KICAD_PROJECT_NAME` | 项目名 | model 决定 |
| `KICAD_SOURCE_PROJECT_DIR` | 项目根目录 | — |
| `KICAD_GENERATE_PCB` | 是否生成 PCB | `true` |
| `KICAD_FOOTPRINT_DIR` | 封装库额外路径 | — |
| `KICAD_EXTRA_FOOTPRINT_DIR` | 额外封装库 | — |
| `KICAD_LAYOUT_PROFILES_FILE` | 布局配置 | `config/kicad-layout-profiles.json` |

## 项目文件布局 / Project Layout

```
project/
├── circuit-model.json      ✏️  源文件（AI 编写）
├── project.state.json      状态机
├── logs/
│   └── operations.jsonl    操作日志
├── build/
│   ├── ir.v1.json          中间表示
│   ├── ir-validation.json  验证报告
│   ├── rule-check.json     规则检查
│   ├── report.json         JSON 报告
│   └── report.md           Markdown 报告
├── libraries/
│   ├── symbols/            .kicad_sym 文件
│   └── footprints/
│       └── JLC-MCP.pretty/ .kicad_mod 文件
├── output/<topology>/
│   ├── <topology>.kicad_pro  项目
│   ├── <topology>.kicad_sch  原理图
│   ├── <topology>.kicad_pcb  PCB
│   ├── *.erc.json            ERC
│   ├── fp-lib-table          封装表
│   ├── sym-lib-table         符号表
│   └── agent-report.json     Agent 报告
├── schemas/
│   ├── circuit-model.v1.json
│   ├── ir.v1.json
│   └── dsl-api-*.json
└── config/
    └── kicad-layout-profiles.json
```
