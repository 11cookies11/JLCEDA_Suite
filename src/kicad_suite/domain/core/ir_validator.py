"""IR Validator: structural and semantic checks on a Resolved Hardware IR."""

from __future__ import annotations

import re
from typing import Any

from ...shared.schema_versions import IR_SCHEMA_VERSION
from ...shared.validation.common import ValidationReport


# Fields that must never appear in IR (KiCad-specific leakage).
_KICAD_FORBIDDEN_FIELDS = ("lib_id", "footprint", "at", "symbol_size")
_KICAD_FORBIDDEN_PREFIXES = ("KiCad:", "kicad_", "AIAgent:")
_KICAD_LIBRARY_PATH_RE = re.compile(r"^[A-Za-z0-9_.+\-]+:[A-Za-z0-9_.+\-/]+$")


def validate_ir(ir: dict[str, Any]) -> ValidationReport:
    """Run all structural and semantic checks on an IR dict.

    Returns a ``ValidationReport`` ???check ``report.ok`` for pass/fail.
    """
    report = ValidationReport()

    _check_schema(report, ir)
    _check_components(report, ir)
    _check_pin_integrity(report, ir)
    _check_nets(report, ir)
    _check_reference_integrity(report, ir)
    _check_sheets(report, ir)
    _check_power_tree(report, ir)
    _check_constraint_targets(report, ir)
    _check_no_kicad_leakage(report, ir)

    # Always emit stats so callers can consume counts.
    components = ir.get("components", [])
    nets = ir.get("nets", [])
    report.stats.update({
        "component_count": len(components) if isinstance(components, list) else 0,
        "net_count": len(nets) if isinstance(nets, list) else 0,
        "sheet_count": len(ir.get("sheets", []) or []),
        "power_rail_count": len(ir.get("power_tree", []) or []),
        "interface_count": len(ir.get("interfaces", []) or []),
        "risk_count": len(ir.get("risks", []) or []),
        "constraint_count": len(ir.get("constraints", []) or []),
    })

    if report.ok:
        report.add_check("IR validation passed")
    return report


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_schema(report: ValidationReport, ir: dict[str, Any]) -> None:
    if not isinstance(ir, dict):
        report.add_error("IR must be a dict")
        return
    sv = ir.get("schema_version", "")
    if sv != IR_SCHEMA_VERSION:
        report.add_error(f"IR schema_version must be '{IR_SCHEMA_VERSION}', got '{sv}'")
    for key in ("request_id", "project_id", "topology"):
        if not isinstance(ir.get(key), str) or not ir.get(key):
            report.add_warning(f"IR.{key} is missing or empty")
    for key in ("components", "nets"):
        if not isinstance(ir.get(key), list):
            report.add_error(f"IR.{key} must be a list")
    if report.ok:
        report.add_check("IR schema structure ok")


def _check_components(report: ValidationReport, ir: dict[str, Any]) -> None:
    components = ir.get("components", [])
    if not isinstance(components, list):
        return
    seen_refs: set[str] = set()
    for i, comp in enumerate(components):
        if not isinstance(comp, dict):
            report.add_error(f"IR.components[{i}] must be an object")
            continue
        ref = str(comp.get("ref", ""))
        if not ref:
            report.add_error(f"IR.components[{i}] missing ref")
            continue
        if ref in seen_refs:
            report.add_error(f"IR.components: duplicate ref '{ref}'")
        seen_refs.add(ref)
    report.add_check("IR components checked")


def _check_pin_integrity(report: ValidationReport, ir: dict[str, Any]) -> None:
    valid_sources = {"netlist", "pinmap", "model", "pack_default", "resolver"}
    for comp in ir.get("components", []):
        if not isinstance(comp, dict):
            continue
        ref = comp.get("ref", "?")
        pins = comp.get("pins", [])
        if not isinstance(pins, list):
            report.add_error(f"IR.components[{ref}].pins must be a list")
            continue
        if not pins:
            report.add_warning(f"IR.components[{ref}] has no pins")
            continue
        seen_numbers: set[str] = set()
        for i, pin in enumerate(pins):
            if not isinstance(pin, dict):
                report.add_error(f"IR.components[{ref}].pins[{i}] must be an object")
                continue
            number = str(pin.get("number", ""))
            if not number:
                report.add_error(f"IR.components[{ref}].pins[{i}] missing number")
            elif number in seen_numbers:
                report.add_error(f"IR.components[{ref}].pins: duplicate pin number '{number}'")
            seen_numbers.add(number)
            source = str(pin.get("source", ""))
            if source and source not in valid_sources:
                report.add_warning(
                    f"IR.components[{ref}].pins[{number}] unknown source '{source}'"
                )
    report.add_check("IR pin integrity checked")


