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

The repository is still in the template-cleanup and architecture-definition stage. The current focus is to finish the following foundation work:

- Replace template repository content with project-specific documentation and metadata
- Build the minimum runnable JLCEDA extension skeleton
- Design the command protocol between Codex and the plugin
- Wrap the official JLCEDA APIs behind a stable internal capability layer

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

An initial development plan is already tracked inside the repository:

- Where board: `.where-agent-progress.md`
- Plan notes: `.where/development-plan.md`

Recommended immediate next steps:

1. Finish replacing template repository metadata and documentation
2. Add the minimum runnable JLCEDA extension skeleton
3. Draft the first version of the Codex command protocol
4. Pick the first end-to-end demo workflow

## Reference

- Official JLCEDA extension guide: https://prodocs.lceda.cn/cn/api/guide/how-to-start.html

## License

See `LICENSE`.
