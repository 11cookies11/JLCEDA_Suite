"""Generate a new example workspace skeleton."""

from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent


DOC_FILENAMES = [
    "00_requirements.md",
    "01_system_architecture.md",
    "02_power_tree.md",
    "03_boot_flow.md",
    "04_pinmux.md",
    "05_schematic_modules.md",
    "06_pcb_constraints.md",
    "07_bringup_plan.md",
    "08_risks.md",
]

WORKSPACE_FILES = {
    "hardware/README.md": "# Hardware Workspace\n\nThis folder is reserved for hardware artifacts.\n",
    "hardware/schematic/README.md": "# Schematic\n\nPlace KiCad schematic work products here when the design becomes concrete.\n",
    "hardware/pcb/README.md": "# PCB\n\nPlace PCB constraint notes, layout exports, and review artifacts here.\n",
    "hardware/libraries/README.md": "# Libraries\n\nPlace local symbol, footprint, and 3D asset work here if needed.\n",
    "hardware/production/README.md": "# Production\n\nPlace generated BOM, pick-and-place, fabrication outputs, and release notes here.\n",
    "source/README.md": "# Source Model\n\nAuthor the human-maintained circuit model here.\n",
    "build/README.md": "# Build Artifacts\n\nToolchain-generated resolved models and reports live here.\n",
}


def _default_title(project_name: str) -> str:
    parts = project_name.replace("_", "-").split("-")
    return " ".join(part.capitalize() if not part.isdigit() else part for part in parts if part)


def _render_root_readme(title: str, project_name: str) -> str:
    return dedent(
        f"""
        # {title}

        This example is a starter workspace for the {title} project.

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

        Generated project slug: `{project_name}`
        """
    ).lstrip()


def _render_doc(name: str, title: str) -> str:
    if name == "00_requirements.md":
        return dedent(
            f"""
            # 00 Requirements

            Project: {title}

            Status:

            - Draft
            - TODO / NEED_VERIFY items are expected until the first architecture pass is complete

            Captured intent:

            - Define the target hardware platform and product goals
            - Keep the first revision debug-friendly
            - Preserve a stable boot path and recovery path
            - Identify the required external interfaces and expansion points

            Open items:

            - Power tree
            - Core silicon / SoC selection
            - Connector count and pin assignment
            - Thermal and PCB size constraints
            """
        ).lstrip()

    if name == "01_system_architecture.md":
        return dedent(
            """
            # 01 System Architecture

            Status: Draft

            Planned contents:

            - System block diagram
            - Module list
            - Power tree draft
            - Boot chain overview
            - Major risk list

            Notes:

            - Keep the first revision focused on bring-up and observability
            - Avoid locking in detailed pin muxing until the reference design set is reviewed
            """
        ).lstrip()

    if name == "02_power_tree.md":
        return dedent(
            """
            # 02 Power Tree

            Status: Draft

            Planned contents:

            - Input protection
            - PMIC and regulator choices
            - Voltage rails
            - Current budget
            - Power-up sequencing
            - Test points
            - Per-rail risks
            """
        ).lstrip()

    if name == "03_boot_flow.md":
        return dedent(
            """
            # 03 Boot Flow

            Status: Draft

            Planned contents:

            - BootROM
            - Boot modes and recovery behavior
            - Primary boot path
            - Recovery boot path
            - Bootloader handoff
            - Kernel and rootfs bring-up
            """
        ).lstrip()

    if name == "04_pinmux.md":
        return dedent(
            """
            # 04 Pinmux

            Status: Draft

            Planned contents:

            - Debug UART pins
            - Boot-sensitive pins
            - High-speed interfaces
            - USB
            - GPIO header
            - I2C and SPI expansion
            - Reserved coprocessor interface
            """
        ).lstrip()

    if name == "05_schematic_modules.md":
        return dedent(
            """
            # 05 Schematic Modules

            Status: Draft

            Planned contents:

            - Core compute module
            - Memory subsystem
            - PMIC and regulators
            - Boot storage
            - Debug UART
            - External interfaces
            - Indicators and buttons
            - Test points
            """
        ).lstrip()

    if name == "06_pcb_constraints.md":
        return dedent(
            """
            # 06 PCB Constraints

            Status: Draft

            Planned contents:

            - Stackup target
            - High-speed routing constraints
            - DDR placement constraints
            - Power and return path guidance
            - Keepout and serviceability rules
            - Debug access requirements
            """
        ).lstrip()

    if name == "07_bringup_plan.md":
        return dedent(
            """
            # 07 Bring-up Plan

            Status: Draft

            Planned contents:

            - Pre-power checks
            - First power-on steps
            - UART log capture
            - FEL and SD boot checks
            - Peripheral smoke tests
            - Recovery plan when boot fails
            """
        ).lstrip()

    if name == "08_risks.md":
        return dedent(
            """
            # 08 Risks

            Status: Draft

            Primary risks to track:

            - DDR initialization failures
            - Wrong power rail sequencing
            - Missing Debug UART access
            - Boot strap mistakes
            - RGMII and USB signal integrity issues
            - Hardware and DTS mismatch
            """
        ).lstrip()

    return f"# {name.replace('_', ' ').replace('.md', '').title()}\n\nStatus: Draft\n"


def scaffold_example(
    project_name: str,
    *,
    title: str | None = None,
    root_dir: Path | str = "examples",
    overwrite: bool = False,
    include_circuit_model: bool = False,
) -> list[Path]:
    project_title = title or _default_title(project_name)
    root_path = Path(root_dir) / project_name

    if root_path.exists() and any(root_path.iterdir()) and not overwrite:
        raise FileExistsError(f"{root_path} already exists; pass --overwrite to reuse it")

    created: list[Path] = []

    def write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return
        path.write_text(content, encoding="utf-8", newline="\n")
        created.append(path)

    root_path.mkdir(parents=True, exist_ok=True)
    write_text(root_path / "README.md", _render_root_readme(project_title, project_name))

    docs_dir = root_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    for doc_name in DOC_FILENAMES:
        write_text(docs_dir / doc_name, _render_doc(doc_name, project_title))

    if include_circuit_model:
        write_text(
            root_path / "source" / "circuit-model.source.json",
            dedent(
                f"""
                {{
                  "schema_version": "circuit-model.v1",
                  "project_id": "{project_name}",
                  "request_id": "{project_name}",
                  "topology": "todo",
                  "components": [],
                  "nets": []
                }}
                """
            ).strip()
            + "\n",
        )
        write_text(
            root_path / "build" / "circuit-model.resolved.json",
            "{}\n",
        )

    for relative_path, content in WORKSPACE_FILES.items():
        write_text(root_path / relative_path, content)

    return created


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_name", help="Directory name to create under the example root")
    parser.add_argument("--title", help="Display title for the example")
    parser.add_argument("--root-dir", default="examples", help="Parent directory for the new example")
    parser.add_argument("--overwrite", action="store_true", help="Rewrite existing scaffold files")
    parser.add_argument(
        "--include-circuit-model",
        action="store_true",
        help="Also create minimal source/circuit-model.source.json and build/circuit-model.resolved.json placeholders",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        created = scaffold_example(
            args.project_name,
            title=args.title,
            root_dir=args.root_dir,
            overwrite=args.overwrite,
            include_circuit_model=args.include_circuit_model,
        )
    except FileExistsError as exc:
        parser.error(str(exc))
        return 2

    print(f"Created example scaffold at {Path(args.root_dir) / args.project_name}")
    print(f"Wrote {len(created)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
