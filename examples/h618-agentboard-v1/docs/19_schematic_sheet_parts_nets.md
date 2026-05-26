# 19 原理图分图元件与网络清单

Status: Draft

## 目的

把 [原理图模块输入](18_schematic_module_inputs.md) 再压缩成每个分图可直接照着捕获的元件清单和网络清单。

## 使用规则

- 每个分图先放元件，再连网络。
- 只写当前分图必须出现的器件和网络。
- 未冻结内容继续保留在收口文档里，不在这里发散。

## `sheet_01_power_entry_pmic`

### 元件清单

- `J1`
- `F1`
- `D1`
- `U1`
- `C5`
- `C6`
- `C7`
- `C8`
- `R1`
- `R2`
- `R3`
- `TP1`
- `TP2`
- `TP3`
- `TP4`

### 网络清单

- `+5V_IN`
- `+5V_SYS`
- `+3V3`
- `+1V8`
- `+1V1_CORE`
- `+1V2_DDR`
- `+0V9_DDR`
- `H618_PMIC_I2C_SCL`
- `H618_PMIC_I2C_SDA`
- `H618_PMIC_INT`
- `H618_PMIC_PWRON`

## `sheet_02_soc_boot_clock`

### 元件清单

- `U2`
- `Y1`
- `Y2`
- `C1`
- `C2`
- `C3`
- `C4`
- 与启动相关的小阻值电阻和上拉件

### 网络清单

- `H618_UART0_TX`
- `H618_UART0_RX`
- `H618_RESET_N`
- `H618_FEL_BOOT`
- `H618_24M_OSC`
- `H618_32K_OSC`

## `sheet_03_memory_ddr`

### 元件清单

- `U3`
- DDR 相关去耦电容
- DDR 相关参考和终端器件

### 网络清单

- `+1V2_DDR`
- `+0V9_DDR`
- `H618_LPDDR4`

## `sheet_04_boot_storage`

### 元件清单

- `J2`
- `U4`

### 网络清单

- `H618_SDIO`
- `H618_SPI_NOR`
- `H618_FEL_BOOT`
- `H618_RESET_N`

## `sheet_05_debug_and_control`

### 元件清单

- `J3`
- `SW1`
- `SW2`
- `TP5`
- `TP6`
- `TP7`
- `TP8`

### 网络清单

- `H618_UART0_TX`
- `H618_UART0_RX`
- `H618_RESET_N`
- `H618_FEL_BOOT`

## `sheet_06_network`

### 元件清单

- `U5`
- `J6`

### 网络清单

- `H618_RGMII`
- `H618_RGMII_MDC_MDIO`
- `H618_RGMII_RESET`
- `H618_RGMII_MDC`
- `H618_RGMII_MDIO`

## `sheet_07_usb`

### 元件清单

- `U6`
- `J7`
- `J8`

### 网络清单

- `H618_USB0`
- `USB_HUB_RESET`
- `USB_HUB_PORT1`
- `USB_HUB_PORT2`
- `+5V_SYS`
- `+3V3`

## `sheet_08_display`

### 元件清单

- `J9`

### 网络清单

- `H618_HDMI`
- `+3V3`

## `sheet_09_expansion`

### 元件清单

- `J4`
- `J5`

### 网络清单

- `H618_26PIN_3V3`
- `H618_26PIN_5V`
- `H618_26PIN_PH5_TWI3_SDA_SPI1_CS0`
- `H618_26PIN_PH4_TWI3_SCK_SPDIF_OUT`
- `H618_26PIN_PC9`
- `H618_26PIN_UART5_TX_PH2`
- `H618_26PIN_UART5_RX_PH3`
- `H618_26PIN_SDC2_CMD_PC6`
- `H618_26PIN_PC11`
- `H618_26PIN_SDC2_CLK_PC5`
- `H618_26PIN_PC8`
- `H618_26PIN_PC15`
- `H618_26PIN_PC14`
- `H618_26PIN_UART2_RTS_TWI4_SDA_PH7`
- `H618_26PIN_UART2_CTS_PH8`
- `H618_26PIN_PC7`
- `H618_26PIN_UART2_RX_TWI4_SCK_PH6`
- `H618_26PIN_SPI1_CS0_PH9`
- `H618_26PIN_PC10`
- `H618_COPRO_UART`
- `H618_COPRO_HEADER`

## `sheet_10_testpoints_led`

### 元件清单

- `LED1`
- `R4`
- `TP1`
- `TP2`
- `TP3`
- `TP4`

### 网络清单

- `+5V_IN`
- `+3V3`
- `+1V8`
- `+1V1_CORE`
- `H618_UART0_TX`
- `H618_UART0_RX`
- `H618_RESET_N`
- `H618_FEL_BOOT`

## 额外说明

- `sheet_00_top` 不单独列器件清单，保留全局说明即可。
- 如果某个器件最终不属于某个分图，应回到 [原理图模块输入](18_schematic_module_inputs.md) 调整职责边界。
- 如果某个网络名还不稳定，应先回收口文档，不要先在这里发明新名字。
