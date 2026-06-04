"""
KiCad Library Importer ???imports LCSC parts into project-local KiCad libraries.

Calls easyeda2kicad to download symbols, footprints, and 3D models, then
organizes them into a per-project library structure with lock file and risk report.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..shared.env_utils import env
from ..domain.core.part_selector import SelectedPart, classify_package_risk, package_risk_note


# ---------------------------------------------------------------------------
# YAML serializer (stdlib only, no pyyaml dependency)
# ---------------------------------------------------------------------------


def _yaml_value(value: object) -> str:
    """Serialize a scalar to YAML."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        if any(c in value for c in (':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`', '"', "'")):
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        if not value:
            return '""'
        return value
    return str(value)


def _yaml_dumps(obj: object, indent: int = 0) -> str:
    """Serialize a Python object to a YAML string (simple subset)."""
    pad = "  " * indent

    if isinstance(obj, dict):
        lines: list[str] = []
        for key, value in obj.items():
            prefix = f"{pad}{key}"
            if isinstance(value, dict):
                if value:
                    lines.append(f"{prefix}:")
                    lines.append(_yaml_dumps(value, indent + 1))
                else:
                    lines.append(f"{prefix}: {{}}")
            elif isinstance(value, list):
                if value:
                    lines.append(f"{prefix}:")
                    for item in value:
                        if isinstance(item, dict):
                            item_rendered = _yaml_dumps(item, indent + 1)
                            item_lines = item_rendered.splitlines()
                        if item_lines:
                            # First key prefixed with "- "
                            lines.append(f"{pad}  - {item_lines[0].strip()}")
                            # Remaining keys aligned under the key (4-space indent from key level)
                            for nl in item_lines[1:]:
                                if nl.strip():
                                    relative = nl[2:] if nl.startswith("  ") else nl.lstrip()
                                    lines.append(f"{pad}    {relative}")
                        else:
                            lines.append(f"{pad}  - {_yaml_value(item)}")
                else:
                    lines.append(f"{prefix}: []")
            else:
                lines.append(f"{prefix}: {_yaml_value(value)}")
        return "\n".join(lines)

    if isinstance(obj, list):
        lines: list[str] = []
        for item in obj:
            if isinstance(item, dict):
                item_rendered = _yaml_dumps(item, indent)
                item_lines = item_rendered.splitlines()
                if item_lines:
                    lines.append(f"{pad}- {item_lines[0].strip()}")
                    for nl in item_lines[1:]:
                        stripped = nl.strip()
                        if stripped:
                            lines.append(f"{pad}  {stripped}")
            else:
                lines.append(f"{pad}- {_yaml_value(item)}")
        return "\n".join(lines)

    return f"{pad}{_yaml_value(obj)}"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    """Result of importing parts into a KiCad project."""
    imported_count: int
    skipped_count: int
    failed_lcsc_ids: list[str]
    symbol_lib_file: str
    footprint_lib_dir: str
    model_dir: str
    lock_file: str
    risk_report_file: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------


def resolve_easyeda2kicad() -> str:
    """Locate the easyeda2kicad executable."""
    explicit = env("EASYEDA2KICAD_BIN")
    if explicit:
        return explicit
    located = shutil.which("easyeda2kicad") or shutil.which("easyeda2kicad.exe")
    if located:
        return located
    return ""


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------


def _run_easyeda2kicad(
    lcsc_id: str,
    executable: str,
    output_dir: Path,
    timeout: float,
) -> dict[str, object]:
    """Run easyeda2kicad for a single LCSC ID."""
    command = [executable, "--full", f"--lcsc_id={lcsc_id}", "--output", str(output_dir)]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "lcsc_id": lcsc_id,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "success": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "lcsc_id": lcsc_id,
            "returncode": None,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
            "success": False,
        }
    except OSError as exc:
        return {
            "lcsc_id": lcsc_id,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "success": False,
        }


# ---------------------------------------------------------------------------
# Lock file
# ---------------------------------------------------------------------------


