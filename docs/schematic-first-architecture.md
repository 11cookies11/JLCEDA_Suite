# Schematic-First Architecture

## Goal

Build a usable developer version that lets Codex and the user iteratively produce high-quality schematics first, then hand them to JLCEDA for PCB transfer, auto placement, and auto routing.

The system should be:

- usable
- stable
- configurable
- able to improve over time without rewriting code for every rule tweak

## Core Principle

The system should not duplicate JLCEDA capabilities when JLCEDA already provides them.

Instead:

- reuse native JLCEDA features first
- add policy/configuration for project preferences
- implement fallback heuristics only where native behavior is missing or insufficient

## Responsibility Split

### Codex

Codex owns the high-level decision making:

- choose the task strategy
- decide which workflow to use
- interpret the output of checks and suggestions
- request follow-up operations

### Server

The Python server is the control plane and rules brain:

- command orchestration
- heuristic evaluation
- layout suggestions
- profile loading
- result normalization
- fallback rule computation

The server should be allowed to do more than transport.

### Plugin

The plugin is the execution plane inside JLCEDA:

- read the actual document state
- call `eda.*`
- place parts
- draw wires
- import changes
- save documents
- return the real runtime result

### Native JLCEDA

Native JLCEDA behavior should be preferred for:

- schematic to PCB transfer
- auto layout
- auto routing
- DRC
- document import/save
- library and footprint access

## Design Layers

### 1. Hard Constraints

These are safety boundaries and should stay in code.

Examples:

- wire endpoints must connect to pins
- components must not overlap
- PCB components must not be too close to board edges
- silk should not collide with pads

### 2. Profiles

These are configurable engineering preferences.

Examples:

- spacing thresholds
- label clearance
- power block arrangement style
- preferred board-edge conservatism
- component grouping weights

Profiles should be project-specific when needed.

### 3. Fallback Heuristics

Fallbacks are used when native JLCEDA support is missing or too weak.

Examples:

- label crowding suggestions
- power block placement guidance
- placement avoidance for schematic parts
- PCB placement hygiene checks

## Schematic-First Workflow

### Step 1: Generate or load schematic

The system should build a schematic that is:

- connected correctly
- readable
- organized into blocks
- minimal in overlap and clutter

### Step 2: Run schematic checks

Checks should cover:

- connectivity
- layout hygiene
- label hygiene
- power block guidance

### Step 3: Apply minimal fixes

Only apply changes that improve correctness or reduce obvious clutter.

Avoid adding complex style rules too early.

### Step 4: Hand off to native JLCEDA

Let JLCEDA handle:

- schematic to PCB transfer
- PCB auto placement
- PCB auto routing
- DRC

### Step 5: Review and iterate

The system should capture human edits and turn them into the next profile revision.

## What We Should Avoid

- hardcoding every preference as code
- reimplementing JLCEDA-native behavior
- adding low-value special cases too early
- building a full PCB optimizer before schematic quality is stable

## Development Strategy

### Phase 1: Usable

Ship a developer version that can:

- create and edit schematic reliably
- avoid obvious wire/component/label collisions
- validate connectivity
- keep the workflow stable

### Phase 2: Configurable

Add:

- profiles
- rule parameters
- project overrides
- recommendation tuning

### Phase 3: Adaptive

Add feedback loops:

- record human fixes
- adjust defaults
- learn project-specific preferences

## Plugin Freeze Policy

The plugin should be treated as a stable execution layer once a baseline release is working.

Default policy:

- prefer changing server profiles, rules, and orchestration first
- avoid touching the plugin unless JLCEDA runtime behavior changes or a plugin bug blocks execution
- keep plugin releases infrequent and capability-driven

This lets the team iterate on behavior without forcing constant plugin reinstallation.

## Recommended Initial Scope

Focus on:

- schematic connectivity
- schematic placement hygiene
- label hygiene
- power block ordering and guidance
- minimal PCB hygiene checks

Defer:

- deep PCB auto-optimization
- low-frequency aesthetic rules
- custom reimplementation of JLCEDA native algorithms

## Summary

This architecture is a controlled, schematic-first, schema-driven workflow:

- Codex decides
- Server reasons and coordinates
- Plugin executes in JLCEDA
- Native JLCEDA features are reused first
- Custom rules are configurable, not permanently hardcoded
