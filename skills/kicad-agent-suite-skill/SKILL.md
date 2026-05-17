---
name: kicad-agent-suite-skill
description: Help an AI agent use this repository's reusable hardware-development resources to design, validate, and improve circuit projects. Use when working from requirements to circuit models, netlists, simulation feedback, KiCad schematic/project generation, symbol/layout resources, LCSC part selection, EasyEDA footprint import, or refactoring the hardware agent pipeline for better generality without hardcoded project-specific logic.
---

# Hardware Development Skill

## When to use

Use this skill when the user wants an AI agent to use repository resources to produce, inspect, validate, or improve hardware design artifacts.

The active implementation target is KiCad, but the skill's purpose is broader: use structured requirements, circuit models, netlists, reusable component knowledge, simulation feedback, symbol resources, layout profiles, and validation tools as a hardware-development workspace.

## Workspace Mode (preferred — single root, no path confusion)

Set `KICAD_WORKSPACE` to the project root. All paths derive from it automatically:

```
my-project/                     ← $env:KICAD_WORKSPACE
├── circuit-model.json
├── part-selection-results.json
├── libraries/                  ← put JLC-MCP assets here
│   ├── symbols/    (.kicad_sym)
│   ├── footprints/ (.pretty/)
│   └── 3dmodels/   (.step)
└── output/                     ← auto-generated
    └── {project_name}/
        ├── *.kicad_{pro,sch,pcb}
        └── libraries/          ← auto-copied from workspace
```

If `KICAD_WORKSPACE` is not set, the pipeline auto-detects it from `circuit-model.json`'s parent directory (when it contains `libraries/symbols/`).

**Do NOT scatter files across `.where/` and `examples/` with different paths.** This was the root cause of v13's library resolution failures.

## Current pipeline workflow (non-linear, iterative)

```
circuit-model.json + JLC libs → compile_plan() → write_project() → postprocess → ERC
                       ↑                            │
                       └── feedback loops ──────────┘
```

Each stage produces versioned JSON. Changes to earlier stages just re-run the pipeline.

1. **Clarify requirements** — electrical constraints, interfaces, power
2. **Build circuit-model.json** — components (ref, role, value) + nets (name, kind, members)
3. **Part selection** — LCSC Resolver → Part Selector → JLC MCP install
4. **Compile execution plan** — symbol mapping, area-aware layout, library validation
5. **Write KiCad files** — schematic (wire from pin tip to label), PCB, project
6. **Post-process** — copy JLC libraries, inject symbols, fix pin types, register lib tables
7. **ERC validation** — kicad-cli, check for pin_not_connected=0

## Critical gotchas (cost weeks to debug)

### Fake 2-pin fallback (silent pin_not_connected disaster)
If `kicad_symbol_roots()` cannot find a JLC library file, `symbol_block_for_lib_id()` silently returns a fake 2-pin symbol with pins at ±5.08mm from body center. For a 57-pin RP2040, this means ALL wires go to wrong positions → `pin_not_connected` × 274.

**Pre-flight check**: `_validate_symbol_libraries()` in `compile_kicad_execution_plan.py` now catches this BEFORE generation and raises a clear RuntimeError listing which `.kicad_sym` files are missing and which components need them.

**To debug**: run `parse_symbol_pin_map(lib_id)` — if it returns ≤2 pins for a JLC-MCP symbol, the library file is not found.

### NaN arcs in JLC-MCP symbols
Some JLC-MCP `.kicad_sym` files contain `<arc (mid NaN NaN)>`. This crashes KiCad GUI when loading the schematic. `sanitize_symbol_block()` removes them. If you see `NaN` in any `.kicad_sym` or `.kicad_sch` file, run it through that function or regex-remove the arc block.

### sym-lib-table / fp-lib-table path mismatch
The original v13 had `.where/` paths that didn't exist. In workspace mode, tables are auto-generated with correct absolute paths. If KiCad still can't find libraries, verify:
1. `libraries/symbols/` has the actual `.kicad_sym` files
2. `sym-lib-table` entries point to those files with absolute paths
3. KiCad restarted after table changes

### Don't reuse old execution plans
v13 → v17 → v19 showed that reusing pre-compiled JSON plans bypasses all layout and mapping improvements. Always regenerate from `circuit-model.json` using `compile_plan()`.

