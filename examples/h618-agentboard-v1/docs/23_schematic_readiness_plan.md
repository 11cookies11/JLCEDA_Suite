# H618 AgentBoard V1 原理图可用化计划

本文件把当前 H618 AgentBoard V1 从“KiCad 可生成、ERC 归零”推进到“可评审、可打样前检查”的工作拆成清晰阶段。

## 当前状态

- 当前工程可以通过 pipeline 干净生成。
- KiCad ERC 当前为 `0` findings。
- USB-C 5V 输入、CC 下拉、TVS、保险丝到 `+5V_SYS` 的基础路径已修正。
- SPI NOR、MicroSD、UART0、RESET、FEL 等 bring-up 入口已有基础拓扑。
- 主要差距不在生成链路，而在 H618 真实参考设计对齐、PMIC 时序、DDR、外设细节和去耦完整性。

## 阶段 1：电源与复位闭环

目标：先让板子的上电、复位和基础供电关系可信。

当前进展：

- 已补 `H618_RESET_N` 默认上拉 `R7`。
- 已补 `H618_FEL_BOOT` 默认上拉 `R8`。
- 已补 DDR rail 测试点 `TP9 / TP10`。
- 已把 H618 代表性电源域挂入 `+3V3`、`+1V1_CORE`、`+1V2_DDR`。
- 已将 UART0 作为第一条软件可见日志路径固定在模型和计划里。

任务：

- 梳理 AXP313A 到 H618、LPDDR4、PHY、USB Hub 的 rail 归属。
- 明确 `+5V_IN`、`+5V_SYS`、`+3V3`、`+1V8`、`+1V1_CORE`、`+1V2_DDR`、`+0V9_DDR` 的输入输出关系。
- 补齐 PMIC EN、PWRON、INT、I2C、RESET 相关默认状态。
- 把 H618 RESET/FEL 与 PMIC reset release 的关系写入 `source/circuit-model.source.json`。
- 为关键 rail 增加测试点和最小 bulk / decoupling 规则。

完成标准：

- 电源树在模型中没有方向性硬伤。
- pipeline 后 ERC 仍为 `0`。
- 文档能解释每条主电源 rail 的来源和用途。

## 阶段 2：H618 最小启动闭环

目标：把“能点亮和能救砖”的最小系统从骨架变成可审查拓扑。

任务：

- 对齐 H618 最小启动 pinmap：`UART0`、`RESET`、`FEL/BOOT`、`SPI0`、`SDIO`、`24MHz`、`32kHz`。
- 补齐 SPI NOR 和 MicroSD 的上拉、串阻、检测脚和默认状态。
- 把 PMIC 的 `PWRON`、`INT` 和 reset release 逻辑一起纳入启动闭环。
- 说明 UART0 调试口、电源、地和测试点在 bring-up 阶段如何直接使用。
- 将启动路径风险写入 docs 和 `risks`。

完成标准：

- MicroSD、SPI NOR、UART0、RESET、FEL 都有明确网络和默认状态。
- PMIC 状态线和上电释放逻辑已经写入模型约束。
- 不再依赖聚合网表达启动关键路径。

## 阶段 3：LPDDR4 参考设计对齐

目标：把当前 DDR 骨架推进到真实可评审的 DDR 拓扑。

任务：

- 按成熟 H618/H616 参考设计补齐 DDR pinmap。
- 拆分 DQ、DQS、DM、CA、CK、CS、CKE、ODT、RESET 等 DDR 网络。
- 补齐 DDR 电源 rail 和去耦分组。
- 标注 DDR placement / routing constraint domain。
- 明确当前是否继续使用 U3 这个 EasyEDA/JLC 器件，还是切换到更可验证的替代料。
- 先按 [DDR 参考设计采集清单](14_ddr_reference_capture_checklist.md) 收集资料，再扩展模型。

当前原则：

- 当前模型只保留 5 条 LPDDR4 骨架网和电源域，不能把它误当成完整 DDR 拓扑。
- 采集顺序按“器件与封装 -> pinmap -> 电源/去耦 -> 版图约束”推进。

完成标准：

- DDR 不再只是骨架网。
- DDR 网络可以进入独立评审。
- 在参考设计确认前，不承诺 PCB 可布线。

## 阶段 4：高速与外设接口闭环

目标：让外设从“有连接”推进到“接近真实板卡设计”。

任务：

- RGMII：补 PHY strap、时钟 / 晶振、复位、电源去耦、MDIO / MDC 上拉和 RJ45 磁性器件侧网络。
- USB Hub：补 hub reset、配置脚、下游端口供电 / 限流 / ESD。
- HDMI：补 DDC、HPD、5V、ESD、差分对拆分和连接器真实脚位。
- USB-C：继续补 ESD、输入浪涌、VBUS 保护和机械壳地策略。
- 先按 [高速接口参考设计采集清单](15_high_speed_reference_capture_checklist.md) 收集资料，再扩展模型。

完成标准：

- 各接口不再只靠聚合网或最小连接表达。
- 每个接口都有后续 PCB 约束依据。

## 阶段 5：可打样前审查包

目标：生成一套可以交给硬件评审的资料包。

任务：

- 生成干净 KiCad 工程并同步 example。
- 输出 ERC 报告、BOM 风险清单、关键网络清单。
- 更新 bring-up plan：上电顺序、测量点、预期电压、故障分支。
- 更新风险清单，把未确认项明确标为 `blocked` 或 `need-verify`。
- 汇总成 [可打样前审查包](24_final_review_package.md)。

完成标准：

- KiCad 工程可直接打开，ERC 为 `0`。
- 关键电源和启动链路有测量点。
- 未确认事项被显式记录，不伪装成已完成。
- 阶段 5 资料已能作为统一讨论底稿使用。

## 推荐推进顺序

1. 电源与复位闭环。
2. H618 最小启动闭环。
3. LPDDR4 参考设计对齐。
4. 高速与外设接口闭环。
5. 可打样前审查包。
