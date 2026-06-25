# KiCad Agent Suite

Agent-assisted KiCad hardware development pipeline.

KiCad Agent Suite uses a structured source model to resolve parts, compile an
intermediate representation, validate it, and export KiCad projects.

## Software Architecture

The suite is organized as a layered toolchain. AI agents and humans edit a
structured circuit model, then the toolchain derives build artifacts, validation
reports, and KiCad output from that source.

```text
AI agent / human
  |
  v
CLI and agent entrypoints
  src/kicad_suite/cli.py
  src/kicad_suite/entrypoints/
  |
  v
Orchestration layer
  src/kicad_suite/orchestration/
  - workflow templates, task routing, pipeline coordination, post-processing
  |
  v
Application services
  src/kicad_suite/application_services/
  - project state, diagnostics, reports, part resolution, semantic gates
  |
  v
Domain core
  src/kicad_suite/domain/core/
  - circuit model IO, IR compiler, IR validator, netlist, simulation plan,
    pin management, KiCad execution plan
  |
  v
Adapters
  src/kicad_suite/adapters/
  - KiCad writers/runners, PCB generation, JLC/LCSC/EasyEDA, symbol and
    footprint resolution
  |
  v
Generated build/output artifacts
```

### Main Data Flow

```text
source/circuit-model.source.json
  -> resolve parts and project-local libraries
  -> build/circuit-model.resolved.json
  -> build/ir.v1.json
  -> build/ir-validation.json
  -> hardware semantic gate artifacts
     build/net-intents.v1.json
     build/pin-contracts.v1.json
     build/hardware-erc.v1.json
     build/export-gate.v1.json
  -> output/<topology>/*.kicad_*
  -> ERC classification and agent reports
  -> build/report.json and build/report.md
```

`source/circuit-model.source.json` is the only authoritative project model for
new projects. `build/` and `output/` are generated views of that source.

### Agent-Facing API

The stable agent entrypoint is:

```powershell
hwtool agent manifest
```

The `agent` command group exposes machine-readable lifecycle operations:

- `status`, `inspect`, `explain`, `diagnose`, `report`
- `build-ir`, `validate-ir`, `resolve-symbols`, `export-kicad`
- `run` and `patch` for controlled model edits through the Model API
- `workflow` for template-driven multi-step tasks
- `pins` for pin resource checks and assignments
- `jlc` for LCSC search, preview, and project-local downloads
- `semantic-gates` for listing, validating, proposing, and accepting semantic
  gate rules

Agents should prefer these commands over direct writes to generated artifacts.

### Validation and Gate Layers

The repository uses several validation layers with different responsibilities:

- IR validation checks structural correctness before KiCad export.
- Circuit sanity checks catch shorts, floating pins, and suspicious passives.
- Hardware semantic gates catch topology-level mistakes before export, such as
  missing USB-C CC pull-downs or unsafe power-path wiring.
- KiCad ERC runs on exported KiCad projects and is classified into agent-readable
  findings.
- Semantic gate proposals can be generated from hardware ERC findings and stored
  as reviewable project knowledge.

Semantic gate files live in:

```text
build/proposed-semantic-gates/*.gate.json   # generated review queue
source/semantic-gates/*.gate.json           # accepted project rules
resources/hardware-rules/builtin/           # reserved built-in rules
resources/hardware-rules/promoted/          # reserved promoted rules
```

### Source Tree Responsibilities

- `src/kicad_suite/cli.py`: command-line and agent command dispatch.
- `src/kicad_suite/domain/core/`: pure model compilation, validation, planning,
  and pin/resource logic.
- `src/kicad_suite/application_services/`: project-level services that combine
  domain logic with filesystem state, reports, diagnostics, and rule registries.
- `src/kicad_suite/orchestration/`: workflow templates, agent task generation,
  pipeline event logs, and build coordination.
- `src/kicad_suite/adapters/`: integrations with KiCad files/tools,
  EasyEDA/JLC/LCSC, symbol libraries, and PCB writers.
- `schemas/`: JSON schemas for source models, IR, API requests/results, reports,
  semantic gates, and generated sidecar artifacts.
- `scripts/`: standalone utility scripts, including the hardware semantic gate.
- `tests/`: regression tests for CLI commands, schemas, model APIs, semantic
  gates, KiCad generation, and fixture behavior.

## Project Layout

New projects use the split source/build layout:

```text
project/
  source/
    circuit-model.source.json
  build/
    circuit-model.resolved.json
    ir.v1.json
    ir-validation.json
    report.json
    report.md
  libraries/
    symbols/
    footprints/
    3dmodels/
  output/
    <topology>/
      <topology>.kicad_pro
      <topology>.kicad_sch
      <topology>.kicad_pcb
      <topology>.erc.json
      <topology>.erc.classification.json
      agent-report.json
```

Edit `source/circuit-model.source.json`. Treat `build/`, `output/`, logs, and
`project.state.json` as generated artifacts.

## Common Workflow

Run commands from a project directory:

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent diagnose --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown
hwtool agent diagnose --project .
```

Do not export KiCad before IR validation passes.

## Examples

Editable example source models live under `examples/*/source/`.

- `examples/stm32f103-minimal-system/source/circuit-model.source.json`
- `examples/esp32c3-minimal-system/source/circuit-model.source.json`
- `examples/refactor-layout-demo/source/circuit-model.source.json`
- `examples/h618-agentboard-v1/source/circuit-model.source.json`

Generated example `build/`, `output/`, and downloaded project-local libraries are
not tracked in git. Regenerate them with the workflow above when needed.

## Development

Useful commands:

```powershell
python scripts/kas.py --help
python -m pytest
npm run jlc:search -- STM32F103C8T6
```

Repository-wide KiCad resource libraries live in `resources/kicad/`.