### Pin endpoint coordinate system
`pin_endpoint(symbol, pin_number)` returns the **pin tip absolute position** (electrical connection point). Wire must start EXACTLY here. `endpoint_from_pin()` applies rotation transform. The returned `direction` is the wire exit convention (0=left, 180=right, 90=up, 270=down).

### CLI vs GUI ERC discrepancy
The CLI may produce different ERC results than the GUI (v19: CLI=100, GUI=718). The CLI is the authoritative source. Use `--format json` for machine-readable output.

## ERC diagnostic mapping

| ERC type | Cause | Fix |
|----------|-------|-----|
| `pin_not_connected` × many | JLC lib not found → fake 2-pin symbols | Check workspace, verify `libraries/symbols/` |
| `multiple_net_names` | Different labels shorted by single wire | Check circuit-model.json net members |
| `pin_to_pin` (bidirectional↔power_out) | Power pins typed wrong in library | Pin type fix in pipeline_postprocess |
| `lib_symbol_mismatch` × many | Embedded symbols out of sync | "Update Symbols from Library" in KiCad GUI |
| `label_dangling` | Label not connected to net | Usually cascading from pin_not_connected |

## Running the pipeline

```powershell
# From workspace
$env:KICAD_WORKSPACE = "D:/path/to/project"
python -m kicad_suite.pipeline_coordinator circuit-model.json output/

# Standalone ERC
& "D:/Program Files/KiCad/10.0/bin/kicad-cli.exe" sch erc --format json --output erc.json project.kicad_sch
```

## Agent Quick Start

When an agent needs to use this repository directly, prefer this order:

1. Inspect the user's goal and identify the missing electrical constraints.
2. Use the unified local entrypoint for pipeline work:
   - `python scripts/kas.py pipeline <model.json> <output-dir>`
   - `python scripts/kas.py validate-artifacts --summary <summary.json>`
   - `python scripts/kas.py erc`
3. If real parts are needed, use the repository's parts pipeline and JLC MCP bridge instead of ad hoc searches or manual library copying.
4. Read the generated summary before changing the design. Let validation errors, ERC failures, and missing paths drive the next edit.
5. Improve reusable resources, configs, and validators first; avoid patching only the current board unless the change is truly one-off.
6. Treat top-level summary warnings as structured fallback signals. A run can complete with warnings and still need review before acceptance.

## Default Workflow

1. Read the user's design intent and identify missing electrical constraints.
2. If the requirement is underspecified, clarify input source, outputs, current, interfaces, packages, and acceptance checks.
3. Build or normalize `BRIDGE_REQUIREMENT_SPEC_JSON`.
4. Run the KiCad pipeline with `npm run pipeline` or `python scripts/kas.py pipeline <model.json> <output-dir>`.
5. If real LCSC parts are needed, enable `KICAD_PARTS_PIPELINE=true` to generate `part.lock.yaml` and `part-risk-report.md`.
6. Review generated model, netlist, ngspice feedback, KiCad execution plan, ERC summary, validation report, and any top-level summary warnings.
7. Run `npm run ngspice:regression`, `npm run erc`, or `npm run validate:artifacts -- --summary <summary.json>` when relevant.
8. When code or pipeline gaps appear, improve the reusable hardware-development resources rather than patching only the current board.
9. Report generated files, diagnostics, part selection summary, and next modeling, mapping, validation, or resource-improvement tasks.

## Parts Pipeline (New)

The full component lifecycle from requirement to locked BOM:

```
PartRequirement → LCSC Resolver → ResolverResult (candidates)
                                     ↓
                              Part Selector → SelectedPart (score + reasons + risks)
                                     ↓
                              KiCad Lib Importer → project/libs/ + part.lock.yaml + part-risk-report.md
```

### Module Overview

| Module | File | Purpose |
|--------|------|---------|
| LCSC Resolver | `src/kicad_suite/lcsc_resolver.py` | Search LCSC + EasyEDA resources for parts by MPN/function/package |
| Part Selector | `src/kicad_suite/part_selector.py` | Multi-factor scoring (MPN/package/Basic/stock/price/library), risk assessment, final selection |
| Parts Pipeline | `src/kicad_suite/parts_pipeline.py` | Integration: resolve -> select -> lock file -> risk report |
| KiCad Lib Importer | `src/kicad_suite/kicad_lib_importer.py` | Import JLC assets, generate part.lock.yaml, build risk report |

