# Text To Schematic Workflow

This workflow implements the model-driven chain:

`RequirementSpec -> CircuitModel -> ExecutionPlan -> (optional) Execute`

Before the `CircuitModel` step, the agent should normalize the user-facing theory circuit into SCD, the strict textual schematic construction format described in [schematic-construction-description.md](schematic-construction-description.md).

## Input Contract

- `BRIDGE_REQUIREMENT_SPEC_JSON`
- `BRIDGE_COMPONENT_CATALOG_JSON`
- `BRIDGE_EXECUTE_PLAN`

Requirement payload should include:
- `schema_version=requirement-spec.v1`
- `goal`
- `electrical_targets`

If the user's requirement is still underspecified, the pipeline should stop at clarification and not synthesize SCD yet.

When the user wants a readable circuit description, the preferred intermediate output is SCD, not free-form prose.

## Output Artifacts

The pipeline writes:
- `requirement-spec.json`
- `schematic-construction-description.md` when the readable theory schematic view is requested
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

- Treat incomplete prompts as requirement clarification tasks first, not schematic generation tasks.
- If the requirement is still evolving, ask whether the requirement is finalized before moving into SCD generation.
- Preferred clarification phrasing: "需求现在已经定稿了吗？如果还没有，我先帮你把需求补完整，再进入原理图构建。"
- Treat SCD as the canonical human-readable representation of the theory schematic.
- Prefer candidates with verified `library_uuid`, `symbol_uuid`, and `pin_count > 0`.
- Do not continue automatic wiring when pin geometry is missing.

## Reference set

Use these companion references while working in this mode:

- [requirement-clarification.md](requirement-clarification.md)
- [strap-and-bias-rules.md](strap-and-bias-rules.md)
- [netlist-guidelines.md](netlist-guidelines.md)
- [simulation-guidelines.md](simulation-guidelines.md)
- [decision-log-template.md](decision-log-template.md)
- Keep `design_decisions[]` updated when switching candidates or topology assumptions.
