---
name: where-skill
description: Manage planning and progress tracking for the Where extension using `.where-agent-progress.md`. Use when Codex needs to create or update the workspace plan file, maintain indentation-based parent/child task hierarchy, preserve the tree structure that drives Where sidebar and whiteboard layout, keep one-task-per-line formatting, preserve existing task identity comments, and resolve blocked/in-progress transitions in multi-agent workflows. Do not use this skill for generic planning advice or plain-text templates when the user does not request file updates.
---

# Where Skill

Keep the source-of-truth plan file valid, concise, and aligned with real execution.

Treat indentation as product behavior, not cosmetic formatting. Where renders nested tasks as a collapsible multi-level tree, so flattening branches changes the UI layout and loses planning context.

Plan history is enabled by default in Where. When you update the plan and older content will disappear, preserve that previous snapshot in history instead of discarding it. Prefer archiving before any destructive rewrite.

## Use this workflow

1. Locate the plan file (default `.where-agent-progress.md`).
2. If missing, initialize from `assets/plan-template.md` or run `scripts/init_where_plan.ps1`.
3. Update existing task lines first; add new lines only when no existing task matches.
4. Keep status transitions explicit (`[ ] -> [~] -> [x]` or `[!]`).
5. Keep hierarchy stable with 2-space indentation increments.
6. Preserve or create indentation-based multi-level nesting so Where keeps the intended board/sidebar layout.
7. If the edit will replace or remove existing content, archive the current plan first so the previous snapshot remains available.
8. Finish by validating format via `scripts/validate_where_plan.ps1`.
9. If validation fails or file state is inconsistent, follow `references/error-handling.md`.

## Enforce trigger boundary

- Trigger only when user intent requires plan file creation or modification.
- Do not trigger for pure consultation, generic project planning text, or template brainstorming without file edits.
- If intent is ambiguous, prefer asking or giving plain guidance without editing files.

## Enforce plan contract

- Keep Markdown only.
- Keep one task per line.
- Use status markers exactly: `[ ]`, `[~]`, `[!]`, `[x]`.
- Use spaces only; do not use tabs.
- Do not skip indentation levels.
- Keep task titles short and actionable.
- Include blocker reason in blocked task title.
- Do not flatten child tasks into sibling tasks unless the user explicitly asks to restructure the plan.

## Preserve existing structure

- Preserve existing HTML ID comments when present, for example `<!-- where:id:xxx -->`.
- Do not duplicate a task line to represent status change; edit the original line.
- Prefer one active `[~]` parent task at a time unless parallel work is clearly intended.
- Mark completed parent and relevant children `[x]` together.
- Preserve branch meaning: parent tasks describe outcomes, child tasks describe scoped steps inside that branch.
- Default history is on. If plan content shrinks, make sure the removed material is preserved through the history workflow.

## Hierarchy example

Wrong: flattening removes the branch grouping that Where uses for layout.

```md
- [~] Improve task editing
- [x] Support cycle task status
- [ ] Optimize rename flow
- [ ] Add keyboard shortcuts
```

Correct: keep scoped work nested under the parent branch.

```md
- [~] Improve task editing
  - [x] Support cycle task status
  - [ ] Optimize rename flow
  - [ ] Add keyboard shortcuts
```

## Resolve common scenarios

- New request fits existing parent task: add a child task line under that parent.
- User asks for execution now: set the relevant task to `[~]` before edits.
- Task is complete: set parent and done children `[x]`, then move next target to `[~]`.
- User refers to dashboard, board, sidebar, whiteboard, tree, branch, or nested layout: treat that as a signal to protect hierarchy and avoid flattening.
- Any parse/write/structure error: resolve using `references/error-handling.md`.

## Use bundled resources

- Read `references/where-progress-rules.md` for strict format and status rules.
- Read `references/workflow-recipes.md` for edit patterns and edge cases.
- Read `references/error-handling.md` for recovery steps and fallback strategy.
- Read `references/integration-mapping.md` for cross-agent trigger mapping and guardrails.
- Use `assets/plan-template.md` when creating or resetting a plan skeleton.
- Run `scripts/init_where_plan.ps1` to initialize a missing plan file.
- Run `scripts/validate_where_plan.ps1` after edits to catch format regressions.

## Validate before handoff

Run:

```powershell
powershell -ExecutionPolicy Bypass -File skills/where-skill/scripts/validate_where_plan.ps1 -PlanPath .where-agent-progress.md
```

Treat validation warnings as action items and fix the file before final response.