### Env Vars

| Variable | Purpose |
|----------|---------|
| `KICAD_PARTS_PIPELINE=true` | Enable parts pipeline in server_text_to_kicad / run_pipeline |
| `KICAD_PARTS_IMPORT=true` | Also run KiCad library import after part selection |
| `EASYEDA2KICAD_BIN` | Path to easyeda2kicad executable |
| `KICAD_SYMBOL_MAP_FILE` | Override symbol map (e.g., project-specific JLC map) |
| `KICAD_EXTRA_FOOTPRINT_DIR` | Additional footprint search paths |
| `KICAD_DISABLE_JLC_MCP` | Set to `1` to bypass the repository `@jlcpcb/mcp` bridge |
| `JLC_MCP_COMMAND` | Optional custom command for starting the JLC MCP server |
| `JLC_MCP_ARGS` | Optional JSON array of command args for `JLC_MCP_COMMAND` |
| `JLC_MCP_DEBUG` | Set to `1` to print MCP server stderr |
| `JLC_MCP_INSTALL_TIMEOUT_SEC` | Optional per-part timeout for JLC MCP batch installation |
| `JLC_MCP_INSTALL_RETRIES` | Optional retry count for JLC MCP batch installation |
| `LCSC_API_KEY` | LCSC official OpenAPI key for online part search |
| `LCSC_API_SECRET` | LCSC official OpenAPI secret for request signatures |
| `LCSC_OPENAPI_BASE_URL` | Optional OpenAPI base URL; defaults to `https://ips.lcsc.com` |
| `LCSC_OPENAPI_TIMEOUT_SEC` | Optional OpenAPI request timeout |
| `LCSC_OPENAPI_CURRENCY` | Optional pricing currency, e.g. `USD`, `CNY`, `EUR`, `HKD` |
| `LCSC_MCP_BASE_URL` | Optional legacy local MCP HTTP backend exposing `/api/search` |

Prefer the `kas` entrypoint when possible. Use environment variables for configuration, not for choosing which stage to run.
Treat `src/kicad_suite/run_pipeline.py` and `src/kicad_suite/parts_pipeline.py` as compatibility wrappers only; prefer `kas` and the newer module paths for new automation.
Treat `scripts/kas.py` and `src/kicad_suite/cli.py` as the stable command surface; older top-level wrappers are just transition paths.
Treat run summaries as the main compatibility surface. Prefer the stable `files`, `counts`, `erc`, `diagnostics`, `postprocess`, and `warnings` fields, while keeping compatibility with older `output_files` and direct file-path fields when present.
If a breaking summary change is unavoidable, bump `schema_version`, keep the previous readable form for a transition window, and treat top-level `warnings` as "completed with fallback and needs review" rather than as free-form log noise.

### Compatibility Policy

- Prefer stable entrypoints for new work.
- Use wrappers only as transition paths for older scripts and compatibility tests.
- Keep additive summary changes when possible.
- If you must break a summary shape, bump the schema version and add regression coverage for both the old and new forms.
- Treat compatibility warnings as actionable review signals, not optional chatter.

### Wrapper Retirement Timeline

- Now: keep wrappers as forwarding shims for older scripts.
- Next: mark a wrapper deprecated in docs/tests once the stable module path fully covers it.
- Later: after one transition window with regression coverage, reduce the wrapper to the smallest possible shim.

### Canonical Schema Versions

These versions are the repo's shared contract names and should stay aligned with the code:

- `requirement-spec.v1`
- `circuit-model.v1`
- `netlist.v1`
- `spice-netlist.v1`
- `ngspice-execution.v1`
- `ngspice-feedback.v1`
- `kicad-execution-plan.v1`
- `kicad-project-write-result.v1`
- `kicad-erc-result.v1`
- `text-to-kicad-summary.v1`
- `part-lock.v1`

### Field-Level Contracts

- Run summary: stable fields are `files`, `counts`, `erc`, `diagnostics`, `postprocess`, and `warnings`.
- ERC result: stable fields are `enabled`, `attempted`, `success`, `finding_count`, `summary_file`, `output_file`, `error`, and `warnings`.
- Execution plan: stable fields are `request_id`, `target`, `symbols`, `nets`, and `diagnostics`.
- Part lock: stable fields are `project`, `generated_at`, and `parts`.
- Compatibility fields may still appear, but new code should target the stable fields first.

