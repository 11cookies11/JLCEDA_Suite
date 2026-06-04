# 现有文件归位表

本文档把当前 `src/kicad_suite/` 的文件，按照已经确定的目标架构归位：

- `agent interface`：给 agent 的受控操作面
- `orchestration`：流程编排、重试、阶段切换
- `application services`：业务动作封装、状态管理、报告输出
- `domain/core`：模型、parts、IR、校验、计划编译
- `adapters`：KiCad / JLC / EasyEDA / ngspice / filesystem
- `tooling`：测试、示例、脚本、开发辅助

这是一份“重构导航图”，不是要求一次性把文件全部搬完。

## 1. 入口层

| 文件 | 归位 | 备注 |
|---|---|---|
| `src/kicad_suite/__main__.py` | `entrypoints` | Python 包入口，只做转发 |
| `src/kicad_suite/cli.py` | `entrypoints` | CLI 总入口，后续应继续瘦身 |
| `src/kicad_suite/server_text_to_kicad.py` | `entrypoints` | 对外服务/命令入口 |

## 2. 流程编排层

| 文件 | 归位 | 备注 |
|---|---|---|
| `src/kicad_suite/pipeline_coordinator.py` | `orchestration` | 主流水线导演 |
| `src/kicad_suite/circuit_pipeline.py` | `orchestration` | 兼容/流程辅助层，建议继续收口 |
| `src/kicad_suite/pipeline_postprocess.py` | `orchestration` | 输出后处理，不要再混兼容补丁 |
| `src/kicad_suite/pipeline_event_log.py` | `orchestration` | 流程事件记录 |
| `src/kicad_suite/pipeline_summary.py` | `orchestration` | 流程摘要生成 |
| `src/kicad_suite/project_resolution.py` | `orchestration` | 项目解析/决议写回 |

## 3. 应用服务层

| 文件 | 归位 | 备注 |
|---|---|---|
| `src/kicad_suite/model_api/service.py` | `application services` | 模型受控操作主服务 |
| `src/kicad_suite/model_api/commands.py` | `application services` | 请求/命令对象 |
| `src/kicad_suite/model_api/payloads.py` | `application services` | 请求载荷校验 |
| `src/kicad_suite/model_api/results.py` | `application services` | 结果对象 |
| `src/kicad_suite/model_api/repository.py` | `application services` | 模型仓储 |
| `src/kicad_suite/model_api/handlers_crud.py` | `application services` | CRUD 用例处理器 |
| `src/kicad_suite/model_api/handlers_extended.py` | `application services` | 扩展用例处理器，后续应拆分导出/批处理职责 |
| `src/kicad_suite/model_api/external_tools.py` | `application services` | 与外部工具交互的业务封装 |
| `src/kicad_suite/model_api/model.py` | `application services` | 模型对象与归一化 |
| `src/kicad_suite/model_api/validation.py` | `application services` | 模型请求和快照校验 |
| `src/kicad_suite/project_state.py` | `application services` | 项目状态管理 |
| `src/kicad_suite/report_system.py` | `application services` | 报告生成与格式化 |
| `src/kicad_suite/artifact_validator.py` | `application services` | 产物校验入口，偏应用层 |

## 4. 领域核心层

| 文件 | 归位 | 备注 |
|---|---|---|
| `src/kicad_suite/circuit_model_io.py` | `domain/core` | 模型读写和路径约定 |
| `src/kicad_suite/ir_compiler.py` | `domain/core` | circuit-model -> IR |
| `src/kicad_suite/ir_validator.py` | `domain/core` | IR 校验 |
| `src/kicad_suite/ir_to_kicad.py` | `domain/core` | IR -> KiCad plan |
| `src/kicad_suite/compile_kicad_execution_plan.py` | `domain/core` | KiCad 执行计划编译 |
| `src/kicad_suite/parts/resolve.py` | `domain/core` | parts 解析与选择规则 |
| `src/kicad_suite/parts/workflow.py` | `domain/core` | parts 主流程，里面的 fallback 仍需继续收敛 |
| `src/kicad_suite/parts/report.py` | `domain/core` | parts 结果汇总 |
| `src/kicad_suite/validation/common.py` | `domain/core` | 统一校验工具 |
| `src/kicad_suite/validation/erc.py` | `domain/core` | ERC 校验逻辑 |
| `src/kicad_suite/validation/plan.py` | `domain/core` | 计划校验逻辑 |
| `src/kicad_suite/validation/summary.py` | `domain/core` | 摘要校验逻辑 |
| `src/kicad_suite/part_selector.py` | `domain/core` | 器件选择策略 |
| `src/kicad_suite/pin_manager.py` | `domain/core` | 引脚映射/分配规则 |
| `src/kicad_suite/schematic_layout_rules.py` | `domain/core` | 原理图布局规则 |
| `src/kicad_suite/simulation_planner.py` | `domain/core` | 仿真计划构建 |
| `src/kicad_suite/netlist_builder.py` | `domain/core` | 网表构建 |

