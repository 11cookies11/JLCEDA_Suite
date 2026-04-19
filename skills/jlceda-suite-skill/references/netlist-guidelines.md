# JLCEDA Suite Netlist Guidelines

This reference defines the internal connection-level representation that should sit between CircuitModel and simulation or display layers.

## Goal

Make the electrical truth explicit and machine-readable.

Use this reference when:

- the agent needs a connection truth source
- the design should be checked or simulated
- the schematic display should be derived from electrical connectivity
- the user wants the connection structure normalized before execution

## What netlist should contain

At minimum, a netlist representation should include:

- component instance identifiers
- pin-to-net mapping
- net names
- parameter values
- subcircuit references
- explicit power and ground naming

## What netlist should not contain

Do not mix into the netlist:

- visual layout
- page placement
- drawing coordinates
- execution commands
- explanatory prose
- design rationale text

## Rules

- one component instance should map to stable pins
- one net name should represent one electrical connectivity group
- implicit connections should be normalized into explicit mappings
- unresolved or missing pin info should be marked clearly, not guessed

## Downstream uses

The netlist can feed:

- SPICE export
- simulation
- connectivity verification
- display graph generation