### Online LCSC Resolver

For live component search, use the repository bridge to `@jlcpcb/mcp`:

```powershell
npm run jlc:list-tools
node scripts\jlc_mcp_bridge.mjs search --query "STM32G431" --source lcsc --limit 3 --in-stock
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
```

To import a selected component into KiCad libraries through JLC MCP:

```powershell
node scripts\jlc_mcp_bridge.mjs install --id C529355 --project-path .where\nema23-industrial-stepper-driver-v0.1 --include-3d
```

To install all selected, non-review parts from a selector result:

```powershell
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json --output .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json
python scripts\install_jlc_mcp_parts.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --include-3d --timeout 180 --retries 1
python scripts\write_jlc_mcp_part_lock.py --selections .where\nema23-industrial-stepper-driver-v0.1\selected-parts.json --install-report .where\nema23-industrial-stepper-driver-v0.1\jlc-mcp-install-report.json --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1
```

For known symbol issues, apply a targeted repair before writing the final lock:

```powershell
python scripts\fix_lm393_jlc_mcp_symbol.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --id C5252905
python scripts\install_jlc_mcp_parts.py --project-dir .where\nema23-industrial-stepper-driver-v0.1\nema23_industrial_stepper_driver_v0_1 --register-only
```

The Python resolver prefers this bridge when available. As a fallback, it can use LCSC's official OpenAPI:

```powershell
$env:LCSC_API_KEY = '<your-api-key>'
$env:LCSC_API_SECRET = '<your-api-secret>'
python scripts\select_parts.py --json examples\nema23-industrial-stepper-driver-v0.1\part.requirements.resolver.json
```

If neither the MCP bridge nor OpenAPI credentials are available, the CLI reports a structured setup error. The old `localhost:3847` path is treated only as an optional legacy backend.

#### JLC MCP Details

- Treat `@jlcpcb/mcp` as the preferred online LCSC source for this repository.
- Do not assume Claude Code's `.claude/mcp.json` is available in other agent runtimes; use `scripts/jlc_mcp_bridge.mjs` from the repo instead.
- The bridge starts the local dependency at `node_modules/@jlcpcb/mcp/dist/index.js` after `npm install`; if missing, it can fall back to `npx -y @jlcpcb/mcp@0.3.2`.
- `component_search` uses `source=lcsc` for official LCSC/JLCPCB parts and `source=community` for EasyEDA community libraries.
- Pass requirement filters through to live search: `PartRequirement.in_stock_only` maps to `--in-stock`, and `PartRequirement.basic_only` maps to `--basic-only`.
- `library_install` accepts an LCSC ID such as `C529355` and can install KiCad assets into a project-local library with `--project-path`.
- `scripts/install_jlc_mcp_parts.py` reads selector JSON and installs selected LCSC IDs in batch; by default it skips `needs_review=true` parts unless `--include-review` is supplied.
- `scripts/write_jlc_mcp_part_lock.py` converts selector and install reports into `part.lock.yaml` and `part-risk-report.md`.
- `scripts/fix_lm393_jlc_mcp_symbol.py` repairs the known LM393 SOP-8 missing-pin case using the standard dual-comparator pinout.
- Treat MCP validation warnings as design work, not noise. For example, `pin_pad_match=false` or `pin_count=0` means the generated symbol/footprint must be manually checked or repaired before schematic acceptance.
- Use `JLC_MCP_DEBUG=1` only while diagnosing bridge startup or MCP stderr output.
- Use `KICAD_DISABLE_JLC_MCP=1` only when intentionally testing OpenAPI or legacy HTTP fallback behavior.

Direct checks:

```powershell
npm run jlc:list-tools
node scripts\jlc_mcp_bridge.mjs search --query "100nF 0603" --source lcsc --limit 3 --in-stock --basic-only
node scripts\jlc_mcp_bridge.mjs search --query "XIAO RP2040" --source community --limit 3
```

### Part Selector Scoring Rules

1. MPN exact match: +50, partial: +30
2. Package exact match: +25, partial: +15
3. JLCPCB Basic Part: +15
4. Stock depth: ≥10k +10, ≥1k +7, ≥100 +4
5. EasyEDA library completeness: symbol+footprint+3D +10, symbol+footprint +5
6. Price within budget: proportional up to +10
7. Complex package penalty (BGA/QFN/LGA/DFN/WLCSP): -15
8. Score capped at 0-100

