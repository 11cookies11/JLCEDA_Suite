# nexdap-esp32c3-managed-rp2040-swd-coprocessor-v2

This example is a starter workspace for the nexdap-esp32c3-managed-rp2040-swd-coprocessor-v2 project.

Project intent:

- Start from a generic hardware project template
- Keep the workspace ready for schematic, PCB, release, and validation artifacts
- Let the hardware model define the actual target platform and BOM

Current status:

- Requirements captured in `docs/00_requirements.md`
- Architecture and bring-up documents are scaffolded
- Hardware workspaces are ready for detail work

Recommended next steps:

1. Freeze requirements in `docs/00_requirements.md`
2. Draft the system architecture in `docs/01_system_architecture.md`
3. Create `source/circuit-model.source.json` when the interface list is stable
4. Let the toolchain generate `build/circuit-model.resolved.json`

Generated project slug: `nexdap-v2`
