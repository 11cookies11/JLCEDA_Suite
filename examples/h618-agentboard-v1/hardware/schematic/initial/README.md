# 初版原理图工程

这是 H618 AgentBoard V1 的第一版原理图工作目录。

## 目标

- 先把前四个高优先级分图落成真实 KiCad 工程。
- 以 `circuit-model.json` 和当前收口文档为依据，生成可打开、可继续编辑的原理图骨架。
- 同时接入本地 EasyEDA/JLC 库，逐步把元件来源统一到 JLC 体系。

## 当前范围

- `sheet_01_power_entry_pmic`
- `sheet_02_soc_boot_clock`
- `sheet_03_memory_ddr`
- `sheet_04_boot_storage`

## 说明

- 这里的文件由流水线生成或更新。
- 如果后续收口文档发生变化，应优先回到收口文档修改，再重新生成此目录下的工程文件。
- 任何要替换占位件的动作，优先使用 `libraries/` 里的 EasyEDA/JLC 资产。
