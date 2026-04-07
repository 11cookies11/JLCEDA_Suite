# Integration Mapping

## Purpose

Use this mapping to keep skill triggering behavior consistent across Codex, Claude, Gemini, and Qwen style agents.

## Positive Trigger Signals

- User explicitly references `.where-agent-progress.md`.
- User asks to create/update task states (`[ ]`, `[~]`, `[!]`, `[x]`).
- User asks to fix plan format, indentation hierarchy, or duplicate task lines.
- User asks about Where board/sidebar/whiteboard tree layout or complains that tasks were flattened.
- User asks to preserve `where:id` while editing tasks.

## Negative Trigger Signals

- Pure Q&A, translation, writing help, or generic project advice without file edits.
- Request is for a plain-text plan template only, no file update expected.
- Request targets unrelated files and no Where plan operation is needed.

## Agent-Specific Notes

### Codex

- Trigger when user asks direct plan-file operations in workspace.
- Prefer immediate file edits and post-edit validation.
- If intent is ambiguous, avoid editing and ask for confirmation once.
- Treat indentation as UI structure, not decoration; preserve nested branches so Where keeps the intended grouped layout.

### Claude

- Trigger when user request references plan states or task hierarchy operations.
- Avoid over-triggering on abstract planning conversations.
- Keep structured edits deterministic and preserve existing IDs.

### Gemini

- Trigger on explicit markdown plan maintenance tasks.
- Require clear file-target intent before writing.
- Keep hierarchical indentation conservative (2-space step).

### Qwen

- Trigger when user asks practical plan synchronization and status transitions.
- Defer triggering if user requests only conceptual plan suggestions.
- Run validation script after edits when shell is available.

## Shared Guardrails

1. Preserve existing `where:id` comments.
2. Avoid duplicate tasks; update existing lines.
3. Keep one task per line.
4. Keep indentation level changes incremental.
5. Prefer one active `[~]` task unless parallel work is explicit.
