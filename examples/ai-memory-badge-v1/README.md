# AI Memory Badge V1

全天候随身 AI 记忆器原型项目。

本版本先定义产品需求和系统设计，不急于锁定完整原理图。目标是做一块可佩戴、可夹持、低功耗、以人声触发录音为核心的硬件原型板。

## Product Direction

- 形态：胸牌 / 夹子
- 录音策略：人声触发录音，支持手动标记重点片段
- 隐私策略：本地加密预留，录音状态可见，支持物理静音
- 同步方式：USB-C + Wi-Fi
- 设计优先级：续航优先，其次是可接受的人声清晰度
- 项目阶段：原型板，不追求第一版直接小型量产

## Documents

- `docs/00_requirements.md`：产品需求与约束
- `docs/01_system_architecture.md`：系统架构和模块划分
- `docs/02_design_decisions.md`：关键设计取舍
- `docs/03_hardware_design_plan.md`：硬件设计方案与验证计划
- `docs/04_component_selection.md`：Rev A 器件选型方向
- `docs/05_esp32s3_bare_chip_design.md`：ESP32-S3 裸芯片实现方案
- `docs/06_schematic_module_plan.md`：原理图模块拆分方案
- `docs/07_part_resolution_notes.md`：关键器件解析状态与候选料

## Next Step

确认需求后，下一步生成：

```text
source/circuit-model.source.json
```

并进入 KiCad Agent Suite 的标准流程：

```powershell
hwtool agent inspect --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown
```