### Risk Classification (for EasyEDA import)

| Level | Package types |
|-------|--------------|
| **Low** | 0603/0805/1206 passives, SOT-23, SOT-223, SOP, QFN/QFP, 3225/5032 crystals |
| **Medium** | BGA, LGA, WLCSP, modules, edge-pad devices, headers/connectors |
| **High** | USB-C, FPC/FFC, card sockets (TF/SIM), DC jacks, irregular pads, slotted holes |

### part.lock.yaml Format

```yaml
schema_version: part-lock.v1
project: esp32-c3-debugger
generated_at: "2026-05-15T..."
parts:
  - ref: U1
    role: main_mcu
    mpn: STM32F103C8T6
    value: STM32F103C8Tx
    lcsc_id: C8734
    package: LQFP-48
    source: jlcpcb_parts
    kicad_symbol: ""
    kicad_footprint: jlc_footprints:LQFP-48_...
    risk: low
    note: Standard package
    price: 2.50
    status: locked
```

### KiCad → EasyEDA Pro Import

Every symbol generated by the pipeline includes three hidden properties:
- `LCSC` — LCSC part number for EasyEDA matching
- `MPN` — Manufacturer Part Number
- `Manufacturer` — Brand name

EasyEDA Pro reads these on import to automatically match components to their LCSC library entries.

## Circuit Model Format

The pipeline accepts a `circuit-model.json` with this structure:

```json
{
  "schema_version": "circuit-model.v1",
  "request_id": "...",
  "topology": "...",
  "components": [
    {
      "ref": "U1",
      "role": "stm32f103_mcu",
      "value": "STM32F103C8Tx",
      "selected_part": {
        "part_id": "C8734",
        "display_name": "STM32F103C8T6",
        "lcsc_id": "C8734",
        "mpn": "STM32F103C8T6",
        "manufacturer": "STMicroelectronics",
        "package": "LQFP-48",
        "pin_count": 48
      },
      "candidate_parts": [],
      "availability_status": "available"
    }
  ],
  "nets": [
    { "name": "+3V3", "members": ["U2.2", "C2.1", "U1.9", "U1.24", "U1.36", "U1.48"] },
    { "name": "GND", "members": ["U2.1", "U1.8", "U1.23", "U1.35", "U1.47"] }
  ],
  "design_decisions": [...],
  "risks": [...]
}
```

Key conventions:
- `ref`: KiCad reference designator (U1, R1, C1, etc.)
- `role`: unique functional identifier (stm32f103_mcu, ldo_regulator)
- `nets.members`: `REF.PIN_NUMBER` format (e.g., "U1.7" for U1 pin 7)
- `selected_part.lcsc_id`: real LCSC part number for EasyEDA matching
- Simple components (R/C/L/LED) only need 2 pins; complex ICs need correct pin numbers

## Library Configuration

### Global EasyEDA Library (install once)

```bash
# Copy imported libraries to KiCad user directory
cp project-dir/libs/jlc_symbols.kicad_sym $APPDATA/kicad/10.0/libraries/
cp project-dir/libs/jlc_footprints.pretty/* $APPDATA/kicad/10.0/libraries/jlc_footprints.pretty/
cp project-dir/libs/3dmodels/* $APPDATA/kicad/10.0/libraries/3dmodels/

# Register in KiCad global sym-lib-table (use absolute paths on Windows!)
# sym-lib-table entry:
#   (lib (name "jlc_symbols")(type "KiCad")(uri "C:/Users/.../libraries/jlc_symbols.kicad_sym")...)
```

### Project-Local Library

The pipeline auto-generates `pinned_footprint_libs` and `pinned_symbol_libs` in `.kicad_pro` when `libs/` directory exists. The `fp-lib-table` and `sym-lib-table` are also auto-generated.

**Critical**: On Windows, use absolute paths in sym-lib-table. `${KICAD_USER_DIR}` does not always resolve correctly. Verify with:
```bash
kicad-cli sym export svg --symbol "jlc_symbols:STM32F103C8T6" --output test/ path/to/lib.kicad_sym
```

## Common Issues

### MCU symbol not rendering in KiCad
**Cause**: sym-lib-table path variable not resolving (especially `${KICAD_USER_DIR}` on Windows).
**Fix**: Use absolute Windows paths in global `sym-lib-table`.

