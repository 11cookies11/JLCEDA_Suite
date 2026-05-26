# 05 原理图模块

Status: Draft

目标：

- 把当前虚拟电路拆成可维护的原理图分图
- 每个模块只负责一类功能，避免主图过度拥挤
- 让后续 ERC、布线和 bring-up 更容易定位问题

建议分图：

1. `sheet_00_top` 总图
- 只保留项目入口、全局网络和跨模块连接
- 展示系统级电源、启动、调试和外设分区

2. `sheet_01_power_entry_pmic` 电源入口与 PMIC
- `J1`、`F1`、`D1`、`U1`
- 负责 `+5V_IN` 到各电源域的转换和时序控制

3. `sheet_02_soc_boot_clock` SoC、启动与时钟
- `U2`、`Y1`、`Y2`、`C1`、`C2`、`C3`、`C4`
- 负责 H618 主控、晶振、复位和启动相关信号

4. `sheet_03_memory_ddr` DDR 存储
- `U3`
- 负责 LPDDR4 及其相关电源、去耦和布线约束

5. `sheet_04_boot_storage` 启动存储
- `J2`、`U4`
- 负责 `MicroSD` 主启动和 `SPI NOR` 备用 / 恢复启动

6. `sheet_05_debug_and_control` 调试与控制
- `J3`、`SW1`、`SW2`、`TP5`、`TP6`、`TP7`、`TP8`
- 负责串口日志、复位和 `FEL / BOOT`

7. `sheet_06_network` 网络接口
- `U5`、`J6`
- 负责 RGMII、MDIO/MDC、PHY 复位和千兆网口

8. `sheet_07_usb` USB 子系统
- `U6`、`J7`、`J8`
- 负责 H618 到 USB Hub，再到双 USB Host 口的分发

9. `sheet_08_display` 显示输出
- `J9`
- 负责 HDMI 输出

10. `sheet_09_expansion` 扩展口与预留口
- `J4`、`J5`
- 负责 26Pin 扩展口和协处理器预留口

11. `sheet_10_testpoints_led` 测试点与指示灯
- `TP1`、`TP2`、`TP3`、`TP4`、`LED1`、`R4`
- 负责供电指示与关键电源测试

拆分原则：

- 电源和启动优先独立成图
- DDR 单独成图，避免和通用外设混在一起
- 调试口必须在总图中容易找到
- 外设模块尽量按接口类型分开
- 每个分图都要保留清晰的输入和输出网名

模块间关系：

- 电源模块给所有其他模块供电
- 启动存储和 DDR 共同决定最小可启动系统
- 调试模块应不依赖复杂外设即可工作
- 外设模块不得反过来影响启动链

实现建议：

- 先从 `sheet_01`、`sheet_02`、`sheet_03`、`sheet_04` 开始
- 再补 `sheet_05` 到 `sheet_10`
- 任何模块拆分都要保持当前 `circuit-model.json` 的网名可追溯

待确认项：

- 是否把 `sheet_10` 和 `sheet_05` 中的测试点合并
- `J6 / J7 / J8 / J9` 的机械布局是否会反过来影响分图顺序
- 是否需要给 `U2` 再拆一个单独的 `pinmux` 说明页
