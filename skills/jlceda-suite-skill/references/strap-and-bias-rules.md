# JLCEDA Suite Strap and Bias Rules

This reference collects the rules for mode straps, bias defaults, pull networks, startup choices, and other decisions that should not be guessed silently.

## Goal

Prevent the agent from taking shortcuts on mode pins, strap pins, bias networks, or startup defaults.

Use this reference when:

- the circuit includes enable, mode, boot, sense, or select pins
- a component needs a pull-up or pull-down choice
- a bias network or reference voltage needs to be selected
- a default connection could change the operating mode
- the user asked for power, regulator, interface, or startup behavior

## Rule

Every strap or bias choice should have one of these forms of support:

- datasheet recommendation
- application note guidance
- direct calculation
- explicit user confirmation
- clearly labeled assumption

## Required output shape

For each critical strap or bias decision, record:

- pin or net name
- chosen state or value
- support type
- source or calculation basis
- risk if wrong
- whether manual confirmation is still needed

## Hard rules

- do not guess strap states from convenience
- do not leave a strap node floating unless the datasheet allows it
- do not convert a bias choice into a default without explanation
- do not hide an assumption inside the schematic description

## Review checks

Before synthesis or execution, check:

- every mode pin has a stated state
- every pull network has an explicit reason
- every startup-sensitive node has a documented choice
- every unresolved decision is marked as pending

