# ESP32-C3 Minimal System

Verified example for the current KiCad Agent Suite project protocol.

This project models an ESP32-C3 minimum system board with 5 V input, 3.3 V
regulation, USB-C power and data, boot and reset controls, status LED, and GPIO
expansion headers.

## Source Of Truth

Edit this file only:

```text
source/circuit-model.source.json
```

Generated files are kept for inspection and KiCad handoff:

```text
output/esp32c3_minimal_system/
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

- `build-ir`: 17 components, 8 nets
- `validate-ir`: ok, 0 errors, 0 warnings
- `export-kicad`: generated schematic, PCB, ERC, and report artifacts
- `diagnose`: no must-fix issues

