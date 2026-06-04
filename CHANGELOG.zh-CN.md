# 更新日志

语言：简体中文 | [English](CHANGELOG.md)

所有项目的重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/spec/v2.0.0.html)。

## [0.3.2] - 2026-06-05

### 变更

- 在同步包元数据和 release 文档之后，发布一个后续的 release 构建。

## [0.3.1] - 2026-06-05

### 变更

- 删除 symbol fallback 路径，缺失或不匹配的 KiCad symbol 现在会直接失败，而不是静默生成占位器件。
- 刷新了已验证的 `esp32c3-minimal-system` 和 `stm32f103-minimal-system` 示例，使其对齐当前协议和 release 布局。
- 同步了 Python 包元数据版本，使其与可发布的 `package.json` 版本保持一致。

## [0.1.28] - 2026-05-11

### 修复

- 提升远程 bridge 连接韧性：心跳和响应发送失败会按传输故障处理并触发重连。
- 默认关闭 server 端 WebSocket 协议级 heartbeat，避免与 JLCEDA WebSocket 运行时不兼容，同时保留应用层心跳。
- 增加 heartbeat 失败后重连的 bridge smoke 覆盖。

## [0.1.27] - 2026-04-12

### 新增

- 添加了 Python 多页放置验证脚本 (`server_placement_multipage_test.py`)，用于验证从简单到密集场景的放置行为。
- 添加了通用电路模型到执行计划的编译器 (`compile_execution_plan.py`) 及配套映射指南。

### 修复

- 改进了原理图放置碰撞回避，在最终确定候选坐标前增加了运行时占用检查。

## [0.1.26] - 2026-04-09

### 修复

- 为 GitHub 发布检查添加了 `XMLHttpRequest` 回退方案，使插件自动更新在 `fetch` 不可用的 JLCEDA 运行时中正常工作
- 保留了 0.1.24 的菜单标签修复和 suite 发布资源布局

## [0.1.24] - 2026-04-09

### 修复

- 将菜单标签替换为 ASCII 安全标题 (`Introduction`、`Open Console`)，避免在 JLCEDA 菜单中出现 `???` 乱码
- 保留了 0.1.23 的扩展管理器元数据打包修复，确保 README 详情在打包版本中可用

## [0.1.23] - 2026-04-09

### 修复

- 将 `README.md` 和 `README.zh-CN.md` 打包进扩展包，使扩展管理器可以渲染插件详情页
- 为扩展清单元数据添加了 suite 主页和问题跟踪链接

## [0.1.22] - 2026-04-09

### 新增

- 添加了专用插件介绍页和内置图标，方便首次用户在打开控制台前了解该软件包

### 变更

- 将项目品牌从 JLCEDA AIAgent 重命名为 JLCEDA Suite，涵盖插件、服务器默认值、更新设置和发布产物
- 将套件命名拆分为 `JLCEDA Suite Plugin`、`JLCEDA Suite Server` 和 `JLCEDA Suite Skill`
- 将打包的技能包和发布产物重命名为 `jlceda-suite-*` 命名方案

## [0.1.21] - 2026-04-09

### 新增

- 为原理图和 PCB 启发式规则添加了服务端规则配置文件，包含检查和切换的配置端点
- 插件端基于配置的阈值：放置回避、标签卫生、PCB 卫生和电源块建议
- 稳定的插件执行层基线指导，方便后续调优在服务端配置层进行

### 变更

- 远程桥接配置现在包含独立的控制面 URL 和令牌，在可能的情况下可从服务器 URL 自动推导

### 修复

- 原理图放置、标签放置和电源块启发式规则现在从活动服务器配置中读取可调参数，而非硬编码常量

## [0.1.20] - 2026-04-09

### 修复

- 为 `pcb.place_footprint` 添加了源级回退路径，避免 `pcb_PrimitiveComponent.create` 中当前 JLCEDA 运行时对象转换失败
- 为直接 PCB 放置路径和回退路径添加了冒烟测试覆盖

## [Unreleased]
