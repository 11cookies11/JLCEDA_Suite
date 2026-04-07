# Changelog

Language: English | [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Runnable JLCEDA extension skeleton with packaged `.eext` output
- First-pass Codex bridge protocol, guarded command routing, ping handshake, and confirmation gates
- A minimal bridge server with WebSocket session registration, heartbeats, and request routing
- A plugin-side remote transport client with saved settings, bridge menus, and remote-request handling
- A local end-to-end bridge smoke test plus reconnect scheduling for the plugin transport client
- Read-only project inspection commands for bridge status, document summary, and selection snapshot
- Schematic write-command scaffolding for component placement and wire creation
- BOM export flow, smoke-test coverage, troubleshooting notes, release checklist, and versioning guide
- A runtime validation report template for recording JLCEDA import and execution results

### Changed

- Repository documentation now describes the project as a Codex-to-JLCEDA bridge instead of a generic template