### "找不到封装" (footprint not found)
**Cause**: KiCad `pinned_footprint_libs` in `.kicad_pro` not set, or `fp-lib-table` path incorrect.
**Fix**: Ensure `.kicad_pro` has `libraries.pinned_footprint_libs` with correct `${KIPRJMOD}` relative path. Regenerate with `KICAD_PARTS_PIPELINE=true`.

### EasyEDA API 403 errors
**Cause**: Rate limiting from easyeda.com API.
**Fix**: Use `--delay 4.0` with import script. Try alternative LCSC IDs for the same component from different manufacturers.

### "pin X doesn't exist in symbol"
**Cause**: Circuit model netlist uses pin numbers that don't match the KiCad symbol's pin numbering.
**Fix**: Use the same symbol source consistently. EasyEDA symbols use numeric pins. KiCad system symbols may use named pins. For MCUs, prefer KiCad system symbols for the schematic (better rendering) with EasyEDA footprints.

## Scripts

### Root Commands

- `npm run kas -- --help`: inspect the unified local CLI
- `npm run pipeline`: run the main KiCad pipeline through the unified entrypoint
- `npm run text-to-kicad`: run the text-to-KiCad flow through the unified entrypoint
- `npm run validate:artifacts -- --summary <summary.json>`: validate generated outputs and ERC summaries
- `npm run compile-plan`: compile CircuitModel and Netlist into KiCadExecutionPlan
- `npm run write-project`: write KiCad project files from an execution plan
- `npm run erc`: run KiCad ERC when `kicad-cli` and input paths are available
- `npm run ngspice:regression`: run ngspice feedback regression fixtures

### Parts Commands

- `python scripts/resolve_parts.py`: test LCSC Resolver with built-in demo
- `python scripts/select_parts.py`: test Part Selector with built-in demo
- `node scripts/jlc_mcp_bridge.mjs search --query "STM32G431" --source lcsc --limit 3 --in-stock`: direct `@jlcpcb/mcp` search
- `node scripts/jlc_mcp_bridge.mjs install --id C529355 --project-path <project-dir>`: install JLC MCP KiCad library assets
- `python scripts/install_jlc_mcp_parts.py --selections selections.json --project-dir <project-dir>`: batch-install selected non-review LCSC assets through JLC MCP
- `python scripts/write_jlc_mcp_part_lock.py --selections selections.json --install-report jlc-mcp-install-report.json --project-dir <project-dir>`: write JLC MCP `part.lock.yaml`
- `python scripts/fix_lm393_jlc_mcp_symbol.py --project-dir <project-dir> --id C5252905`: repair missing LM393 pins after JLC MCP install
- `python scripts/import_parts.py --selections selections.json --project-dir ./project`: import parts to project
- `python scripts/import_jlc_parts.py <circuit-model.json> <project-dir> [--delay 3.0]`: import all LCSC parts from a circuit model
- `python scripts/demo_parts_pipeline.py`: end-to-end parts pipeline demo
- `python scripts/demo_e2e_pipeline.py`: full pipeline demo with KiCad output
- `python scripts/run_pipeline.py <circuit-model.json> <output-dir>`: run full KiCad pipeline from existing circuit model

### `scripts/kas.py`

Unified local CLI entrypoint for this skill.

- `python scripts/kas.py pipeline <model.json> <output-dir>`: run the main KiCad pipeline
- `python scripts/kas.py validate-artifacts --summary <summary.json>`: validate generated outputs and ERC summaries
- `python scripts/kas.py erc`: run KiCad ERC on the resolved schematic
- `python scripts/kas.py text-to-kicad`: run the text-to-KiCad flow

Prefer `kas` for new work instead of calling stage scripts directly.

## Output Expectations

The pipeline normally writes into:

```text
.where/kicad-output/<project_name>/
```

Expected artifacts:

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
- validation output on stdout when `--json` is used

With `KICAD_PARTS_PIPELINE=true`, additionally:

- `part.lock.yaml`
- `part-risk-report.md`
- `libs/jlc_symbols.kicad_sym`
- `libs/jlc_footprints.pretty/`
- `libs/3dmodels/`
- `sym-lib-table`
- `fp-lib-table`

## Call Strategy