def _check_nets(report: ValidationReport, ir: dict[str, Any]) -> None:
    nets = ir.get("nets", [])
    if not isinstance(nets, list):
        return
    seen_names: set[str] = set()
    for i, net in enumerate(nets):
        if not isinstance(net, dict):
            report.add_error(f"IR.nets[{i}] must be an object")
            continue
        name = str(net.get("name", ""))
        if not name:
            report.add_error(f"IR.nets[{i}] missing name")
            continue
        if name in seen_names:
            report.add_error(f"IR.nets: duplicate net name '{name}'")
        seen_names.add(name)
        members = net.get("members", [])
        if not isinstance(members, list):
            report.add_error(f"IR.nets[{name}].members must be a list")
        elif not members:
            report.add_warning(f"IR.nets[{name}] has no members (floating)")
        else:
            for j, member in enumerate(members):
                member_str = str(member)
                if "." not in member_str:
                    report.add_error(
                        f"IR.nets[{name}].members[{j}] '{member_str}' must be ref.pin format"
                    )
        kind = net.get("kind", "")
        if kind not in ("signal", "power", "ground", "unknown", ""):
            report.add_warning(f"IR.nets[{name}] unknown kind '{kind}'")
    report.add_check("IR nets checked")


def _check_reference_integrity(report: ValidationReport, ir: dict[str, Any]) -> None:
    """Ensure net members, sheet refs, and pinmap refs point to real entities."""
    components = ir.get("components", [])
    nets = ir.get("nets", [])
    refs = {str(c.get("ref", "")) for c in components if isinstance(c, dict)}
    net_names = {str(n.get("name", "")) for n in nets if isinstance(n, dict)}

    # Net members ->component refs.
    for net in nets:
        if not isinstance(net, dict):
            continue
        net_name = net.get("name", "?")
        for member in net.get("members", []):
            ref = str(member).split(".", 1)[0]
            if ref and ref not in refs:
                report.add_error(
                    f"IR.nets[{net_name}] member '{member}' references missing component '{ref}'"
                )

    # Sheet refs.
    for sheet in ir.get("sheets", []):
        if not isinstance(sheet, dict):
            continue
        sname = sheet.get("name", "?")
        for ref in sheet.get("components", []):
            if str(ref) not in refs:
                report.add_error(f"IR.sheets[{sname}].components references missing '{ref}'")
        for n in sheet.get("nets", []):
            if str(n) not in net_names:
                report.add_error(f"IR.sheets[{sname}].nets references missing net '{n}'")
        for n in sheet.get("inputs", []):
            if str(n) not in net_names:
                report.add_error(f"IR.sheets[{sname}].inputs references missing net '{n}'")
        for n in sheet.get("outputs", []):
            if str(n) not in net_names:
                report.add_error(f"IR.sheets[{sname}].outputs references missing net '{n}'")

    # Pinmap refs.
    pinmap = ir.get("pinmap", {})
    if isinstance(pinmap, dict):
        for ref, pins in pinmap.items():
            if ref not in refs:
                report.add_error(f"IR.pinmap references missing component '{ref}'")
            if isinstance(pins, dict):
                for pin, entry in pins.items():
                    net = ""
                    if isinstance(entry, dict):
                        net = str(entry.get("net", ""))
                    if net and net not in net_names:
                        report.add_error(
                            f"IR.pinmap[{ref}][{pin}].net '{net}' not found in nets"
                        )

    # Interface connector refs.
    for iface in ir.get("interfaces", []):
        if not isinstance(iface, dict):
            continue
        conn = str(iface.get("connector_ref", ""))
        if conn and conn not in refs:
            report.add_error(f"IR.interfaces[{iface.get('name', '?')}].connector_ref '{conn}' not found")
        for n in iface.get("nets", []):
            if str(n) not in net_names:
                report.add_error(f"IR.interfaces[{iface.get('name', '?')}].nets references missing net '{n}'")

    report.add_check("IR reference integrity checked")


