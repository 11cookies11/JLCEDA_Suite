# Workflow Recipes

## Recipe 1: Start New Work

1. Find a matching parent task.
2. If missing, add a new concise parent task.
3. Set target task to `[~]`.
4. Add the first child step as `[ ]`.

## Recipe 2: Mark Completion

1. Mark completed child steps `[x]`.
2. Mark parent `[x]` when all required children are done.
3. Move next relevant task to `[~]` if work continues.

## Recipe 3: Handle Blockers

1. Set blocked task to `[!]`.
2. Add blocker reason in the title.
3. Add a separate unblocked fallback task if work can continue.

## Recipe 4: Keep Tree Stable

1. Do not move unrelated branches.
2. Keep indentation changes by one level only.
3. Reuse existing wording when possible to keep history readable.
4. Treat a parent branch as a visual group in Where; add new substeps inside that branch instead of flattening them beside it.
5. If a user mentions whiteboard, board, sidebar, tree, or layout, double-check that the final structure still renders as intended.

## Recipe 5: Recover from Errors

1. Identify error category with `references/error-handling.md`.
2. Apply the matching recovery steps.
3. Run validation script again before handoff.

## Recipe 6: Dedupe While Preserving IDs

1. Detect duplicates by semantic title match in same branch.
2. Select canonical line (earliest task line in branch).
3. Preserve canonical `where:id` comment unchanged.
4. Merge status/title updates into canonical line.
5. Remove duplicates only after confirming children remain attached.
6. If non-canonical IDs are removed, keep a one-line audit note for manual cleanup.

## Recipe 7: Preserve Shrinking Plans

1. If the next edit removes or overwrites existing plan content, archive the current plan first.
2. Keep the disappearing snapshot available in history for later article-writing or retrospective work.
3. Then update the source plan file normally.
