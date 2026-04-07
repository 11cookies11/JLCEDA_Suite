# JLCEDA AIAgent

A bridge project that lets Codex connect to and control JLCEDA through a plugin.

Language: English | [简体中文](README.zh-CN.md)

## Overview

`JLCEDA AIAgent` is intended to turn the official JLCEDA extension capabilities into a hardware-development capability layer that Codex can call.

This repository is not just a generic EDA plugin template. It is becoming a bridge between two sides:

- `Codex` running on a server, which understands higher-level tasks and generates execution plans
- `JLCEDA` running on a local client, which performs the actual schematic, PCB, and project operations
- A middle layer made of a public bridge service plus a JLCEDA plugin, which translates protocol messages, wraps capabilities, controls execution, and returns results

The end goal is to let server-side Codex participate in hardware-development workflows within controlled boundaries, such as reading project state, assisting with component placement, executing selected editor actions, and exporting structured results.

## Current Status

The repository has moved beyond the initial template-cleanup stage. It now includes:

- A runnable JLCEDA extension skeleton with packaged `.eext` output
- A first-pass Codex bridge protocol and guarded command dispatcher
- A minimal bridge server with session registration, heartbeats, and request routing
- A plugin-side remote transport client built on `eda.sys_WebSocket`
- Read-only project inspection commands
- Basic schematic write-command scaffolding
- BOM export support
- Plugin and server smoke tests, troubleshooting, and release-check documentation

The main gaps that remain are connection hardening, end-to-end public-network validation, and real JLCEDA runtime verification through local import and manual execution.

## Implemented Commands

The current bridge implementation supports these commands:

- `system.ping`
- `system.get_bridge_status`
- `project.get_document_summary`
- `project.get_selection_snapshot`
- `schematic.place_component`
- `schematic.create_wire`
- `project.export_bom`

Unsupported but registered commands are rejected explicitly, and high-risk write operations are gated by confirmation rules.

## Validation

The repository already includes a repeatable local validation path:

1. `npm run lint`
2. `npm run build`
3. `npm run smoke-test`
4. `npm run server:smoke-test`
5. `npm run remote-client:smoke-test`
6. `npm run release:check`

For runtime verification inside JLCEDA, see:

- `docs/example-scenarios.md`
- `docs/troubleshooting.md`
- `docs/release-checklist.md`

## Planned Capability Areas

The roadmap currently focuses on these capability areas:

- Project inspection: read the current document, selection, components, and connectivity
- Safe execution: perform placement, wiring, annotation, and similar actions under explicit constraints
- Result reporting: return structured state, execution results, and error details back to Codex
- Remote transport: let the plugin connect outward to a public bridge service and receive remote commands
- Workflow packaging: provide reusable tasks such as "inspect project", "place component", and "export BOM"

## Suggested Architecture

The current recommended structure has four layers:

1. JLCEDA extension host layer
2. EDA capability adapter layer
3. Codex bridge/protocol layer
4. Hardware workflow layer

This keeps official JLCEDA API details isolated in lower layers while giving Codex a safer and more stable capability boundary.

## Development Plan

The working plan is tracked inside the repository:

- Where board: `.where-agent-progress.md`
- Plan notes: `.where/development-plan.md`

Current next steps:

1. Design the communication and security model between the plugin and the public bridge service
2. Implement the server-side bridge service and the plugin-side transport layer
3. Complete an end-to-end flow from server-side Codex to a running JLCEDA client
4. Follow up with real runtime validation and tighten the command contract where needed

## Reference

- Official JLCEDA extension guide: https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## License

See `LICENSE`.
