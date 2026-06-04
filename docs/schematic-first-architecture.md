# KiCad-First Architecture

## Goal

Build a usable developer pipeline that lets Codex and the user iteratively produce high-quality KiCad schematics from structured requirements.

The system should be:

- file-based
- repeatable
- schema-driven
- simulation-aware
- able to improve without rewriting every rule as code

## Core Principle

KiCad is the only active EDA target.

The pipeline should generate clear intermediate artifacts before writing KiCad files:

- `RequirementSpec` captures design intent
- `CircuitModel` captures selected topology, parts, risks, and decisions
- `Netlist` captures electrical connection truth
- `SPICE Netlist` captures simulation input
- `KiCadExecutionPlan` captures schematic file generation intent

## Responsibility Split

### Codex

Codex owns high-level decision making:

- clarify incomplete requirements
- choose the workflow
- interpret diagnostics and simulation feedback
- decide the next model or mapping improvement

### Python Pipeline

The Python pipeline owns transformation and validation:

- requirement normalization
- circuit model synthesis
- part role mapping
- netlist generation
- SPICE export
- ngspice execution and feedback
- KiCad execution plan compilation
- KiCad project and schematic writing

### KiCad

KiCad owns downstream EDA validation and editing:

- schematic review
- ERC through `kicad-cli`
- manual or future scripted refinement
- PCB work after schematic quality is acceptable

## Design Layers

### 1. Hard Constraints

These are safety boundaries and should stay in code.

Examples:

- netlist members must resolve to component pins
- ground and power nets must be classified consistently
- unsupported SPICE exports must be explicit
- placeholder KiCad symbols must be reported in diagnostics

### 2. Profiles and Rules

These are configurable engineering preferences.

Examples:

- block placement order
- spacing thresholds
- symbol dimensions
- preferred role-to-library mappings
- net label style

### 3. Fallback Heuristics

Fallbacks are used when verified library metadata is missing.

Examples:

- local placeholder symbols
- estimated symbol sizes
- conservative schematic layout positions
- diagnostics that name missing mappings

## Schematic-First Workflow

### Step 1: Normalize Requirements

Capture enough electrical intent before synthesis:

- input source
- output rails
- current limits
- interfaces
- package or procurement constraints
- acceptance criteria

### Step 2: Build Circuit and Netlist Models

Generate:

- `source/circuit-model.source.json`
- `netlist.json`
- design decisions
- model risks

### Step 3: Simulate Where Possible

Generate SPICE artifacts and run ngspice when available:

- `spice-netlist.cir`
- `ngspice-execution.json`
- `ngspice-feedback.json`

Simulation feedback should update risk, not hide uncertainty.

### Step 4: Write KiCad Files

Compile `kicad-execution-plan.json`, then write:

- `<project_name>.kicad_pro`
- `<project_name>.kicad_sch`
- `kicad-write-summary.json`

### Step 5: Run ERC and Iterate

Use `kicad-cli` ERC when available. Feed diagnostics back into:

- role mapping
- pin mapping
- netlist generation
- schematic layout rules
- regression fixtures

## What We Should Avoid

- adding new EasyEDA/JLCEDA GUI bridge behavior
- hiding placeholder symbols as if they were verified library parts
- mixing layout concerns into `Netlist`
- accepting a circuit solely because file generation succeeded
- making GUI automation a dependency for the core pipeline

## Development Strategy

### Phase 1: Reliable Files

Ship deterministic KiCad project and schematic generation with clear diagnostics.

### Phase 2: Better Mappings

Add verified KiCad symbol and footprint mappings for common components.

### Phase 3: Stronger Validation

Expand ngspice fixtures, ERC parsing, and regression coverage.

### Phase 4: PCB Handoff

After schematic generation is stable, add PCB-oriented handoff artifacts and checks.

## Summary

This architecture is a KiCad-first, schema-driven workflow:

- Codex clarifies and decides
- Python transforms and validates
- ngspice checks electrical behavior where possible
- KiCad receives generated project files
- historical EasyEDA/JLCEDA GUI bridge code is no longer part of this repository
