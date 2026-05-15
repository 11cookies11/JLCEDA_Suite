---
name: kicad-suite-skill
description: Help an AI agent use this repository's reusable hardware-development resources to design, validate, and improve circuit projects. Use when working from requirements to circuit models, netlists, simulation feedback, KiCad schematic/project generation, symbol/layout resources, LCSC part selection, EasyEDA footprint import, or refactoring the hardware agent pipeline for better generality without hardcoded project-specific logic.
---

# Hardware Development Skill

## When to use

Use this skill when the user wants an AI agent to use repository resources to produce, inspect, validate, or improve hardware design artifacts.

The active implementation target is KiCad, but the skill's purpose is broader: use structured requirements, circuit models, netlists, reusable component knowledge, simulation feedback, symbol resources, layout profiles, and validation tools as a hardware-development workspace.

The current workflow is:

- clarify electrical requirements before synthesis
- convert requirements into a typed `RequirementSpec`
- synthesize a `CircuitModel`
- derive connection truth as `Netlist`
- export a SPICE netlist and collect ngspice feedback
- **run LCSC Resolver → Part Selector to choose real components**
- **import EasyEDA footprints via easyeda2kicad**
- **generate part.lock.yaml and part-risk-report.md**
- compile a `KiCadExecutionPlan`
- write `.kicad_pro` and `.kicad_sch` files (with LCSC/MPN/Manufacturer fields)
- optionally run `kicad-cli` ERC

Legacy EasyEDA/JLCEDA live-session bridge flows are archived under `legacy/` and should not be used for new work.

## Default Workflow

1. Read the user's design intent and identify missing electrical constraints.
2. If the requirement is underspecified, clarify input source, outputs, current, interfaces, packages, and acceptance checks.
3. Build or normalize `BRIDGE_REQUIREMENT_SPEC_JSON`.
4. Run the KiCad pipeline with `npm run text-to-kicad` or `python scripts/run_pipeline.py`.
5. **If real LCSC parts are needed, enable `KICAD_PARTS_PIPELINE=true` to generate part.lock.yaml and part-risk-report.md.**
6. **To import EasyEDA symbols/footprints/3D models, run `python scripts/import_jlc_parts.py <circuit-model.json> <project-dir>`.**
7. Review generated model, netlist, ngspice feedback, KiCad execution plan, part lock file, and risk report.
8. Run `npm run ngspice:regression` or `npm run erc` when relevant.
9. When code or pipeline gaps appear, improve the reusable hardware-development resources rather than patching only the current board.
10. Report generated files, diagnostics, part selection summary, and next modeling, mapping, validation, or resource-improvement tasks.

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
| LCSC Resolver | `src/kicad_suite/lcsc_resolver.py` | Search LCSC + EasyEDA for parts by MPN/function/package |
| Part Selector | `src/kicad_suite/part_selector.py` | Multi-factor scoring (MPN/package/Basic/stock/price/library), risk assessment, final selection |
| Parts Pipeline | `src/kicad_suite/parts_pipeline.py` | Integration: resolve → select → lock file → risk report |
| KiCad Lib Importer | `src/kicad_suite/kicad_lib_importer.py` | Run easyeda2kicad subprocess, generate part.lock.yaml, build risk report |

### Env Vars

| Variable | Purpose |
|----------|---------|
| `KICAD_PARTS_PIPELINE=true` | Enable parts pipeline in server_text_to_kicad / run_pipeline |
| `KICAD_PARTS_IMPORT=true` | Also run easyeda2kicad import (requires tool installed) |
| `EASYEDA2KICAD_BIN` | Path to easyeda2kicad executable |
| `KICAD_SYMBOL_MAP_FILE` | Override symbol map (e.g., project-specific JLC map) |
| `KICAD_EXTRA_FOOTPRINT_DIR` | Additional footprint search paths |

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

- `npm run text-to-kicad`: end-to-end RequirementSpec to KiCad output
- `npm run pipeline`: same KiCad target through the generic entry
- `npm run compile-plan`: compile CircuitModel and Netlist into KiCadExecutionPlan
- `npm run write-project`: write KiCad project files from an execution plan
- `npm run erc`: run KiCad ERC when `kicad-cli` and input paths are available
- `npm run ngspice:regression`: run ngspice feedback regression fixtures

### Parts Commands

- `python scripts/resolve_parts.py`: test LCSC Resolver with built-in demo
- `python scripts/select_parts.py`: test Part Selector with built-in demo
- `python scripts/import_parts.py --selections selections.json --project-dir ./project`: import parts to project
- `python scripts/import_jlc_parts.py <circuit-model.json> <project-dir> [--delay 3.0]`: import all LCSC parts from a circuit model
- `python scripts/demo_parts_pipeline.py`: end-to-end parts pipeline demo
- `python scripts/demo_e2e_pipeline.py`: full pipeline demo with KiCad output
- `python scripts/run_pipeline.py <circuit-model.json> <output-dir>`: run full KiCad pipeline from existing circuit model

### `scripts/server-text-to-schematic.mjs`

Compatibility wrapper for older skill callers. It now invokes:

- `src/kicad_suite/server_text_to_kicad.py`; the compatibility entry remains at `scripts/server_text_to_kicad.py`

Prefer the root command `npm run text-to-kicad` for new work.

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
- `text-to-kicad-summary.json`

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
- Use ngspice feedback to surface verification risk, not to silently accept a design.
- Use KiCad ERC as an additional check after file generation.
- Keep EasyEDA/JLCEDA references confined to `legacy/`.

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
