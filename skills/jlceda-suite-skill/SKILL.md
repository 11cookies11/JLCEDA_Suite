---
name: jlceda-suite-skill
description: Drive a connected JLCEDA Suite session through the suite server control plane, operate supported project/schematic/PCB/system APIs, and use system.api_invoke for the official JLCEDA API surface when the user wants an AI agent to operate JLCEDA through the suite.
---

# JLCEDA Suite Skill

## When to use

Use this skill when the user wants an AI agent to drive a live JLCEDA session through the JLCEDA Suite Server instead of manually clicking the GUI.

Typical requests:

- create or open a JLCEDA project from the server side
- verify that the bridge session is connected before issuing editor commands
- run a repeatable server-side project flow against a connected EDA client
- package the bridge-session test flow together with the EDA plugin release
- call supported JLCEDA APIs directly through the bridge, including `system.api_invoke` for official API methods not exposed as dedicated bridge commands

## Workflow

1. Confirm the bridge server is running and the plugin session is connected.
2. Use the control plane to read `/sessions` and pick the target `clientId`.
3. Prefer dedicated bridge commands for common project, schematic, PCB, and system operations.
4. Use `system.api_invoke` for official JLCEDA API methods that are not exposed as dedicated bridge commands.
5. Run `scripts/server-project-flow.mjs` when you need the standard create/open/project-inspection flow.
6. Run `scripts/server-command-runner.mjs` when you need an arbitrary multi-step control-plane sequence against a connected session.
7. If the user wants more coverage, continue with explicit bridge requests on the same connected session.

## Script

Use `scripts/server-project-flow.mjs` for the server-side project flow.

Environment:

- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target
- `BRIDGE_PROJECT_NAME`: project friendly name, default `Codex Test Project`
- `BRIDGE_PROJECT_CODE`: project code, default `codex-test-project`

The script:

- lists connected bridge sessions
- selects the target client
- creates a project
- opens the project
- reads project info and inventory
- creates a schematic and a schematic page
- reads the current schematic and document summary

Use `scripts/server-command-runner.mjs` for generic control-plane execution.

Environment:

- `BRIDGE_CONTROL_URL`: control-plane URL, default `http://127.0.0.1:8788`
- `BRIDGE_CONTROL_TOKEN`: optional control-plane token
- `BRIDGE_TARGET_CLIENT_ID`: optional client id to target
- `BRIDGE_AUTO_APPROVE`: set to `true` to resubmit confirmation-required commands without manual intervention
- `BRIDGE_COMMANDS_JSON`: inline JSON plan with `clientId` and `requests`
- `BRIDGE_COMMANDS_FILE`: path to a JSON plan file

The plan format is:

```json
{
  "clientId": "jlc-eda-main",
  "requests": [
    {
      "id": "step-001",
      "domain": "system",
      "action": "get_bridge_status",
      "payload": {}
    }
  ]
}
```

The runner:

- resolves the target session
- sends each command in order
- prints each response
- can auto-approve confirmation-required steps when requested

## Supported API surface

The bridge supports two layers:

1. Dedicated bridge commands for the most common actions.
2. `system.api_invoke` for direct access to the underlying JLCEDA API surface.

Read [references/api-surface.md](references/api-surface.md) for the family-by-family API map and the recommended call order.
Read [references/task-sequences.md](references/task-sequences.md) for the shortest call sequences for common tasks.

## Call strategy

- Use dedicated bridge commands first when they exist and already cover the task.
- Use `system.api_invoke` when the official JLCEDA API exists but has not been wrapped as a bridge command yet.
- Use `scripts/server-command-runner.mjs` when you want Codex to drive a multi-step sequence from the control plane without hand-editing live GUI state.
- Use confirmation-free read operations for inspection.
- Keep confirmation enabled for state-changing operations unless the user explicitly requests a test path.
- Keep the same connected session for any follow-up request chain.
- If a command returns `confirmation_required`, stop and ask before retrying with confirmation.

## Notes

- Keep `requiresConfirmation` disabled for read-only bridge requests unless the user explicitly asks to test confirmation handling.
- For `system.api_invoke`, pass a dotted path like `dmt_Project.getCurrentProjectInfo` or `eda.dmt_Project.getCurrentProjectInfo`.
- For library, schematic, and PCB work, prefer first reading the current project/document context, then invoking the smallest method needed, then saving/exporting results.
