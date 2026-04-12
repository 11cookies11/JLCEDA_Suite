# Text To Schematic Workflow

This workflow implements the model-driven chain:

`RequirementSpec -> CircuitModel -> ExecutionPlan -> (optional) Execute`

## Input Contract

- `BRIDGE_REQUIREMENT_SPEC_JSON`
- `BRIDGE_COMPONENT_CATALOG_JSON`
- `BRIDGE_EXECUTE_PLAN`

Requirement payload should include:
- `schema_version=requirement-spec.v1`
- `goal`
- `electrical_targets`

## Output Artifacts

The pipeline writes:
- `requirement-spec.json`
- `circuit-model.json`
- `execution-plan.json`
- `pipeline-summary.json`

Default output root:
- `.where/pipeline-output/<request-id>/`

## Fallback Rules

The generated execution plan includes standard fallback triggers:
- `PART_UNAVAILABLE`
- `PIN_MISSING`
- `WIRE_FAILED`
- `EXECUTION_FAILED`

Use these signals to let the AI agent:
- switch to backup candidates
- ask for pin-verified symbols
- keep labels and request manual wire confirmation

## Practical Notes

- Prefer candidates with verified `library_uuid`, `symbol_uuid`, and `pin_count > 0`.
- Do not continue automatic wiring when pin geometry is missing.
- Keep `design_decisions[]` updated when switching candidates or topology assumptions.
