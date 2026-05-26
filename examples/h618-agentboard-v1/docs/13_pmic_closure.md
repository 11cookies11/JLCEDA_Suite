# 13 PMIC 收口方案

Status: In Progress

## 目标

把 H618 AgentBoard V1 的电源树从“可生成骨架”推进到“可评审原理图输入”。

## 当前策略

- 继续以 `AXP313A` 作为 V1 的 PMIC 参考器件。
- 不在当前阶段引入复杂多 PMIC 方案。
- 先保证 5V 输入、主 rail、复位、FEL、UART0 和测试点形成可 bring-up 的闭环。
- DDR、H618 全量电源球位和 PMIC 时序仍必须跟随成熟参考设计确认。

## 当前模型中的 PMIC 输出

1. `+5V_IN`
- 来自 USB-C VBUS。
- TVS 和测试点位于保险丝前。

2. `+5V_SYS`
- 经过 F1 后的系统 5V。
- 供给 PMIC 输入和板级辅助 5V 负载。

3. `+3V3`
- 主逻辑电源。
- 供上拉、SPI NOR、MicroSD、PHY、USB Hub、调试口、扩展口和 SoC 代表性 I/O 电源域。

4. `+1V8`
- I/O 与外设偏置电源。
- 当前仍需要按参考设计继续确认负载归属。

5. `+1V1_CORE`
- H618 核心电源域。
- 当前通过 `U2.VDD1` 建立代表性连接。

6. `+1V2_DDR`
- DDR I/O 相关电源域。
- 当前连接 `U3.VDDQ`、`U2.VDDQ` 和 TP9。

7. `+0V9_DDR`
- DDR 低压/参考相关电源域。
- 当前连接 U1 输出和 TP10。

## 复位与默认状态

- `H618_RESET_N` 已补 R7 默认上拉，并保留 SW1 手动拉低复位。
- `H618_FEL_BOOT` 已补 R8 默认上拉，并保留 SW2 手动拉低进入恢复。
- `H618_PMIC_PWRON` 已通过 R3 上拉到 `+3V3`。
- `H618_PMIC_I2C_SCL/SDA` 已通过 R1/R2 上拉到 `+3V3`。

## 完成标准

- 每条主电源 rail 都有明确来源、负载和测试点。
- RESET/FEL 默认状态明确，且可手动介入。
- PMIC 控制总线和 PWRON 默认状态明确。
- pipeline 生成后 ERC 保持 0。

## 后续待办

- 按 H618/AXP313A 参考设计核对每路 rail 的真实电压、电流和时序。
- 补齐 PMIC 输出电感、反馈、补偿、去耦和布局约束。
- 将 H618 全量电源球位从代表性 pinmap 扩展为真实 pinmap。
- 将 DDR 供电和去耦推入 DDR 专项闭环。
