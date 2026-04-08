---
name: jlceda-bridge-flow
description: Drive a connected JLCEDA bridge session through the server control plane, create or open projects, and run the bundled project-flow script when the user wants Codex to operate JLCEDA through the bridge.
---

# JLCEDA Bridge Flow

## When to use

Use this skill when the user wants Codex to drive a live JLCEDA session through the bridge server instead of manually clicking the GUI.

Typical requests:

- create or open a JLCEDA project from the server side
- verify that the bridge session is connected before issuing editor commands
- run a repeatable server-side project flow against a connected EDA client
- package the bridge-session test flow together with the EDA plugin release

## Workflow

1. Confirm the bridge server is running and the plugin session is connected.
2. Use the control plane to read `/sessions` and pick the target `clientId`.
3. Run `scripts/server-project-flow.mjs` to create or open a project and exercise the bridge APIs.
4. If the user wants more coverage, continue with explicit bridge requests on the same connected session.

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

## Notes

- Keep `requiresConfirmation` disabled for the scripted flow unless the user explicitly asks to test confirmation handling.
- Use the same connected session for any follow-up bridge commands.
- If a command returns `confirmation_required`, stop and ask before retrying with confirmation.