- Keep assumptions explicit in the requirement and decision log.
- Treat `Netlist` as the source of electrical connection truth.
- **Prefer real LCSC parts with EasyEDA symbols/footprints over placeholders.**
- **Use Part Selector to score and choose components; record decisions in part.lock.yaml.**
- **For MCUs, KiCad system symbols + EasyEDA footprints is a valid hybrid approach.**
- **Always embed LCSC/MPN/Manufacturer properties on schematic symbols for EasyEDA Pro compatibility.**
- **Use absolute paths in sym-lib-table on Windows; verify with kicad-cli export.**
- Treat config files, KiCad symbols, examples, and references as reusable resources the agent should improve over time.
- Prefer real KiCad library mappings over placeholder symbols when available.
- Prefer reusable config/resources/parsers over hardcoded demo-specific branches.
- Refactor when the current structure blocks generality; do not only append special cases.
- When the issue is electrical, modify the circuit model, netlist, or KiCad execution plan.
- When the issue is in generation, validation, orchestration, or CLI behavior, modify the code.
- Use ngspice feedback to surface verification risk, not to silently accept a design.
- Use KiCad ERC as an additional check after file generation.
- Use `validate-artifacts` before declaring a run complete, and use `--strict` when you want structured warnings to fail the run.
- Do not reintroduce EasyEDA/JLCEDA GUI bridge flows; keep EasyEDA references limited to library/resource import tooling.

## Tooling Compatibility Rules

- Preserve existing CLI entrypoints when possible; add adapters or wrappers before removing old paths.
- Prefer additive changes over breaking changes. If behavior must change, keep the old form working during a transition period.
- Keep `scripts/` thin and move shared logic into `src/kicad_suite/` so compatibility wrappers can stay small.
- When a schema or summary format changes, bump the schema version and keep the validator able to read the previous stable shape when feasible.
- Keep summary warnings structured and machine-readable; do not hide fallback paths in prose-only logs when they affect acceptance.
- Add or update tests for both the new path and the legacy path before removing compatibility code.
- Treat deprecations explicitly: document them in the skill, README, or release notes instead of letting callers discover breakage by accident.
- For any new stage, prefer a stable adapter layer over direct coupling to one board, one script, or one temporary folder.

## Reference Map

Use the smallest relevant reference set:

- `references/requirement-clarification.md` for incomplete requirements
- `references/strap-and-bias-rules.md` for mode pins, straps, pulls, and defaults
- `references/netlist-guidelines.md` for connection truth and simulation-ready structure
- `references/simulation-guidelines.md` for ngspice validation
- `references/decision-log-template.md` for engineering decisions and assumptions
- `references/schematic-construction-description.md` for strict schematic intent structure
- `references/refactoring-design-rules.md` before changing generator code, mappings, symbol resources, layout logic, or scripts
- `references/text-to-schematic.md` for the older text-to-schematic terminology, interpreted as text-to-KiCad in this repository

## Resource Model

Treat the repository as the agent's hardware-development resource base:

- `src/kicad_suite/` contains reusable implementation code
- `config/` contains mapping and layout policy
- `resources/kicad/symbols/` contains local KiCad symbol resources
- `examples/` contains reusable circuit-model examples
- `schemas/` contains JSON Schema contracts for all pipeline stages
- `references/` inside this skill contains engineering workflow guidance
- generated outputs are evidence to inspect, not source-of-truth design rules

## Troubleshooting: JLC-MCP Symbols Not Visible in KiCad

### Symptom

After running `python scripts/run_pipeline.py`, opening the generated `.kicad_pro` in KiCad shows JLC-MCP components as tiny 2-pin boxes or completely blank symbols. This affects all non-Device-library components (STM32, gate drivers, MOSFETs, LDOs, connectors from `@jlcpcb/mcp`).

### Root Cause

`kicad_project_writer.py` generates 2-pin placeholder stubs for symbols outside the KiCad Device library. These stubs are embedded in the `.kicad_sch` file's `(lib_symbols ...)` section. KiCad reads this embedded data to render symbols — it **does not resolve external sym-lib-table references** during rendering.

Even if the full symbol definition exists in `libraries/symbols/JLC-MCP-*.kicad_sym` and is correctly registered in `sym-lib-table`, KiCad will use the embedded stub instead.

### Automatic Fix (Built-in)