def _check_sheets(report: ValidationReport, ir: dict[str, Any]) -> None:
    sheets = ir.get("sheets", [])
    if not isinstance(sheets, list):
        return
    seen: set[str] = set()
    for s in sheets:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", ""))
        if not name:
            report.add_error("IR.sheets entry missing name")
        elif name in seen:
            report.add_error(f"IR.sheets duplicate name '{name}'")
        seen.add(name)
    report.add_check("IR sheets checked")


def _check_power_tree(report: ValidationReport, ir: dict[str, Any]) -> None:
    tree = ir.get("power_tree", [])
    if not isinstance(tree, list):
        return
    rail_names = {str(r.get("rail", "")) for r in tree if isinstance(r, dict)}
    for r in tree:
        if not isinstance(r, dict):
            continue
        rail = str(r.get("rail", "?"))
        parent = str(r.get("parent", ""))
        if parent and parent not in rail_names:
            report.add_error(f"IR.power_tree[{rail}].parent '{parent}' not found")
        for child in r.get("children", []):
            if str(child) not in rail_names:
                report.add_error(f"IR.power_tree[{rail}].children '{child}' not found")

    # Circular reference detection via DFS.
    if rail_names:
        graph: dict[str, list[str]] = {n: [] for n in rail_names}
        for r in tree:
            if not isinstance(r, dict):
                continue
            rail = str(r.get("rail", ""))
            parent = str(r.get("parent", ""))
            if parent and parent in rail_names:
                graph[parent].append(rail)

        WHITE, GREY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in rail_names}

        def _dfs(node: str) -> bool:
            color[node] = GREY
            for child in graph.get(node, []):
                if color[child] == GREY:
                    report.add_error(f"IR.power_tree circular reference involving '{node}' -> '{child}'")
                    return False
                if color[child] == WHITE:
                    if not _dfs(child):
                        return False
            color[node] = BLACK
            return True

        for n in rail_names:
            if color[n] == WHITE:
                _dfs(n)

    report.add_check("IR power tree checked")


def _check_constraint_targets(report: ValidationReport, ir: dict[str, Any]) -> None:
    constraints = ir.get("constraints", [])
    if not isinstance(constraints, list) or not constraints:
        return
    refs = {str(c.get("ref", "")) for c in ir.get("components", []) if isinstance(c, dict)}
    net_names = {str(n.get("name", "")) for n in ir.get("nets", []) if isinstance(n, dict)}
    for c in constraints:
        if not isinstance(c, dict):
            continue
        cname = c.get("name", c.get("type", "?"))
        scope = str(c.get("scope", ""))
        targets = c.get("targets", c.get("rules", []))
        if not isinstance(targets, list):
            continue
        for t in targets:
            t_str = str(t)
            if scope == "net" and t_str not in net_names:
                report.add_warning(f"IR.constraints[{cname}].targets '{t_str}' not found in nets")
            elif scope == "component" and t_str not in refs:
                report.add_warning(f"IR.constraints[{cname}].targets '{t_str}' not found in components")
    report.add_check("IR constraints checked")


def _check_no_kicad_leakage(report: ValidationReport, ir: dict[str, Any]) -> None:
    """Detect KiCad-specific fields leaking into the IR."""
    import json

    def _scan(obj: Any, path: str = "$") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                cur = f"{path}.{key}"
                if key in _KICAD_FORBIDDEN_FIELDS:
                    report.add_error(f"IR{cur}: forbidden KiCad field '{key}' leaked into IR")
                if isinstance(value, str):
                    # Check for KiCad library path patterns (e.g. "Resistor_SMD:R_0603").
                    if _KICAD_LIBRARY_PATH_RE.match(value) and not value.startswith(("http:", "https:")):
                        # Package strings like "QFN-20" are hardware facts ???allowed.
                        # Full library paths like "Resistor_SMD:R_0603" are not.
                        parts = value.split(":")
                        if len(parts) == 2 and not any(
                            c in parts[0] for c in (" ", "-", "_")
                        ) and parts[0][0].isupper():
                            pass  # likely "JLC-MCP:..." ???check further
                        else:
                            report.add_warning(
                                f"IR{cur}: value '{value}' looks like a KiCad library path"
                            )
                    for prefix in _KICAD_FORBIDDEN_PREFIXES:
                        if value.startswith(prefix):
                            report.add_error(
                                f"IR{cur}: value '{value}' starts with KiCad-specific prefix '{prefix}'"
                            )
                _scan(value, cur)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan(item, f"{path}[{i}]")

    _scan(ir)
    if report.ok:
        report.add_check("IR no KiCad leakage")
