# JLCEDA Suite Requirement Clarification

This reference defines how the skill should handle incomplete, ambiguous, or unstable design intent before any schematic synthesis begins.

## Goal

Stop the agent from guessing core electrical intent too early.

Use this reference when:

- the request is short or seed-like
- the design goal is still moving
- the user has not fixed the input, output, package, or constraints
- the circuit could otherwise be synthesized with hidden assumptions

## Clarification rule

Before generating SCD, CircuitModel, or ExecutionPlan, the agent should verify at least the minimum electrical intent needed to continue.

Examples of minimum intent:

- input source
- output voltage or target rail
- current budget
- interface type
- package constraint
- power-role expectation
- known chip or block requirement

## What to output

When the input is underspecified, the agent should output:

- what is already known
- what is missing
- which assumptions would be risky
- what should be confirmed next
- a short clarification prompt

## Hard stop cases

The agent should stop at clarification when:

- the user explicitly says the requirement is not finalized
- a strap or default mode would otherwise be guessed
- the block selection would depend on unstated electrical limits
- the user has not accepted the assumption set

## Safe behavior

- restate the current understanding
- ask for the minimum missing intent
- label any fallback assumption clearly
- keep the assumption visible in later outputs
- do not synthesize SCD until the intent is stable

