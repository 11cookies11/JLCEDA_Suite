# JLCEDA Suite PCB Assistance

This reference describes the preferred PCB follow-up workflow after schematic context is already clear.

## Goal

Carry the confirmed schematic intent into the PCB editor, check current board hygiene, and suggest the next safe placement or routing tasks.

## Inputs

Prepare these before running PCB assistance:

- current schematic block or design goal
- active PCB or board name
- optional focus areas such as power path, analog section, connector edge, or MCU core
- optional hygiene thresholds when the default rule profile should be overridden

## Workflow

1. Read the current document, schematic, board summary, and current PCB info.
2. Inspect PCB layout hygiene to surface crowding, routing, label, or board-edge risks.
3. Check ratline state so placement guidance stays aligned with live connectivity.
4. Summarize the top PCB issues.
5. Output placement advice and the next short task list.

## Good output shape

A good PCB-assist result should include:

- current schematic and PCB context
- hygiene issue count and issue-type summary
- top placement or routing risks
- placement advice for the next PCB pass
- next tasks that keep the board moving forward without losing schematic intent

## Edit policy

- Read first, move components second.
- Keep changes scoped to one function block at a time.
- Re-run hygiene checks after every meaningful placement pass.
- Use ratlines as guidance, but keep human review in charge of final placement and routing tradeoffs.
