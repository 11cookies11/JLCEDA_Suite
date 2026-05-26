# Schematic

This folder holds the KiCad schematic work products for H618 AgentBoard V1.

## Current work area

- `initial/` contains the first generated KiCad project skeleton for the high-priority sheets.
- `initial/libraries/` contains the copied EasyEDA/JLC local symbol, footprint, and 3D asset set.

## Workflow

- Update the schematic inputs in `docs/18_schematic_module_inputs.md` and related closure docs first.
- Regenerate the project into `initial/` when the capture order or sheet templates change.
- Treat the generated files here as the working schematic artifact set for the first pass.
- Prefer the EasyEDA/JLC library set in `initial/libraries/` when replacing placeholder symbols and footprints.
