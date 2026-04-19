# JLCEDA Suite Simulation Guidelines

This reference defines how the skill should prepare and use simulation results, with `ngspice` as the initial target.

## Goal

Use simulation as a validation layer, not as a substitute for engineering judgment.

Use this reference when:

- the user wants behavioral validation
- the circuit should be checked before a schematic commit
- the result needs to be fed back into risks or follow-up edits
- the agent needs to turn a netlist into a simulation input

## Scope

The first simulation scope should focus on:

- operating point
- transient response
- small-signal AC response

## What simulation can validate

- bias correctness
- steady-state operating point
- waveform shape
- response trend
- sensitivity to parameter changes

## What simulation cannot replace

- strap and mode reasoning
- datasheet compliance judgment
- package and availability selection
- PCB parasitic and EMI analysis

## Required workflow

1. derive a simulation-ready netlist
2. export SPICE input
3. run `ngspice`
4. collect results and failures
5. write the outcome back into risks or follow-up tasks

## Good simulation output

A good result should include:

- analysis type
- key measured values
- pass or fail outcome
- failure reason if any
- next recommended action

