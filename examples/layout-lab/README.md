# Layout Lab

This directory is a standalone PCB placement sandbox.

It does not call KiCad and it does not touch the main pipeline.
The goal is to visualize how a rule-driven grid placer behaves before
we wire it into production code.

## Model

- Grid: `1mm x 1mm`
- Placement anchor: lower-left corner of the occupied rectangle
- Output: one SVG snapshot per placement step
- Collision handling: occupied-rectangle overlap checks, board margin checks, and keepout checks
- Role definitions live in [roles.json](./roles.json)
- Pattern definitions live in [patterns.json](./patterns.json)
- Scenario definitions live in [scenario.json](./scenario.json)

## Supported patterns

- `center_cluster`
- `boot_reset_cluster`
- `clock_ring`
- `power_entry_chain`
- `power_chain`
- `signal_chain`
- `usb_interface_chain`
- `high_current_path`
- `edge_connector`
- `indicator_cluster`
- `analog_island`
- `rf_keepout_island`
- `rf_island`
- `diff_pair_adjacency`
- `debug_access_cluster`

## Run

```powershell
python scripts/layout_lab.py --scenario examples/layout-lab/scenario.json --out tmp/layout-lab
```

The command writes:

- `tmp/layout-lab/steps/*.svg`
- `tmp/layout-lab/final.svg`
- `tmp/layout-lab/layout-summary.json`
- `tmp/layout-lab/report.md`
- `tmp/layout-lab/steps.html`

To regenerate the three showcase samples and the gallery in one go, run:

```powershell
python scripts/layout_lab_batch.py
```

The batch command also writes:

- `tmp/layout-lab-sample-mcu-core/steps.html`
- `tmp/layout-lab-sample-power-usb/steps.html`
- `tmp/layout-lab-sample-rf-debug/steps.html`
- `tmp/layout-lab-gallery/index.html`

## How It Works

The sandbox now uses a small constraint-based search loop:

1. Convert each component into a grid rectangle.
2. Generate candidate positions from a pattern template.
3. Filter out candidates that violate margin, overlap, or keepout rules.
4. Score the remaining candidates.
5. Recurse through the sequence and backtrack if a later component cannot be placed.
6. Render each successful step as SVG, including explanation text and rejected candidate samples.
7. Store a score breakdown for each chosen candidate in the summary JSON.

This makes the output easy to inspect while keeping the implementation
simple enough to run without external solver dependencies.

## File Roles

`roles.json` defines:

- role defaults
- role slot preferences
- cluster slot order
- board defaults

`patterns.json` defines:

- pattern colors
- template summaries

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the solver and rendering flow.

`rules.json` is kept only as a legacy combined input for compatibility.

`scenario.json` defines:

- board dimensions
- components
- placement patterns for the current board

## Notes

The sandbox is intentionally independent from KiCad export. It is meant
to explain and validate the placement model visually before we wire the
same rules into the production pipeline.
