# KiCad Agent Suite

Agent-assisted KiCad hardware development pipeline.

Language: English | [简体中文](README.zh-CN.md)

## Overview

`KiCad Agent Suite` turns structured hardware requirements into KiCad-ready artifacts. The current workflow is file-based: it does not drive a GUI editor. Instead, it generates intermediate design models, simulation inputs, KiCad schematic/project files, and structured validation summaries.

The active pipeline is:

```text
RequirementSpec
  -> CircuitModel
  -> Netlist
  -> SPICE Netlist
  -> ngspice feedback
  -> KiCadExecutionPlan
  -> .kicad_pro + .kicad_sch
  -> optional kicad-cli ERC
```

The old EasyEDA/JLCEDA plugin bridge has been removed. New work targets KiCad project generation and reusable KiCad/LCSC resources only.

## Architecture

Think of the repository as a small hardware-design factory with four layers:

```text
kas
  -> pipeline / text-to-kicad / erc / validate-artifacts
  -> model -> netlist -> execution plan -> KiCad files
  -> kicad-cli / ngspice / JLC MCP adapters
  -> validation and summary reports
```

The code is organized around that flow:

- `src/kicad_suite/` holds the reusable pipeline, adapters, and validator logic
- `scripts/` contains thin CLI wrappers for local use and compatibility
- `.where/` stores generated project outputs, summaries, and planning notes

The main idea is simple: each stage has a clear input, a clear output, and a validation point before the next stage starts.

## Current Status

The KiCad path currently includes:

- JSON schemas for requirements, circuit models, netlists, SPICE netlists, ngspice feedback, and KiCad execution plans
- a Python requirement-to-KiCad pipeline
- a unified `kas` command-line entrypoint for the local workflow
- role-aware schematic layout rules with optional ELK layout support
- KiCad project and schematic file generation
- ngspice export, execution, parsing, and feedback artifacts
- optional KiCad ERC through `kicad-cli`
- artifact validation for summaries, ERC outputs, stale paths, and plan consistency
- a small ngspice regression fixture set

## Commands

Install Node dependencies first:

```bash
npm install
```

Run the default KiCad pipeline:

```bash
npm run pipeline
```

The underlying local entrypoint is `python scripts/kas.py ...`, which keeps the Python-side workflow on one command surface. You can also call `python -m kicad_suite ...` if you prefer the module form.

Useful aliases:

```bash
npm run kas -- --help
npm run text-to-kicad
npm run compile-plan
npm run write-project
npm run erc
npm run ngspice:regression
npm run validate:artifacts -- --summary .where/ci-nema23-run-summary.json
```

The pipeline can use default requirements, or read a structured requirement from `BRIDGE_REQUIREMENT_SPEC_JSON`:

```bash
BRIDGE_REQUIREMENT_SPEC_JSON='{"schema_version":"requirement-spec.v1", "...":"..."}' npm run text-to-kicad
```

PowerShell example:

```powershell
$env:KICAD_PROJECT_NAME = 'led_indicator'
$env:BRIDGE_REQUIREMENT_SPEC_JSON = '{ "schema_version": "requirement-spec.v1", "...": "..." }'
npm run text-to-kicad
```

## Outputs

By default, generated KiCad artifacts are written under:

```text
.where/kicad-output/<project_name>/
```

Typical outputs:

- `requirement-spec.json`
- `circuit-model.json`
- `netlist.json`
- `spice-netlist.cir`
- `ngspice-execution.json`
- `ngspice-feedback.json`
- `kicad-execution-plan.json`
- `<project_name>.kicad_pro`
- `<project_name>.kicad_sch`
- `kicad-write-summary.json`
- `kicad-erc.summary.json`
- `kicad-erc.json`
- `text-to-kicad-summary.json`
- JSON validation output on stdout when you pass `--json` to the validator

## Validation

Run the lightweight checks currently available from the root package:

```bash
npm run ngspice:regression
npm run validate:artifacts -- --summary .where/ci-nema23-run-summary.json
```

Run the validator against the JSON summary emitted by `kas pipeline` or `scripts/run_pipeline.py`; add `--strict` if you want warnings to fail the run. Add `--require-erc` if you want the run to fail when ERC was not enabled or available.

