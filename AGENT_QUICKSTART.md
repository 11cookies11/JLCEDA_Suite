# KiCad Agent Suite Quick Start

This package is built for agents that need to inspect, modify, validate, or export hardware designs.

## Start Here

1. Treat `source/circuit-model.source.json` as the human-authored source of truth.
2. Treat `build/circuit-model.resolved.json` as the toolchain-derived overlay.
3. Set `KICAD_WORKSPACE` to the project root when working on a project.
4. Prefer the stable CLI entrypoints:
   - `python scripts/kas.py pipeline <source/circuit-model.source.json> <output-dir>`
   - `hwtool agent resolve-symbols --project <project-dir>`
   - `python scripts/kas.py validate-artifacts --summary <summary.json>`
   - `python scripts/kas.py erc`

## Model Fields

- `ref`: stable schematic reference, such as `U1` or `R3`
- `role`: functional purpose
- `value`: human-readable component value or description
- `search_hints`: search terms that help part selection
- `selected_part.lcsc_id`: real LCSC identifier used for downloads
- `selected_part.symbol_ref`: exact symbol name used for export
- `selected_part.kicad_footprint_hint`: exact footprint name used for export

## Directory Layout

```text
<project-root>/
├── source/
│   └── circuit-model.source.json
├── build/
│   └── circuit-model.resolved.json
├── libraries/
└── output/
```

## Practical Rules

- Do not treat `display_name` as a stable export key.
- Re-run `resolve-symbols` after changing part choices.
- Re-run `build-ir` and `export-kicad` after changing the source model.
- Review validation and ERC results before shipping a design.

## If Something Looks Wrong

- Missing or wrong symbols usually mean the part resolution step needs to run again.
- Missing footprints usually mean the resolved part needs a better `kicad_footprint_hint`.
- A root-level single-file model is legacy behavior; new work should use the split source/build layout.