## 5. 外部适配层

| 文件 | 归位 | 备注 |
|---|---|---|
| `src/kicad_suite/adapters/kicad_cli.py` | `adapters` | KiCad CLI 适配 |
| `src/kicad_suite/adapters/jlc_mcp.py` | `adapters` | JLC MCP 适配 |
| `src/kicad_suite/jlc_api.py` | `adapters` | JLC 接口封装 |
| `src/kicad_suite/jlc_installer.py` | `adapters` | JLC 资源安装 |
| `src/kicad_suite/lcsc_resolver.py` | `adapters` | LCSC 查询/解析 |
| `src/kicad_suite/easyeda_parser.py` | `adapters` | EasyEDA 解析 |
| `src/kicad_suite/easyeda_converter.py` | `adapters` | EasyEDA -> KiCad 转换 |
| `src/kicad_suite/kicad_lib_importer.py` | `adapters` | KiCad 库导入 |
| `src/kicad_suite/kicad_project_writer.py` | `adapters` | KiCad 工程/原理图写出 |
| `src/kicad_suite/kicad_erc_runner.py` | `adapters` | KiCad ERC 运行 |
| `src/kicad_suite/board_generator.py` | `adapters` | PCB/板级输出适配 |
| `src/kicad_suite/pcb_generator.py` | `adapters` | PCB 生成适配 |
| `src/kicad_suite/symbol_footprint_resolver.py` | `adapters` | 符号/封装映射解析 |

## 6. 工具与支撑层

| 文件 | 归位 | 备注 |
|---|---|---|
| `src/kicad_suite/env_utils.py` | `cross-cutting` | 路径、环境变量、运行时小工具 |
| `src/kicad_suite/example_scaffold.py` | `tooling` | 示例项目脚手架 |
| `src/kicad_suite/ngspice_regression_test.py` | `tooling` | 回归测试脚本 |
| `src/kicad_suite/elk_layout_runner.mjs` | `tooling` | 布局引擎外部脚本 |

## 7. 需要继续拆的混层文件

这些文件虽然已经有了归位方向，但当前实现里仍混着多层职责，是后续重构优先级最高的对象：

| 文件 | 当前问题 |
|---|---|
| `src/kicad_suite/cli.py` | 命令解析、业务调度、状态更新混在一起 |
| `src/kicad_suite/pipeline_coordinator.py` | 编排、文件处理、重写、ERC、报告混在一起 |
| `src/kicad_suite/model_api/service.py` | 大量 `if-else` 分发，缺少显式 command/handler 注册 |
| `src/kicad_suite/model_api/handlers_extended.py` | 导出、批处理、查询、metadata 操作混在一起 |
| `src/kicad_suite/kicad_project_writer.py` | 写出、清洗、兼容、资源定位混在一起 |
| `src/kicad_suite/compile_kicad_execution_plan.py` | 计划生成和历史兼容策略还未完全分离 |
| `src/kicad_suite/parts/workflow.py` | 解析、选择、fallback、importer 逻辑耦合较重 |

## 8. 建议的拆分顺序

1. 先把 `cli.py` 拆成“参数解析 + 命令入口 + 结果输出”。
2. 再把 `model_api/service.py` 改成 command/handler 注册表。
3. 然后把 `pipeline_coordinator.py` 拆成纯编排骨架。
4. 接着把 `kicad_project_writer.py` 和 `compile_kicad_execution_plan.py` 的职责拆干净。
5. 最后处理 `parts/workflow.py` 和 `symbol_footprint_resolver.py` 的 fallback 与策略分发。
