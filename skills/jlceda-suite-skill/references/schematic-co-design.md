# JLCEDA Suite Schematic Co-Design

This reference describes the preferred collaboration pattern for Codex + JLCEDA schematic work.

Use it when the goal is not just to send commands, but to reason about the schematic together with the user.

## Primary objective

Help the user iterate on the target schematic by combining:

- live JLCEDA context
- component selection reasoning
- small, verifiable schematic edits
- explicit design rationale

## Default sequence

1. Inspect the current context.
2. Identify the active function block.
3. Capture requirements and constraints.
4. Compare candidate parts or topology choices.
5. Propose the smallest safe edit.
6. Apply the edit.
7. Re-read the context and verify the result.
8. Leave a short summary for the next step.

## Context checklist

Before making schematic changes, read or summarize:

- current project name
- active schematic and page
- current selection
- power rails involved
- interfaces involved
- critical nets or reference designators already present
- whether the user is asking for selection, correction, or extension

## Component selection checklist

Capture at least these points when recommending a part:

- electrical role in the circuit
- voltage and current limits
- precision, speed, or bandwidth constraints
- package and assembly constraints
- cost or sourcing constraints
- why the chosen part fits this exact schematic block better than the alternatives

## Edit policy

- Prefer one function block at a time.
- Avoid broad multi-sheet changes before local verification.
- Re-read the schematic state after each meaningful edit batch.
- When a constraint is still unclear, stop at a recommendation instead of forcing a schematic mutation.

## Good outputs

A good co-design response should include:

- what the current schematic context is
- what problem or design decision is being addressed
- what change is recommended or applied
- why that change is appropriate
- what should be checked next
