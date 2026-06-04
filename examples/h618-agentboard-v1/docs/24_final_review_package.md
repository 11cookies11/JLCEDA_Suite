# H618 AgentBoard V1 可打样前审查包

本文件是给最终统一讨论用的底稿。它把当前 H618 AgentBoard V1 的原理图、风险、测量点、以及最后需要复核的事项收拢成一份可审查材料。

## 1. 当前结论

- KiCad 工程已经可以稳定生成。
- KiCad ERC 当前为 `0` findings。
- `source/circuit-model.source.json` 到 KiCad 原理图的 pipeline 已经打通。
- `.where` 产物与 example 工程目录已镜像一致。
- 当前工程已经可以进入硬件评审，也具备直接下单打样的基础条件。

## 2. 当前已解决的主链路

### 电源与复位

- USB-C 输入已明确为 `J1 VBUS -> +5V_IN -> F1 -> +5V_SYS`。
- `R5 / R6` 已作为 `CC1 / CC2` 的 5.1k sink Rd。
- `R3` 已作为 `H618_PMIC_PWRON` 默认上拉。
- `R7 / R8` 已作为 `RESET_N / FEL_BOOT` 默认上拉。
- `TP1` 到 `TP4` 已作为关键电源测点。

### 启动与恢复

- `UART0` 已作为第一条软件可见日志路径。
- `MicroSD` 与 `SPI NOR` 已分开表达各自职责。
- `FEL` 恢复路径已保留。
- `WP# / HOLD#` 已默认上拉，避免 SPI NOR 进入非预期暂停状态。

### DDR

- `LPDDR4` 已纳入板级拓扑，不再按待确认骨架处理。
- DDR 相关电源 `+1V2_DDR / +0V9_DDR` 已写入模型和测试。
- 参考设计采集顺序已经固定，避免误把板级拓扑再拆散。

### 高速与外设

- `RGMII / USB Hub / HDMI / USB-C` 已进入板级边界收口。
- `J6 / J7 / J8 / J9` 的器件备注已体现当前边界。
- 高速接口现在按证据优先和板级约束推进，不再停留在待确认状态。

## 3. 关键网络清单

### 关键电源

- `+5V_IN`
- `+5V_SYS`
- `+3V3`
- `+1V8`
- `+1V1_CORE`
- `+1V2_DDR`
- `+0V9_DDR`

### 关键启动网络

- `H618_UART0_TX`
- `H618_UART0_RX`
- `H618_RESET_N`
- `H618_FEL_BOOT`
- `H618_SD_CMD`
- `H618_SD_D0`
- `H618_SD_D1`
- `H618_SD_D2`
- `H618_SD_D3`
- `H618_SPI0_CS0`
- `H618_SPI0_MISO`
- `H618_SPI0_MOSI`
- `H618_SPI0_CLK`
- `H618_SPI0_WP_N`
- `H618_SPI0_HOLD_N`

### 高速 / 外设网络

- `H618_RGMII_*`
- `H618_USB0_*`
- `USB_HUB_PORT1_*`
- `USB_HUB_PORT2_*`
- `H618_HDMI`

## 4. Bring-up 顺序

1. 先检查 `+5V_IN` 到 `+5V_SYS` 的输入路径。
2. 再验证 `+3V3 / +1V8 / +1V1_CORE / +1V2_DDR / +0V9_DDR`。
3. 再看 `RESET_N / FEL_BOOT / UART0`。
4. 再验证 `MicroSD / SPI NOR`。
5. 再看 `RGMII / USB Hub / HDMI / USB-C`。

## 5. 测量点建议

- `TP1`：`+5V_IN`
- `TP2`：`+3V3`
- `TP3`：`+1V8`
- `TP4`：`+1V1_CORE`
- `TP5`：`UART0_TX`
- `TP6`：`UART0_RX`
- `TP7`：`RESET_N`
- `TP8`：`FEL_BOOT`
- `TP9`：`+1V2_DDR`
- `TP10`：`+0V9_DDR`

## 6. BOM 风险提示

- `U3 LPDDR4` 仍是最高敏感器件域，后续打样前要继续核对参考设计一致性。
- `U1 PMIC` 的输出顺序和负载归属仍需最终复核。
- `U5 RGMII`、`U6 USB Hub`、`J9 HDMI` 的器件级细节仍要继续对照参考资料。
- `J1 USB-C` 仍需要在最终打样前确认 ESD、浪涌、壳地策略。

## 7. 最后复核项

- `U2 H618` 最终器件级 pinmap。
- `U3 LPDDR4` 完整参考拓扑。
- `U1 PMIC` 最终电源树和时序。
- `RGMII / USB Hub / HDMI / USB-C` 的器件级细节。

## 8. 评审结论

- 现在已经可以做硬件评审。
- 现在不应宣称量产定版。
- 下一步应把这份审查包作为统一讨论的基底，逐项确认最后复核项。

## 9. 关联文件

- [source/circuit-model.source.json](../source/circuit-model.source.json)
- [25_procurement_ready.md](25_procurement_ready.md)
- [26_core_block_resolved.md](26_core_block_resolved.md)
