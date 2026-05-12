# Legacy — JLCEDA Suite

Files in this directory are JLCEDA-specific and are not needed for KiCad operation.

## jlceda-scripts/

JLCEDA IDE Python scripts:

- `compile_execution_plan.py` — Duplicate of inline logic in `server_text_to_schematic.py`. Dead code.
- `server_placement_multipage_test.py` — JLCEDA bridge placement integration test.
- `schematic_connectivity_diagnostics.py` — JLCEDA source-format connectivity analysis.
- `package-release-bundle.py` — JLCEDA `.eext` plugin bundling.

## schemas/

- `execution-plan.v1.json` — JLCEDA execution plan schema. Superseded by `kicad-execution-plan.v1.json`.

## jlceda-plugin/

Reserved for the JLCEDA TypeScript plugin layer (`src/` + `scripts/*.ts`) when JLCEDA IDE support is fully deprecated.