def _parse_lock_file(path: Path) -> dict[str, dict[str, object]]:
    """Parse an existing part.lock.yaml file.

    Uses a simple line-based parser for the YAML subset we write.
    Returns dict of lcsc_id -> part data.
    """
    result: dict[str, dict[str, object]] = {}
    current_part: dict[str, object] | None = None
    current_lcsc: str | None = None
    in_parts = False

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("parts:"):
            in_parts = True
            continue
        if not in_parts:
            continue
        if stripped.startswith("  - "):
            # Save previous part
            if current_part is not None and current_lcsc:
                result[current_lcsc] = current_part
            current_part = {}
            current_lcsc = None
            # Parse inline key: value on the "  - " line
            rest = stripped[4:].strip()
            if ":" in rest:
                key, _, value = rest.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                current_part[key] = value
                if key == "lcsc_id":
                    current_lcsc = value
        elif current_part is not None and (stripped.startswith("    ") or stripped.startswith("\t")):
            kv = stripped.strip()
            if ":" in kv:
                key, _, value = kv.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                current_part[key] = value
                if key == "lcsc_id":
                    current_lcsc = value

    if current_part is not None and current_lcsc:
        result[current_lcsc] = current_part

    return result


def _build_lock_data(
    imported: list[SelectedPart],
    skipped: list[SelectedPart],
    existing: dict[str, dict[str, object]],
    *,
    project_name: str = "",
) -> dict[str, object]:
    """Build the part.lock.yaml data structure."""
    generated_at = datetime.now(timezone.utc).isoformat()

    parts: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    # Carry forward existing locked parts unchanged
    for lcsc_id, data in existing.items():
        parts.append(data)
        seen_ids.add(lcsc_id)

    def _part_entry(sel: SelectedPart, imported_at: str, status: str) -> dict[str, object]:
        risk = classify_package_risk(sel.package)
        return {
            "ref": sel.ref,                # filled by schematic generation
            "role": sel.requirement_id,
            "mpn": sel.mpn,
            "value": sel.value or sel.description,
            "lcsc_id": sel.lcsc_id,
            "package": sel.package,
            "source": sel.source,
            "kicad_symbol": "",            # filled by KiCad lib importer
            "kicad_footprint": "",         # filled by KiCad lib importer
            "risk": risk,
            "note": sel.note or package_risk_note(sel.package, risk),
            "imported_at": imported_at,
            "price": sel.price,
            "status": status,
        }

    # Add newly imported
    for sel in imported:
        if sel.lcsc_id and sel.lcsc_id not in seen_ids:
            parts.append(_part_entry(sel, generated_at, "review" if sel.needs_review else "locked"))
            seen_ids.add(sel.lcsc_id)

    # Add skipped (already existed) if not already recorded
    for sel in skipped:
        if sel.lcsc_id and sel.lcsc_id not in seen_ids:
            existing_at = str(existing.get(sel.lcsc_id, {}).get("imported_at", ""))
            parts.append(_part_entry(sel, existing_at, "locked"))
            seen_ids.add(sel.lcsc_id)

    result: dict[str, object] = {
        "schema_version": "part-lock.v1",
        "generated_at": generated_at,
        "parts": parts,
    }
    if project_name:
        result["project"] = project_name
    return result


# ---------------------------------------------------------------------------
# Risk report
# ---------------------------------------------------------------------------


