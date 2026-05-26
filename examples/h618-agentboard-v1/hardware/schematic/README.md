# Schematic

This folder keeps hand-written schematic planning notes for H618 AgentBoard V1.

## Current work area

- Generated schematic artifacts are written to `../../output/v1/`.
- The KiCad project entry is `../../output/v1/h618_agentboard_v1_initial/`.

## Workflow

- Update the schematic inputs in `docs/18_schematic_module_inputs.md` and related closure docs first.
- Regenerate the project into `../../output/v1/` when the capture order or sheet templates change.
- Treat `../../output/v1/` as the generated working schematic artifact set for the first pass.
- Prefer the EasyEDA/JLC library set copied under the generated KiCad project when replacing placeholder symbols and footprints.