As of commit `2136792`, `run_pipeline.py` automatically runs symbol injection after schematic generation. The `_inject_jlc_symbols()` function:

1. Scans `libraries/symbols/JLC-MCP-*.kicad_sym` for all installed symbols
2. Replaces each 2-pin stub in the schematic's `lib_symbols` section with the complete symbol definition (all pins, graphics, properties)
3. Handles symbol name prefixing (`STM32G431CBT6` → `JLC-MCP-MCUs:STM32G431CBT6`)

The pipeline summary includes `symbols_injected: true` when injection succeeds.

### Manual Fix

If automatic injection fails or symbols are installed after pipeline run:

```powershell
python scripts/inject_jlc_symbols.py
```

This operates on the schematic at `.where/<project>/<project_name>/<project_name>.kicad_sch`.

### Preconditions

- JLC-MCP symbols must be installed via `node scripts/jlc_mcp_bridge.mjs install --id Cxxxxx --project-path <dir> --include-3d`
- For KiCad 10.0 compatibility, upgrade library files first: `kicad-cli sym upgrade <library.kicad_sym>`
- The `libraries/symbols/` directory must contain the upgraded `.kicad_sym` files

### Verification

```powershell
# Export schematic to SVG — rendered symbols will be visible
kicad-cli sch export svg -o ./preview/ .where/<project>/<project_name>/<project_name>.kicad_sch

# Check embedded symbol pin counts
python -c "
import re
from pathlib import Path
sch = Path('.where/<project>/<project_name>/<project_name>.kicad_sch').read_text()
for m in re.finditer(r'\(symbol \"(JLC-MCP-[^\"]+)\"', sch):
    s = m.start(); d = 0
    for i in range(s, len(sch)):
        if sch[i] == '(': d += 1
        elif sch[i] == ')': d -= 1
        if d == 0:
            pins = sch[s:i].count('(pin ')
            print(f'{m.group(1)}: {pins} pins {\"OK\" if pins > 2 else \"STUB\"}')
            break
"
```

### Known Edge Case

JLC MCP may miscategorize some symbols (e.g., placing `DB2EVC` and `KF2EDGR` connectors in `JLC-MCP-Capacitors.kicad_sym`). The injection script searches ALL `JLC-MCP-*.kicad_sym` files, so miscategorized symbols will still be found and injected under their correct library prefix.

## Root Cause: KiCad 10.0 Path Resolution

JLC MCP (`@jlcpcb/mcp`) generates KiCad files with path variables that do not resolve in KiCad 10.0:

| Asset | JLC MCP Output | Problem | Fix |
|-------|---------------|---------|-----|
| Symbols | `${KIPRJMOD}` in sym-lib-table | KiCad 10.0 doesn't load project sym-lib-table | Embed in `.kicad_sch` via `_inject_jlc_symbols()` |
| Footprints | `${KIPRJMOD}` in fp-lib-table | Same — project fp-lib-table not loaded | Copy to global `%APPDATA%/kicad/10.0/libraries/` |
| 3D Models | `${KICAD9_3RD_PARTY}` in `.kicad_mod` | Variable removed in KiCad 10.0 | Replace with absolute paths via `_fix_3d_model_paths()` |

**Automatic fix**: `install_jlc_mcp_parts.py` (v2) now runs three post-install steps:

1. `_write_project_lib_tables()` — writes sym/fp-lib-tables with **absolute** URIs
2. `_fix_3d_model_paths()` — replaces `${KICAD9_3RD_PARTY}` with absolute 3D model paths
3. `_register_global_libraries()` — copies symbols/footprints/3D models to KiCad global library directory and updates global sym/fp-lib-tables

`run_pipeline.py` automatically invokes `install_jlc_mcp_parts.py --register-only` after schematic generation.

**Manual fix** (if automation fails):
```powershell
python scripts/install_jlc_mcp_parts.py --project-dir <project-dir> --register-only
```

**Verification**:
```powershell
# Check symbols render
kicad-cli sch export svg -o ./preview/ <project>.kicad_sch
# Check global fp-lib-table has JLC-MCP
cat $env:APPDATA/kicad/10.0/fp-lib-table
# Check 3D model paths in footprints
python -c "import re; from pathlib import Path; fp=Path('...kicad_mod'); [print(m.group(1)) for m in re.finditer(r'\(model\s+\"([^\"]+)\"', fp.read_text())]"
```
