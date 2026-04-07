# 更新日志

语言：简体中文 | [English](CHANGELOG.md)

本项目的所有重要变更都会记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，并遵循
[语义化版本](https://semver.org/spec/v2.0.0.html)。

## [Unreleased]

### 新增

- 可构建并打包 `.eext` 的 JLCEDA 扩展骨架
- 第一版 Codex 桥接协议、受控命令路由、探活握手与确认门禁
- 最小可用的桥接服务端，支持 WebSocket 会话注册、心跳和请求路由
- 用于桥接状态、文档摘要和选区快照的只读查看能力
- 用于器件放置与导线创建的原理图写操作骨架
- BOM 导出流程、冒烟测试、排障说明、发布清单和版本管理文档
- 用于记录 JLCEDA 导入和执行结果的实机验证记录模板

### 变更

- 仓库文档已从通用模板说明更新为 Codex 到 JLCEDA 的桥接项目说明