def _build_risk_report(parts: list[SelectedPart]) -> str:
    """Build the part-risk-report.md content, categorized by risk level."""
    now = datetime.now(timezone.utc).isoformat()

    # Categorize parts by EasyEDA import risk level
    low_risk: list[SelectedPart] = []
    medium_risk: list[SelectedPart] = []
    high_risk: list[SelectedPart] = []
    for part in parts:
        risk = classify_package_risk(part.package)
        if risk == "high":
            high_risk.append(part)
        elif risk == "medium":
            medium_risk.append(part)
        else:
            low_risk.append(part)

    lines = [
        "# EasyEDA Import Risk Report",
        f"Generated: {now}",
        "",
    ]

    # Low Risk section
    lines.append("## Low Risk")
    lines.append("")
    if low_risk:
        for part in low_risk:
            note = part.note or package_risk_note(part.package, "low")
            lines.append(f"**{part.requirement_id}** {part.mpn} {part.package} {part.lcsc_id}")
            lines.append(f"- {note}")
            lines.append("- Low-risk package")
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # Medium Risk section
    lines.append("## Medium Risk")
    lines.append("")
    if medium_risk:
        for part in medium_risk:
            note = part.note or package_risk_note(part.package, "medium")
            lines.append(f"**{part.requirement_id}** {part.mpn} {part.package} {part.lcsc_id}")
            lines.append(f"- {note}")
            lines.append("- Medium-risk package; manual review recommended")
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # High Risk section
    lines.append("## High Risk")
    lines.append("")
    if high_risk:
        for part in high_risk:
            note = part.note or package_risk_note(part.package, "high")
            lines.append(f"**{part.requirement_id}** {part.mpn} {part.package} {part.lcsc_id}")
            lines.append(f"- {note}")
            lines.append("- KiCad -> EasyEDA Pro conversion may fail")
            lines.append("- Manual EasyEDA Pro or LCSC footprint path review may be required")
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    # Summary
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total Parts**: {len(parts)}")
    lines.append(f"- **Low Risk**: {len(low_risk)}")
    lines.append(f"- **Medium Risk**: {len(medium_risk)}")
    lines.append(f"- **High Risk**: {len(high_risk)}")

    needs_review = sum(1 for p in parts if p.needs_review)
    if needs_review > 0:
        lines.append(f"- **Needs Review**: {needs_review} part(s)")
    lines.append("")

    # Risk classification rules
    lines.append("### Risk Classification Rules")
    lines.append("")
    lines.append("- **Low**: 0603/0805/1206 passives, SOT-23, SOP, QFN/QFP standard packages")
    lines.append("- **Medium**: modules, edge-pad devices, large ICs (BGA, LGA), special headers/connectors")
    lines.append("- **High**: USB-C, FPC/FFC, card sockets, DC jacks, irregular pads, slotted/oblong holes, complex mechanical")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def import_parts(
    selections: list[SelectedPart],
    project_dir: str | Path,
    *,
    project_name: str = "",
    lib_dir: str | Path | None = None,
    easyeda2kicad_bin: str = "",
    timeout: float = 120.0,
) -> ImportResult:
    """Import selected parts into project-local KiCad libraries.

    Creates the following project structure::

        project/
          libs/
            jlc_symbols.kicad_sym
            JLC-MCP.pretty/
            3dmodels/
          part.lock.yaml
          part-risk-report.md

    Args:
        selections: Selected parts from part_selector.
        project_dir: Root of the KiCad project.
        project_name: Project name for part.lock.yaml (e.g. "esp32-c3-debugger").
        lib_dir: Override library directory (default: <project_dir>/libs).
        easyeda2kicad_bin: Path to easyeda2kicad executable.
        timeout: Timeout per subprocess call in seconds.

    Returns:
        ImportResult with paths and status.
    """
    project_path = Path(project_dir)
    lib_path = Path(lib_dir) if lib_dir else (project_path / "libs")

    # Target subdirectories
    fp_dir = lib_path / "JLC-MCP.pretty"
    model_dir = lib_path / "3dmodels"
    sym_file = lib_path / "jlc_symbols.kicad_sym"

    fp_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    # Locate executable: explicit parameter takes priority, else auto-detect
    if easyeda2kicad_bin:
        executable = easyeda2kicad_bin
    else:
        executable = resolve_easyeda2kicad()
    if not executable or not Path(executable).exists():
        lock_path = project_path / "part.lock.yaml"
        report_path = project_path / "part-risk-report.md"
        return ImportResult(
            imported_count=0,
            skipped_count=0,
            failed_lcsc_ids=[s.lcsc_id for s in selections if s.lcsc_id],
            symbol_lib_file=str(sym_file),
            footprint_lib_dir=str(fp_dir),
            model_dir=str(model_dir),
            lock_file=str(lock_path),
            risk_report_file=str(report_path),
            errors=["easyeda2kicad not found. Install it or set EASYEDA2KICAD_BIN."],
        )

    # Check existing lock file for already-imported parts
    lock_path = project_path / "part.lock.yaml"
    existing_locked = _parse_lock_file(lock_path)

    # Import each part
    imported: list[SelectedPart] = []
    skipped: list[SelectedPart] = []
    failed: list[str] = []

    for sel in selections:
        if not sel.lcsc_id:
            skipped.append(sel)
            continue
        if sel.lcsc_id in existing_locked:
            skipped.append(sel)
            continue

        result = _run_easyeda2kicad(sel.lcsc_id, executable, lib_path, timeout)
        if result["success"]:
            imported.append(sel)
        else:
            failed.append(sel.lcsc_id)

    # Write lock file
    lock_data = _build_lock_data(imported, skipped, existing_locked, project_name=project_name)
    lock_path.write_text(_yaml_dumps(lock_data) + "\n", encoding="utf-8")

    # Write risk report
    all_parts = imported + skipped
    report_path = project_path / "part-risk-report.md"
    report_path.write_text(_build_risk_report(all_parts), encoding="utf-8")

    return ImportResult(
        imported_count=len(imported),
        skipped_count=len(skipped),
        failed_lcsc_ids=failed,
        symbol_lib_file=str(sym_file),
        footprint_lib_dir=str(fp_dir),
        model_dir=str(model_dir),
        lock_file=str(lock_path),
        risk_report_file=str(report_path),
        warnings=[f"Failed to import: {', '.join(failed)}"] if failed else [],
    )
