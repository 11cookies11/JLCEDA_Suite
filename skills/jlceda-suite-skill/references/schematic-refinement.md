# JLCEDA Suite Schematic Refinement

This reference describes the preferred workflow for schematic edit batches.

## Goal

Apply a small, meaningful schematic change, then verify the document state before continuing.

## Inputs

Prepare these before running an edit batch:

- target function block or sheet
- ordered step list for placement, wiring, labels, ports, or save
- short design decisions that explain why the edit is being made
- verification checks for the block after the change

## Workflow

1. Read the current document summary and current schematic info.
2. Execute the edit steps in order.
3. Save when the batch is complete.
4. Re-read the document summary and current schematic info.
5. Review the post-edit validation summary.

## Good output shape

A good schematic-refinement result should include:

- before-state summary
- executed step list with per-step status
- design decisions or rationale log
- after-state summary
- validation summary and next checks

## Edit policy

- Prefer one function block per batch.
- Keep edit batches small enough to verify visually.
- Re-read context after placement and wiring work.
- Stop and review if any step fails instead of continuing blindly.
