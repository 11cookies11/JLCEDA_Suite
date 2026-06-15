# 04 Component Selection

Status: Draft

## Selection Strategy

Rev A 先追求可买、可焊、可调试、资料充分，不追求极限小型化。器件选择分为三层：

- Default：建议 Rev A 默认采用。
- Alternate：默认器件缺货、面积不合适或性能不足时替换。
- Reserve：先预留封装或接口，后续版本再决定是否贴装。

下单前必须重新确认：

- LCSC/JLCPCB 是否可采购、可贴装。
- 器件生命周期是否稳定。
- KiCad 符号和封装是否可用。
- 是否有替代料可以兼容原理图和 PCB。

## Rev A Default BOM Direction

| Block | Default Choice | Alternate | Notes |
| --- | --- | --- | --- |
| Main controller | ESP32-S3 bare SoC | ESP32-S3-WROOM/MINI module fallback | 裸芯片更接近产品化，模组仅作为降风险备选 |
| Program memory | external SPI flash, 8-16 MB | larger flash / octal flash if needed | 裸芯片必须外接启动 Flash |
| PSRAM | external PSRAM, 8 MB class preferred | no PSRAM for minimal firmware | 音频缓冲、VAD 和后续本地算法更从容 |
| RF | PCB antenna or antenna connector with matching network | certified module fallback | Rev A 必须预留 RF 调试和匹配位置 |
| Clock | 40 MHz crystal circuit | approved reference crystal | 按 Espressif 推荐负载电容和布局 |
| Microphones | 2x digital I2S MEMS mic, ICS-43434 class | INMP441 / SPH0645 class digital mic | 先锁 I2S 数字麦克风接口，不锁单一料号 |
| Storage | push-push or push-pull microSD socket | onboard SPI NAND / eMMC later | Rev A 用 microSD 降低容量和调试风险 |
| USB-C | USB-C 16-pin USB2.0 receptacle | 6-pin power-only plus debug header | V1 需要 USB 数据，建议保留 D+/D- |
| Charger | MCP73831 class single-cell LiPo charger | power-path charger such as BQ2407x class | Rev A 简单充电可用，量产考虑 power-path |
| Battery protection | protected LiPo cell or protection IC | charger/protection combo | 原型优先使用带保护电池 |
| 3.3 V regulator | AP2112K-3.3 class 600 mA LDO | high-efficiency buck or buck-boost | LDO 简单，续航版建议换高效率电源 |
| Status LED | discrete red/green or RGB LED | addressable RGB LED | 隐私录音指示建议用独立红色 LED |
| Buttons | low-profile tactile switch | side push switch | mark、boot、reset 至少三个按键位 |
| Mute control | slide switch | latching pushbutton plus firmware state | 隐私控制优先物理滑动开关 |
| Vibration | coin vibration motor + NMOS | haptic driver later | Rev A 用低边 MOS 驱动即可 |
| Secure element | I2C secure element footprint, DNP | ATECC608 class | Rev A 预留，默认不贴 |
| Battery connector | JST-style 2-pin LiPo connector | solder pads for pouch cell | 原型优先可插拔 |
| Test points | 1.27/2.54 mm pads | Tag-Connect footprint | 必须覆盖电源、USB、I2S、SPI、关键 GPIO |

## Main Controller

### Default

ESP32-S3 bare SoC with external flash and preferably external PSRAM.

Why:

- Wi-Fi + BLE 一体，满足同步和配网。
- 原生 USB 可用于调试和导出。
- I2S、SPI、I2C、ADC、GPIO 资源足够。
- 裸芯片更适合胸牌/夹子形态的小型化布局。
- 可自行决定 Flash/PSRAM 容量、天线位置和电源布局。
- 外部 PSRAM 有利于音频缓冲、VAD 和后续唤醒词实验。

### Design Notes

- 必须严格参考 Espressif ESP32-S3 硬件设计指南。
- 40 MHz 晶振要靠近芯片，走线短且避开噪声。
- RF 匹配网络要靠近芯片 RF 引脚并预留调试空间。
- 天线区域必须严格保留 keep-out。
- Flash/PSRAM 要靠近 ESP32-S3，必要时在 SPI 线上预留 0R 串联电阻。
- 所有电源脚就近去耦，不能把去耦电容放远。
- USB D+/D- 走线短而成对。
- Boot、EN/Reset 必须外露，避免原型调试困难。
- 尽量避免把关键功能压到启动绑定位上。

### Bare-Chip Bring-Up Risks

- RF 性能需要 PCB、天线和匹配共同调试。
- Flash/PSRAM 启动失败会直接阻塞固件 bring-up。
- 晶振不起振会导致整机无法启动。
- 去耦和电源完整性问题会在 Wi-Fi 发射时暴露。
- 若项目进度优先于小型化，应保留 ESP32-S3 模组 fallback 原理图分支。

## Audio Front End

### Default

Two bottom-port or top-port digital I2S MEMS microphones.

Electrical interface:

- 3.3 V or 1.8-3.3 V compatible supply.
- I2S BCLK shared.
- I2S LRCLK/WS shared.
- I2S DATA shared if left/right channel select is supported.
- L/R select pins固定成左右声道。

### Selection Criteria

- I2S digital output.
- 低功耗模式可用。
- 频响覆盖人声。
- SNR 适合近场语音。
- 封装和声孔方向适合胸牌外壳。
- 供应状态稳定。

### Mechanical Notes

