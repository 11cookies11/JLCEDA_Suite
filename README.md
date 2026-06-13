# KiCad Agent Suite

Agent-assisted KiCad hardware development pipeline.

KiCad Agent Suite uses a structured source model to resolve parts, compile an
intermediate representation, validate it, and export KiCad projects.

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
