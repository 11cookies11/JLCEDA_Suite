# 04 引脚复用

Status: Draft

目标：

- 先把第一版需要暴露的接口固定下来
- 把调试口、扩展口、启动敏感脚和外设脚分开管理
- 所有未最终确认的映射都保留 `NEED_VERIFY`

调试串口：

- `J3.1` = `GND`
- `J3.2` = `H618_UART0_TX`，对应 `U2.PH0`
- `J3.3` = `H618_UART0_RX`，对应 `U2.PH1`
- `J3.4` = `+3V3`

26Pin 扩展口草案：

- `J4.1` = `+3V3`
- `J4.2` = `+5V_SYS`
- `J4.3` = `H618_26PIN_PH5_TWI3_SDA_SPI1_CS0`，对应 `U2.PH5`
- `J4.4` = `+5V_SYS`
- `J4.5` = `H618_26PIN_PH4_TWI3_SCK_SPDIF_OUT`，对应 `U2.PH4`
- `J4.6` = `GND`
- `J4.7` = `H618_26PIN_PC9`，对应 `U2.PC9`
- `J4.8` = `H618_26PIN_UART5_TX_PH2`，对应 `U2.PH2`
- `J4.9` = `GND`
- `J4.10` = `H618_26PIN_UART5_RX_PH3`，对应 `U2.PH3`
- `J4.11` = `H618_26PIN_SDC2_CMD_PC6`，对应 `U2.PC6`
- `J4.12` = `H618_26PIN_PC11`，对应 `U2.PC11`
- `J4.13` = `H618_26PIN_SDC2_CLK_PC5`，对应 `U2.PC5`
- `J4.14` = `GND`
- `J4.15` = `H618_26PIN_PC8`，对应 `U2.PC8`
- `J4.16` = `H618_26PIN_PC15`，对应 `U2.PC15`
- `J4.17` = `+3V3`
- `J4.18` = `H618_26PIN_PC14`，对应 `U2.PC14`
- `J4.19` = `H618_26PIN_UART2_RTS_TWI4_SDA_PH7`，对应 `U2.PH7`
- `J4.20` = `GND`
- `J4.21` = `H618_26PIN_UART2_CTS_PH8`，对应 `U2.PH8`
- `J4.22` = `H618_26PIN_PC7`，对应 `U2.PC7`
- `J4.23` = `H618_26PIN_UART2_RX_TWI4_SCK_PH6`，对应 `U2.PH6`
- `J4.24` = `H618_26PIN_SPI1_CS0_PH9`，对应 `U2.PH9`
- `J4.25` = `GND`
- `J4.26` = `H618_26PIN_PC10`，对应 `U2.PC10`

启动敏感脚：

- `RESET_N` 必须可手动复位
- `FEL / BOOT` 必须可手动进入恢复模式
- `MicroSD` 必须作为首选启动路径之一
- `SPI NOR` 必须保留恢复或量产引导用途

接口设计原则：

- 调试口优先于扩展口
- 供电脚和地脚必须分布均衡
- 协处理器接口先预留，不在 V1 强行固定最终功能
- 所有复用信号要能回溯到原理图和软件 pinctrl 配置

待确认项：

- 26Pin 口的最终参考板来源
- `PC5 / PC6 / PC7 / PC8 / PC9 / PC10 / PC11 / PC14 / PC15` 的最终软件复用
- `PH4 / PH5 / PH6 / PH7 / PH8 / PH9` 的最终外设分配
- 是否需要补充专用 I2C 总线和独立 SPI 总线