- 声孔必须面向外侧。
- 声孔周围需要无遮挡区域。
- 麦克风下方或上方不能被胶、外壳筋位、夹子结构挡住。
- 左右麦克风尽量拉开距离，用来测试环境噪声和简单空间信息。

## Storage

### Default

microSD over SPI.

Why:

- 方便拿卡分析音频。
- 容量远超 Rev A 需求。
- 对音频分段、文件系统、同步策略都友好。

### Design Notes

- 优先选带 card-detect 的卡座。
- 卡座外露时加 ESD 保护。
- SPI 线加适当串联阻尼位，实际值可 DNP/0R 起步。
- 固件需要处理拔卡、满卡、写失败。

## Power System

### Rev A Simple Power Tree

```text
USB-C 5 V
  |
  +--> MCP73831-class LiPo charger --> protected LiPo
                                      |
                                      +--> 3.3 V LDO --> system 3V3
```

### Why This Is Acceptable For Rev A

- 电路简单，容易 bring-up。
- 资料和参考设计多。
- 成本低，封装好处理。
- 能先验证录音、同步和佩戴体验。

### Known Limitation

LDO 会把电池电压和 3.3 V 之间的压差变成热和损耗。Wi-Fi 高峰电流时效率不理想，低电压段也会更早掉出稳定区。

### Rev B Power Upgrade Candidate

```text
LiPo --> high-efficiency buck/buck-boost --> system 3V3
USB-C --> charger with power-path --> battery + system
```

Rev B 如果续航测试不够，应优先升级：

- power-path charger
- buck/buck-boost regulator
- load switch for microphone/storage domains

## Privacy And UI Components

### Recording Indicator

Use a dedicated red LED or red channel that firmware cannot confuse with decorative status.

Policy:

- active recording must be visible
- muted state must be visible
- LED duty cycle can be low, but state meaning must remain clear

### Mute Switch

Use a physical slide switch.

Recommended wiring:

- one GPIO with pull-up/down
- firmware samples it on boot and wake
- optional routing to microphone power-enable or load switch in later version

For Rev A, GPIO mute is acceptable if validation confirms muted mode never writes audio.

### Vibration Motor

Use a coin motor driven by low-side NMOS.

Signals:

- GPIO -> gate resistor -> NMOS gate
- motor across battery or 3.3 V depending selected motor
- flyback or transient suppression if required by motor type

Use vibration for mark confirmation and muted entry, not continuous status.

## Security Reserve

### Default

Reserve an I2C secure element footprint as DNP.

Candidate class:

- ATECC608-style secure element

Signals:

- I2C SDA/SCL
- 3.3 V
- GND
- optional wake/interrupt if selected device needs it

Purpose:

- device identity
- storage encryption key protection
- pairing/authentication experiments

## Prototype Debug Features

Mandatory:

- Boot button
- Reset button
- USB serial path
- battery current measurement option
- 3.3 V current measurement option
- test pads for I2S and SPI
- exposed GND pads for oscilloscope probing

Nice to have:

- Tag-Connect footprint
- UART header
- charger status LEDs or test pads
- solder jumpers for LED/motor/mic power isolation

## Preliminary Power Budget

These are planning targets, not guaranteed values.

| Mode | Target Behavior | Design Concern |
| --- | --- | --- |
| Deep standby | lowest practical current | regulator Iq, pull-ups, LEDs, card leakage |
| Listening | mic + MCU low-power audio loop | VAD strategy dominates |
| Recording | mic + CPU + microSD writes | storage bursts and buffering |
| Syncing | Wi-Fi + microSD reads | current peaks and thermal |
| Charging | USB powered | charger heat and user handling |

Battery capacity target for Rev A:

- 500 mAh minimum for desk tests.
- 800-1000 mAh preferred for all-day carry experiments.

## Decisions To Lock Before Schematic

- ESP32-S3 bare chip exact variant.
- Flash and PSRAM exact part and bus mode.
- Crystal part, load capacitance and layout constraints.
- RF path: PCB antenna, chip antenna, or antenna connector.
- RF matching network footprint.
- I2S microphone exact package and sound port direction.
- microSD socket footprint.
- USB-C connector footprint.
- charger package and charge current.
- whether Rev A uses LDO only or already includes a switcher footprint.
- whether secure element is DNP reserve or populated.
- LED scheme: discrete privacy LED plus status LED, or RGB LED.

## Procurement Notes

Before converting to `source/circuit-model.source.json`, run part searches for:

```powershell
hwtool agent jlc search "ESP32-S3 chip" -n 10
hwtool agent jlc search "SPI flash 16MB" -n 10
hwtool agent jlc search "PSRAM ESP32-S3" -n 10
hwtool agent jlc search "40MHz crystal ESP32" -n 10
hwtool agent jlc search "I2S MEMS microphone" -n 10
hwtool agent jlc search "MCP73831" -n 5
hwtool agent jlc search "AP2112K-3.3" -n 5
hwtool agent jlc search "USB-C 16P receptacle" -n 10
hwtool agent jlc search "microSD card socket" -n 10
```

Only use returned `lcsc_id` values after checking package, lifecycle and assembly availability.

## Reference Datasheets And Product Pages

- Espressif ESP32-S3 datasheet and hardware design guidelines
- TDK InvenSense ICS-43434 product page / datasheet
- Microchip MCP73831 product page / datasheet
- Diodes Incorporated AP2112 product page / datasheet
