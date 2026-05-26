# 02 电源树

Status: In Progress

本文记录 H618 AgentBoard V1 当前原理图模型中的电源入口、PMIC 输出、测试点和复位相关约束。

## 电源入口

- `J1` 为 USB-C 5V 输入连接器。
- `R5` / `R6` 分别为 CC1 / CC2 的 5.1k Sink Rd 下拉。
- `D1` TVS 接在原始 VBUS 与 GND 之间。
- `F1` 位于 `+5V_IN` 和 `+5V_SYS` 之间，作为输入保护后的系统 5V 路径。

当前路径：

```text
5V USB-C VBUS -> +5V_IN -> F1 -> +5V_SYS -> U1 PMIC / board auxiliary loads
```

## 电源 rail

- `+5V_IN`：USB-C 原始输入，包含 J1 VBUS、D1 TVS、F1 输入端和 TP1。
- `+5V_SYS`：经过 F1 后的系统 5V，供给 PMIC 输入和板级辅助负载。
- `+3V3`：主逻辑电源，供连接器、上拉、SPI NOR、MicroSD、PHY、USB Hub 和调试接口等。
- `+1V8`：I/O 与外设偏置电源。
- `+1V1_CORE`：H618 核心电源域，当前通过 `U2.VDD1` 建立代表性连接。
- `+1V2_DDR`：DDR I/O 相关电源域，当前连接 `U3.VDDQ`、`U2.VDDQ` 和 TP9。
- `+0V9_DDR`：DDR 低压/参考相关电源域，当前连接 U1 输出和 TP10。

## PMIC 相关信号

- `H618_PMIC_I2C_SCL`：U1 到 U2 的 PMIC 控制总线时钟，R1 上拉到 `+3V3`。
- `H618_PMIC_I2C_SDA`：U1 到 U2 的 PMIC 控制总线数据，R2 上拉到 `+3V3`。
- `H618_PMIC_INT`：PMIC 中断/状态线，用于向 SoC 报告电源事件。
- `H618_PMIC_PWRON`：PMIC PWRON 默认上拉路径，R3 上拉到 `+3V3`。

## 复位与启动默认状态

- `H618_RESET_N`：U2 RESET_N、SW1、TP7 和 R7 组成；R7 提供默认上拉，SW1 可手动拉低复位。
- `H618_FEL_BOOT`：U2 BOOT0、SW2、TP8 和 R8 组成；R8 提供默认上拉，SW2 可手动拉低进入恢复模式。
- 复位释放时序仍需按最终 PMIC 参考设计确认。
- FEL/BOOT 默认状态仍需和最终 H618 启动 strap 定义核对。

## 测试点

- `TP1`：`+5V_IN`
- `TP2`：`+3V3`
- `TP3`：`+1V8`
- `TP4`：`+1V1_CORE`
- `TP9`：`+1V2_DDR`
- `TP10`：`+0V9_DDR`
- `TP5`：`H618_UART0_TX`
- `TP6`：`H618_UART0_RX`
- `TP7`：`H618_RESET_N`
- `TP8`：`H618_FEL_BOOT`

## 当前已收口

- USB-C 输入路径不再把保险丝输出端误接到 GND。
- CC1/CC2 已有独立 5.1k Sink Rd。
- RESET_N 和 FEL/BOOT 已有默认上拉和手动拉低路径。
- DDR 相关 rail 已补充 bring-up 测试点。
- PMIC INT 状态线已明确。
- H618 代表性电源域已挂入当前电源树，便于后续继续对齐真实 pinmap。

## 仍需确认

- AXP313A 每路输出和 H618/DDR 参考设计的最终 rail 归属。
- `U2.VDD1`、`U2.VDD2`、`U2.VDDQ` 的完整球位集合和真实电源域映射。
- PMIC reset release、PWRON 默认状态、INT 极性和上电时序。
- 每个 SoC、DDR、PHY、USB Hub 电源脚的去耦数量、位置和封装。
