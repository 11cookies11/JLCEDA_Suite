# 更新日志

语言：简体中文 | [English](CHANGELOG.md)

本项目的所有重要变更都会记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，并遵循
[语义化版本](https://semver.org/spec/v2.0.0.html)。

## [0.1.21] - 2026-04-09

### 新增

- 为原理图和 PCB 的启发式规则新增 server 侧 profile，并提供查看与切换的控制接口
- 插件侧开始按 server profile 读取放件避让、标签卫生、PCB 卫生和 power block 建议的可调参数
- 明确插件作为稳定执行层的基线定位，后续调优优先放在 server profile 层

### 变更

- 远程桥接配置新增独立控制平面地址和令牌，并在可用时自动从服务地址推导

### 修复

- 原理图放件、标签和 power block 的可调参数不再硬编码，而是从当前 server profile 中读取

## [0.1.20] - 2026-04-09

### 修复

- `pcb.place_footprint` 增加源级兜底路径，避免 `pcb_PrimitiveComponent.create` 在当前 JLCEDA 运行时触发对象转换错误
- 增加覆盖直连和兜底两条路径的 smoke test，确保 PCB 落板链路可回归验证

## [Unreleased]
