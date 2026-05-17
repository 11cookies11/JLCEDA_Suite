# CLAUDE.md — KiCad Agent Suite

## What this project does

Generates complete KiCad projects from structured hardware descriptions.
Input: `circuit-model.json` + JLC-MCP parts library.
Output: `.kicad_pro`, `.kicad_sch`, `.kicad_pcb` with ERC validation.

## Project structure

```
src/kicad_suite/           ← core pipeline code
  compile_kicad_execution_plan.py  ← symbol mapping, layout, lib validation
  kicad_project_writer.py          ← schematic/PCB generation
  pipeline_coordinator.py          ← full pipeline orchestration
  pipeline_postprocess.py          ← lib sync, symbol injection, pin fixes
  schematic_layout_rules.py        ← block/pitch/spacing defaults
config/kicad-layout-profiles.json ← per-project layout: roles, blocks, sheet groups
examples/nexdap-.../              ← reference project with circuit-model.json
```

## Pipeline workflow (non-linear, iterative)

```
circuit-model.json + JLC libs → compile_plan() → write_project() → postprocess → ERC
                        ↑                              │
                        └── feedback loops ────────────┘
```

Key principle: each stage produces versionable JSON (plan, summary, ERC report).
Changes to earlier stages just re-run the pipeline — no manual file surgery.

## Critical: workspace mode (do NOT use scattered .where/ paths)

Set ONE env var:
```powershell
$env:KICAD_WORKSPACE = "D:/path/to/project"
```

Workspace layout:
```
project/
├── circuit-model.json
├── libraries/symbols/    ← .kicad_sym files (JLC-MCP etc.)
├── libraries/footprints/ ← .pretty/ directories
├── libraries/3dmodels/   ← .step files
└── output/               ← auto-generated, do NOT commit manually
```

If KICAD_WORKSPACE is not set, the pipeline auto-detects it from `circuit-model.json`'s parent directory.

## Critical gotchas (cost weeks to debug)

1. **Fake 2-pin fallback** — if `kicad_symbol_roots()` can't find a JLC library file, `symbol_block_for_lib_id()` silently returns a fake 2-pin symbol with pins at ±5.08mm. This causes `pin_not_connected` × hundreds. The pre-flight check `_validate_symbol_libraries()` now catches this before generation and raises a clear error listing which libraries are missing.

2. **NaN arcs in JLC-MCP symbols** — some JLC-MCP `.kicad_sym` files contain `<arc (mid NaN NaN)>`. This crashes KiCad GUI loading. Fixed: `sanitize_symbol_block()` removes them. If you see NaN again, run it through that function.

3. **sym-lib-table / fp-lib-table paths** — if KiCad can't find libraries, check these files first. In workspace mode they auto-point to `workspace/output/{project}/libraries/`. If symbols still fail, verify the actual `.kicad_sym` files exist at the expected paths.

4. **Don't reuse old execution plans** — v13's issues came from reusing a pre-compiled JSON plan. Always regenerate from `circuit-model.json` using `compile_plan()` to get current symbol mappings and layout.

5. **Don't hand-edit generated .kicad_sch** — if you need to fix wire positions or pin types, fix the generator code, not the output files. Exception: one-off post-generation patches like pin type regex fixes (`bidirectional→power_in`).

## Common ERC patterns and what they mean

| ERC type | Likely cause | Fix |
|----------|-------------|-----|
| `pin_not_connected` × many | JLC lib not found → fake 2-pin symbols | Check `KICAD_WORKSPACE`, verify `libraries/symbols/` |
| `multiple_net_names` | Different labels shorted by single wire segment | Check circuit-model.json net members |
| `pin_to_pin` (bidirectional↔power_out) | RP2040/ESP32 power pins typed wrong | Pin type fix in pipeline_postprocess or symbol library |
| `lib_symbol_mismatch` × many | Embedded symbols out of sync with library | Run "Update Symbols from Library" in KiCad GUI |
| `label_dangling` | Global label not connected to any net | Usually cascading from pin_not_connected |

## Key generator functions (for debugging)

- `parse_symbol_pin_map(lib_id)` — reads pin positions from .kicad_sym library file, returns dict of pin_number→{x,y,rotation,length}. If returns ≤2 pins for a JLC-MCP symbol, the library file is not found.
- `pin_endpoint(symbol, pin_number)` — returns (x, y, direction) of the pin tip (electrical connection point). Wire MUST start exactly here.
- `endpoint_from_pin(pin_data, origin, rotation)` — transforms local pin offset to absolute coordinates with rotation.
- `render_connectivity(plan, symbols)` — generates all wires and labels. Wire goes from pin tip → stub → label.

## Running the pipeline

```powershell
# Full pipeline from workspace
$env:KICAD_WORKSPACE = "D:/path/to/project"
python -m kicad_suite.pipeline_coordinator circuit-model.json output/

# Or via npm
npm run pipeline
```

## Running ERC standalone

```powershell
& "D:/Program Files/KiCad/10.0/bin/kicad-cli.exe" sch erc `
  --format json --output erc.json `
  project.kicad_sch
```

The CLI and GUI ERC may produce different results — the CLI is the authoritative source.
CLI reading JSON: `d["sheets"][i]["violations"]` → list of {severity, type, description, items}.
