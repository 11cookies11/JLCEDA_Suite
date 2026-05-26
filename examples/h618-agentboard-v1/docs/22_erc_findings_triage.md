# H618 AgentBoard V1 ERC findings 分类

本文记录当前 H618 AgentBoard V1 首版 KiCad 原理图的 ERC 收口结果，用于后续继续细化原理图设计。

## 当前结论

- pipeline 可以生成 KiCad 工程、原理图、PCB 初始文件和 ERC 报告。
- `unsupported` 为空，说明当前 `circuit-model.json` 没有无法映射的器件。
- GUI 资产校验通过，符号、封装和 3D 资产没有阻塞级缺失。
- KiCad ERC 当前为 `0` findings。
- 当前生成结果包含 `44` 个符号、`73` 条网络。
- `pin_to_pin`、`multiple_net_names`、`unconnected_wire_endpoint`、`missing_unit`、`pin_not_connected`、`pin_not_driven` 均已清零。
- 之前剩余的 `lib_symbol_mismatch` 已通过本地缓存符号同步收口。
- 当前 LPDDR4 仍是首版骨架级映射，不能视为最终可布线 DDR 设计。

## 最新 ERC 数量分布

- `total`: 0
- `pin_to_pin`: 0
- `footprint_link_issues`: 0
- `lib_symbol_issues`: 0
- `lib_symbol_mismatch`: 0
- `multiple_net_names`: 0
- `unconnected_wire_endpoint`: 0
- `missing_unit`: 0
- `pin_not_connected`: 0
- `pin_not_driven`: 0

## 已完成的拓扑收口

- SPI NOR 启动信号已拆分为 `H618_SPI0_CS0`、`H618_SPI0_CLK`、`H618_SPI0_MOSI`、`H618_SPI0_MISO`。
- MicroSD 启动信号已拆分为 `H618_SD_CLK`、`H618_SD_CMD`、`H618_SD_D0`、`H618_SD_D1`、`H618_SD_D2`、`H618_SD_D3`。
- USB hub 上游和下游 D+/D- 已拆分为独立差分网络。
- RGMII、MDC/MDIO、26pin GPIO、USB-C VBUS/GND、24MHz/32kHz 晶振和 LPDDR4 最小骨架已从聚合网收敛为单线网络。
- USB-C、SPI NOR、MicroSD、晶振等关键器件已按 EasyEDA/JLC 符号真实脚位修正。
- PMIC、RTL8211F、USB2514B 等器件已从语义 pin 名收敛到 EasyEDA/JLC 符号脚位。
- H618 最小符号 pinmap、DDR alias 解析、DDR 多单元放置和 no-connect 坐标保护已补齐到当前首版所需范围。
- USB-C 电源入口已补入 CC1/CC2 独立 5.1k Rd 下拉，明确把 J1 配置为默认电流 Sink 输入。
- USB-C 电源入口已修正为 `J1 VBUS -> +5V_IN -> F1 -> +5V_SYS`，`D1` TVS 接在原始 VBUS 与 GND 之间，避免保险丝输出端误接地。

## 库缓存一致性收口

- pipeline 会从生成后的各分图提取缓存符号，并同步到本地 `libraries/symbols/*.kicad_sym`。
- 本地 `sym-lib-table` 会注册同步后的符号库，避免 KiCad ERC 把缓存符号与库符号识别为不一致。
- 最新运行中已同步 `Device`、`JLC-MCP-Diodes`、`JLC-MCP-Inductors`、`JLC-MCP-Misc`、`JLC-MCP-Resistors`、`Switch`、`jlc_symbols`、`power` 共 8 个缓存符号库。

## 后续设计提醒

- 当前 ERC 归零表示首版生成拓扑在 KiCad 层面无 ERC findings，不等于所有高速、电源时序和 DDR 细节已经最终定版。
- 后续应继续按参考设计补全 H618/DDR 全量 pinmap、DDR 拓扑、RGMII strap、USB-C CC/保护、电源时序和以太网磁性器件等真实设计内容。
- PCB 摆放和布线暂不作为本阶段目标，当前优先保持原理图输入格式和生成链路稳定。
