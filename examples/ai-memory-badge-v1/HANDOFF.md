# AI Memory Badge v1 — 项目交接文档

## 项目概述

**产品**：AI 拾音器胸牌（Badge），基于 ESP32-S3-WROOM-1 模组。
**版本**：Rev A 工程样机。
**状态**：电路设计完成，原理图 + PCB 可用，待投板验证。

## 硬件架构

```
USB-C(5V) → BQ24074 充电路径管理 → VSYS → AP2112K LDO → SYS_3V3
                                          ↓ BAT_P ← JST PH 2P 电池座

SYS_3V3 ─→ ESP32-S3-WROOM-1
         ├→ U9 TPS22918 → MIC_3V3（静音开关可切断）
         ├→ U10 TPS22918 → SD_3V3（MCU 可控）
         ├→ J6.7 直连 EPD 供电（Rev A 暂不独立控制）
         └→ I2C/VBAT_SENSE/按键/LED/马达

I2S MEMS 麦克风 ×2 → GPIO12-14（共享 I2S 总线）
microSD SPI → GPIO7-11（独立 SPI）
E-Paper SPI → GPIO33-38（独立 SPI + DC/RST/BUSY/PWR_EN）
NFC ST25DV → I2C (GPIO5 SCL, GPIO21 SDA) + GPIO41 GPO
```

## BOM 统计

| 类型 | 数量 | 备注 |
|------|------|------|
| 电阻 | 25 | 全 0603 |
| 电容 | 14 | 全 0603（100nF/1uF/10uF） |
| IC | 7 | MCU + 充电 + LDO + 2×负载开关 + NFC + ESD |
| 连接器 | 5 | USB-C + 电池 + microSD + EPD-FPC + NFC 天线焊盘 |
| 开关 | 5 | Reset(内)/Boot(内)/Mark(用户)/Mute(滑动)/Rec(滑动) |
| 二极管/LED | 3 | 绿LED + 红LED + 肖特基续流 |
| 麦克风/马达 | 3 | 2×I2S MEMS + 振动马达 |
| MOS | 1 | AO3400A NMOS 马达驱动 |
| **合计** | **63** | |

## 文件结构

```
examples/ai-memory-badge-v1/
├── source/circuit-model.source.json   ← DSL 电路模型（唯一编辑入口）
├── build/circuit-model.resolved.json  ← 自动解析补充（勿手动编辑）
├── build/circuit-sanity.json          ← 电路门禁检测报告
├── libraries/
│   ├── symbols/JLC-MCP.kicad_sym      ← 49 个符号（全 JLC 下载 + 2 个手写）
│   ├── footprints/JLC-MCP.pretty/     ← 36 个封装
│   └── 3dmodels/                      ← 64 个 3D 模型（step+wrl）
├── output/ai_memory_badge_v1/         ← 生成的 KiCad 工程
│   ├── ai_memory_badge_v1.kicad_pro
│   ├── ai_memory_badge_v1.kicad_sch
│   ├── ai_memory_badge_v1.kicad_pcb
│   └── libraries/                     ← 输出时自动同步的库
├── docs/                              ← 设计文档（15 篇）
└── HANDOFF.md                         ← 本文件
```

## 流水线操作

```bash
cd <repo_root>
PYTHONPATH="src" python -m kicad_suite agent <command> --project examples/ai-memory-badge-v1

# 常用命令
circuit-sanity     # 电路门禁检查（每次改 DSL 后必跑）
build-ir           # 编译 DSL → Hardware IR
validate-ir        # 校验 IR 结构
export-kicad       # 完整导出 KiCad 工程（原理图+PCB+ERC+报告）
build-kicad        # 同 export-kicad
jlc download       # 下载单个 LCSC 元件到本地库
jlc search <query> # 搜索 LCSC
pins free          # 查看 ESP32 空闲 GPIO
workflow run       # 运行编排工作流
doctor             # 环境检查
report             # 生成项目报告
```

## 关键修复记录（本轮会话）

### 电路拓扑修复
1. **LED 驱动修复**：D1/D2 从 VCC-GND 直连改为 GPIO → R → LED → VCC
2. **静音开关重设计**：SPDT COM 直接控制 U9.ON，GPIO17 同网读取状态
3. **C20/C21 电源短路**：NFC 调谐电容从 SYS_3V3 移除
4. **R31/R32 信号短路**：按键上拉电阻从 GND 移除
5. **R11 麦克风供电链路悬空**：加入 SYS_3V3
6. **R27/R28 上下拉接错**：接入实际信号网
7. **J6.7 电源悬空**：重回 SYS_3V3（Rev A 直连）
8. **J7.2 天线短路**：从 GND 移除

### 设计优化
- D3: BAT54C 续流二极管跨接马达 M1
- C22: 100nF VBAT_SENSE ADC 滤波
- R24/R25/SW6/U7/C20/C21: 全删（不再需要）
- R16/R32: 删除（静音/模式按键重构后废弃）
- J4: 删除（UART DEBUG 不再需要）
- 全阻容统一 0603 封装
- SW4/SW5 统一为 SMD SPDT 滑动开关 (MST-12D18G4)

### 工具链加固
1. **封装裸名**：去掉 JLC-MCP: 前缀，3D 路径用 ${KIPRJMOD}
2. **PCB 生成器**：支持裸封装名回退搜索 JLC-MCP.pretty
3. **JLC 下载器**：自动标准化 3D 路径
4. **电路门禁模块**：`domain/core/validation/circuit_sanity.py`
   - 检测跨网短路、元件自环、可疑电源连接、上拉/下拉角色错误
   - 检测符号库括号平衡
5. **流水线日志**：3D 模型处理状态写入 event log

### 库文件修复
- JLC-MCP.kicad_sym 重写为 49 个独立验证的符号（消除所有括号错误）
- 手写符号 NFC_ANT_2P、BAT54C_FLYBACK
- 从旧 ZIP 恢复 EPD_SPI_CONN_10P（10 脚命名引脚，非 26 脚 FPC）

## 已知注意事项

1. **封装名纯裸名**：不包含库前缀。KiCad 通过 fp-lib-table 查找，EasyEDA 需附带 JLC-MCP.pretty 目录。
2. **EPD 连接器**：符号仅 10 脚，实际 FPC 24 脚。未使用引脚的状态需根据面板 datasheet 确认。
3. **VBAT_SENSE 分压器**：1M+330K，ADC 读数可能受噪声影响（已加 C22 滤波）。
4. **充电电流**：R3=2K → I_CHG≈500mA，需根据所选电池确认。
5. **AP2112K LDO 效率**：线性稳压，电池电压低于 3.5V 时可能压差不足。Rev B 考虑换 buck。
6. **马达无硬件刹车**：仅有续流二极管，制动靠机械摩擦。
7. **单页原理图模式**：所有符号嵌入在 .kicad_sch 中，文件较大但自包含。
8. **不要手动编辑** build/ 和 output/ 下的文件。一切从 circuit-model.source.json 通过流水线生成。

## 下一步建议

- [ ] 确认 EPD 面板型号并验证 FPC 引脚映射
- [ ] NFC 天线设计（PCB 线圈或外接）
- [ ] 电池选型并计算充电电流
- [ ] PCB 布局布线
- [ ] 外壳工业设计（声学通道 + NFC 天线窗 + LED 导光）
- [ ] 固件开发（I2S 录音 + microSD 写入 + EPD 驱动 + NFC 配置）
- [ ] Rev B: LDO → buck、加音频 codec、加电池电量计
