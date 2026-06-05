# Layout Lab Architecture

This sandbox is a standalone placement playground for PCB component layout.
It intentionally does not call KiCad and does not depend on the main export
pipeline.

## Goals

- Make PCB placement rules visible.
- Keep placement logic deterministic and explainable.
- Separate the rule vocabulary from the scenario data.
- Show why a candidate was accepted or rejected.

## Layers

### 1. Rule layer

These files define the vocabulary and reusable templates:

- `roles.json`
  - role defaults
  - preferred slots
  - board defaults
- `patterns.json`
  - pattern summaries
  - pattern colors
  - template defaults

### 2. Scenario layer

`scenario.json` contains only board-specific input:

- board size
- component rectangles
- pattern membership

### 3. Solver layer

`scripts/layout_lab.py` does the work:

- converts components into grid rectangles
- generates candidate positions
- filters candidates against board margins, overlaps, and keepouts
- scores the surviving candidates
- records a score breakdown for each selected candidate
- recurses through the pattern order and backtracks if a later component fails
- records the selected candidate, rejected summary, and rejected samples

### 4. Visualization layer

Each successful step produces:

- a step SVG
- a final SVG
- a summary JSON file
- a markdown report

The SVG includes:

- the board grid
- placed components
- relation arrows
- explanation text
- failed candidate samples

## Placement Model

- Grid size: `1mm x 1mm`
- Placement anchor: lower-left corner of the occupied rectangle
- Occupancy model: rectangle overlap
- Validation model: board margin + existing placements + keepout rectangles

## Why This Design

The sandbox is intentionally smaller than a full PCB autorouter.
It is meant to act as a reasoning aid for the agent:

- the agent can see layout intent
- the solver can keep the rules consistent
- the visualization can explain the final decision

## Current Status

The first and second sandbox stages are both implemented:

- stage 1: standalone rule-driven sandbox with explainable SVG output
- stage 2: constraint-style candidate search with rejected-candidate reporting

The next step, if desired, is to connect the same placement concepts to the
main KiCad pipeline through a dedicated placement planner service.
