# Refactoring Design Rules

Use this reference before changing the hardware-development pipeline, KiCad generator, layout logic, symbol handling, scripts, or skill-facing commands.

## Core Rule

Optimize the reusable hardware-development resource base, not only the current board. If a change is useful only because the active demo is RP2040, ESP32, USB, or another specific topology, put that knowledge into a data/config/resource layer or a named profile instead of embedding it in Python control flow.

## Preferred Locations

- Product code: `src/kicad_suite/`
- Thin compatibility entrypoints: `scripts/`
- Symbol and footprint mapping data: `config/kicad-symbol-map.json`
- Layout defaults and board/topology placement profiles: `config/kicad-layout-profiles.json`
- Local KiCad symbols: `resources/kicad/symbols/*.kicad_sym`
- Example circuit models: `examples/*.circuit-model.json`
- Skill guidance for agent behavior: `skills/kicad-agent-suite-skill/references/`
- Temporary generated projects: `tmp/` or `.where/kicad-output/`, not committed unless explicitly requested

## Design Rules

- Do not add project-specific `if role == ...` or `if topology == ...` branches when the same behavior can be expressed as config, a profile, or a KiCad resource.
- Do not duplicate pin coordinates in code when they can be parsed from KiCad symbols.
- Do not maintain a second hidden truth for nets, pins, or symbols. `Netlist` owns electrical connectivity; KiCad symbols own pin geometry; config owns mapping policy.
- Keep `scripts/` as wrappers only. Put reusable implementation in `src/kicad_suite/`.
- Prefer schema-shaped JSON and KiCad-native files over ad hoc strings.
- Keep placeholder symbols clearly named as placeholders and replace them with verified KiCad library symbols when available.
- If a script grows business logic, move it into a package module and leave a compatibility wrapper.
- When adding support for a new MCU/module, first ask whether it belongs in the symbol map, local symbol library, layout profile, or circuit model example.

## Refactoring Checklist

- Identify whether the change is mapping, resource, layout, connectivity, simulation, or command orchestration.
- Move static knowledge to `config/` or `resources/` before adding code.
- Make code read the data source generically.
- Preserve existing command compatibility unless intentionally changing CLI behavior.
- Regenerate a representative KiCad project after structural changes.
- Run `python -m py_compile` on package and wrappers.
- Run `npm run ngspice:regression` when circuit pipeline or simulation feedback changes.
- Run `npm run compile-plan` and `npm run write-project` or equivalent direct commands when KiCad generation changes.

## Acceptable Hardcoding

Hardcoding is acceptable only for stable format constants, schema versions, fallback defaults, and compatibility wrapper names. Even then, prefer documenting why the value is stable.

## Warning Signs

- The code mentions a board name, chip family, or demo topology in generator logic.
- A new feature requires editing multiple coordinate tables.
- A symbol's pins are described both in `.kicad_sym` and Python.
- A temporary path becomes part of normal operation.
- A fix only works for one example and cannot explain how another board would use it.