ERC validation is included when the summary exposes the ERC report paths. If `kicad-cli` is unavailable, the validator records that state instead of failing the whole pipeline.

Pipeline summaries may include top-level `warnings` for structured fallbacks such as mock parts resolution, disabled ERC, or postprocess registration failures. Those warnings mean the run completed, but they should be reviewed before treating the result as production-ready. Use `--strict` when you want those warnings to fail validation.

Optional KiCad ERC:

```bash
npm run erc
```

Set `KICAD_RUN_ERC=true` to let the full pipeline attempt ERC after writing the schematic. If `kicad-cli` is not installed, the runner returns a structured diagnostic instead of blocking file generation.

The run summary surfaces these conditions through structured `warnings` rather than hiding them. That keeps compatibility with older flows while making fallback paths visible to validators and agents.

## Online LCSC Search

The parts resolver integrates `@jlcpcb/mcp` for live LCSC/JLCPCB search and KiCad library installation. After `npm install`, these commands work without Claude Code-specific MCP configuration:

```powershell
npm run jlc:list-tools
node scripts\jlc_mcp_bridge.mjs search --query "STM32G431" --source lcsc --limit 3 --in-stock
node scripts\jlc_mcp_bridge.mjs install --id C529355 --project-path .where\nema23-industrial-stepper-driver-v0.1 --include-3d
```

Python resolver commands use the bridge by default:

```powershell
python scripts\resolve_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json --output .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json
python scripts\install_jlc_mcp_parts.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --include-3d
python scripts\write_jlc_mcp_part_lock.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --install-report .where\nema23-industrial-stepper-driver-v0.1\jlc-mcp-install-report.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1
```

When a JLC MCP install reports a broken symbol, repair it before accepting the lock file. For example, the NEMA23 LM393 comparator can be fixed with:

```powershell
python scripts\fix_lm393_jlc_mcp_symbol.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --id C5252905
python scripts\install_jlc_mcp_parts.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --register-only
```

Set `KICAD_DISABLE_JLC_MCP=1` to bypass the MCP bridge. The resolver can then use LCSC's official OpenAPI directly if credentials are configured:

```powershell
$env:LCSC_API_KEY = '<your-api-key>'
$env:LCSC_API_SECRET = '<your-api-secret>'
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
```

Optional settings:

- `LCSC_OPENAPI_BASE_URL` defaults to `https://ips.lcsc.com`
- `LCSC_OPENAPI_TIMEOUT_SEC` defaults to `15.0`
- `LCSC_OPENAPI_CURRENCY` defaults to `USD`
- `LCSC_MCP_BASE_URL` is only for the legacy local `/api/search` backend
- `JLC_MCP_COMMAND` and `JLC_MCP_ARGS` can override how the bridge starts the MCP server
- `JLC_MCP_DEBUG=1` prints MCP server stderr while debugging
- `JLC_MCP_INSTALL_TIMEOUT_SEC` and `JLC_MCP_INSTALL_RETRIES` tune batch install behavior

Without the MCP package, OpenAPI credentials, or a local MCP HTTP server, the resolver returns a short structured error instead of hanging on `localhost:3847`.

## Repository Layout

- `src/kicad_suite/`: reusable pipeline, adapters, CLI, and validator code
- `scripts/`: thin Python and Node wrappers for local use and compatibility
- `schemas/`: JSON schemas for the active model contracts
- `docs/`: architecture and workflow notes
- `skills/`: agent-facing workflow references
- `.where/`: local generated outputs, logs, and planning notes

## Development Direction

KiCad is now the only active EDA target. Prefer changes that improve:

- KiCad symbol and footprint mapping
- deterministic schematic generation
- netlist correctness
- ngspice coverage and feedback quality
- KiCad ERC integration
- unified command-line entrypoints
- artifact validation and reproducible summaries
- clear model contracts and regression fixtures

Do not add new EasyEDA/JLCEDA GUI bridge functionality. EasyEDA references should be limited to library/resource import tooling such as `easyeda2kicad`.

## License

See `LICENSE`.
