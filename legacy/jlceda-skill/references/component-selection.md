# JLCEDA Suite Component Selection

This reference describes the preferred workflow for component selection in the JLCEDA Suite skill.

## Goal

Help the user choose a component that fits the current schematic block, then leave enough information for the next schematic change.

## Inputs

Capture these before comparing parts:

- role in the circuit
- function block or sheet name
- minimum voltage and current requirements
- verified pin information for the library symbol when the part must be wired directly
- tolerance or precision requirement when relevant
- preferred or required package
- cost ceiling
- manufacturer preference if any
- availability priority

## Workflow

1. Read the current schematic context.
2. Restate the requirements in a compact structured form.
3. Filter out candidates whose symbol pin geometry is not verified.
4. Compare the remaining candidate parts against the requirements.
5. Pick the best-fit part and explain why it wins.
6. Record a BOM-style note.
7. Name the verification checks before schematic placement or replacement.

## Good output shape

A good component-selection result should include:

- normalized requirement summary
- pin-info verification status
- ranked candidate comparison
- explicit recommendation
- risk list for the chosen part
- BOM note
- verification checklist
- next schematic actions

## Search-first mode

When the user has not given candidate parts yet:

- derive search keywords from role, function block, package, manufacturer preference, and pin-info needs
- list missing constraints that still block a high-confidence recommendation, including pin geometry confirmation
- keep the output focused on what to search and what to confirm next
