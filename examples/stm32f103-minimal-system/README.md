# STM32F103 Minimal System

Verified example for the current KiCad Agent Suite project protocol.

This project models a compact STM32F103C8T6 minimum system board with power input,
3.3 V regulation, reset and boot straps, SWD programming, USB, user LED, and board
edge expansion headers.

## Source Of Truth

Edit this file only:

```text
source/circuit-model.source.json
```

Generated files are kept for inspection and KiCad handoff:

```text
output/stm32f103_minimal_system/
```

Do not edit generated `build/`, `output/`, or `project.state.json` files manually.

## Rebuild

Run from this example directory:

```powershell
hwtool agent status --project .
hwtool agent inspect --project .
hwtool agent resolve-symbols --project . --timeout 120
hwtool agent build-ir --project .
hwtool agent validate-ir --project .
hwtool agent export-kicad --project .
hwtool agent report --project . --markdown
hwtool agent diagnose --project .
```

## Current Verification

- `build-ir`: 18 components, 10 nets
- `validate-ir`: ok, 0 errors, 0 warnings
- `export-kicad`: generated schematic, PCB, ERC, and report artifacts
- `diagnose`: no must-fix issues

