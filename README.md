# JLCEDA AIAgent

A bridge project that lets Codex connect to and control JLCEDA through a plugin.

Language: English | [简体中文](README.zh-CN.md)

## Overview

`JLCEDA AIAgent` is intended to turn the official JLCEDA extension capabilities into a hardware-development capability layer that Codex can call.

This repository is not just a generic EDA plugin template. It is a bridge between two sides:

- `Codex`, which understands higher-level tasks and generates execution plans
- `JLCEDA`, which performs the actual schematic, PCB, and project operations
- A plugin layer in the middle, which translates protocol messages, wraps capabilities, controls execution, and returns results

The end goal is to let Codex participate in hardware-development workflows within controlled boundaries, such as reading project state, assisting with component placement, executing selected editor actions, and exporting structured results.

## Current Status

The repository has moved beyond the initial template-cleanup stage. It now includes:

- A runnable JLCEDA extension skeleton with packaged `.eext` output
- A first-pass Codex bridge protocol and guarded command dispatcher
- Read-only project inspection commands
- Basic schematic write-command scaffolding
- BOM export support
- Smoke-test, troubleshooting, and release-check documentation

The main gap that remains is real JLCEDA runtime verification through local import and manual execution.

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
4. `npm run release:check`

For runtime verification inside JLCEDA, see:

- `docs/example-scenarios.md`
- `docs/troubleshooting.md`
- `docs/release-checklist.md`

## Planned Capability Areas

The roadmap currently focuses on these capability areas:

- Project inspection: read the current document, selection, components, and connectivity
- Safe execution: perform placement, wiring, annotation, and similar actions under explicit constraints
- Result reporting: return structured state, execution results, and error details back to Codex
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

1. Import the packaged extension into JLCEDA and complete real runtime validation
2. Confirm the bridge behavior for document inspection, write gating, and BOM export
3. Decide the next protocol expansion area, likely PCB operations or external transport
4. Record runtime findings and tighten the command contract where needed

## Reference

- Official JLCEDA extension guide: https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## License

See `LICENSE`.
