# 00 需求定义

项目：H618 AgentBoard V1

状态：

- V1 需求收口草案
- 仍有少量 `NEED_VERIFY` 项，但功能范围不再继续扩张

项目目标：

- 基于 Allwinner H618 的低成本 Linux 控制板
- 第一版优先保证可调试、可恢复、可量产验证
- 面向 AI Agent 的硬件控制、日志采集和外设扩展

V1 必做能力：

- `MicroSD` 启动
- `UART0` 调试串口
- `RESET / FEL`
- `SPI NOR` 启动或恢复存储
- `Ethernet`
- `USB Host`
- `GPIO` 扩展
- `I2C` 和 `SPI` 扩展

V1 预留但不强制完成：

- 协处理器接口，目标兼容 `RP2040` 或 `ESP32` 类器件
- `HDMI` 显示输出
- 更多高速外设扩展

关键约束：

- `DDR / LPDDR4` 必须参考成熟的 H618/H616 板子
- `PMIC / 电源树` 必须明确电压、负载、时序和测试点
- `Debug UART / FEL / RESET / MicroSD` 优先级最高
- `PCB` 以可调试、可返修为优先
- 所有未确认内容必须显式标记为 `TODO` 或 `NEED_VERIFY`

验收标准：

- 能稳定上电
- 能通过 `UART0` 看到启动日志
- 能从 `MicroSD` 启动 Linux
- 能通过串口或网络进入系统
- 能访问至少一组通用扩展接口

待确认项：

- 最终 PMIC 选型
- 最终 DDR 参考设计
- 最终连接器数量和机械边界
- 最终 pinmux 绑定
- 热设计和板框尺寸
