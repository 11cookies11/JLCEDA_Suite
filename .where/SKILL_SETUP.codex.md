# Where Skill Setup

The project-local where-skill has been installed to:

- `.where/skills/where-skill`

## Notes

- Keep `AGENTS.md` and this skill aligned.
- Re-run `Where: Setup Skill For Current Project` after extension upgrades if needed.

## For Codex

- Reference `.where/skills/where-skill` in your project instructions.
- Ask Codex to use `where-skill` for `.where-agent-progress.md` updates.
- Tell Codex that indentation controls Where tree/board layout, so nested tasks must stay nested instead of being flattened.
- Prefer running `scripts/validate_where_plan.ps1` after plan edits.

Example:

Wrong:
```md
- [~] Improve task editing
- [x] Support cycle task status
- [ ] Optimize rename flow
```

Correct:
```md
- [~] Improve task editing
  - [x] Support cycle task status
  - [ ] Optimize rename flow
```
