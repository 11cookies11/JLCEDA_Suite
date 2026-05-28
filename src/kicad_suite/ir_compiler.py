"""Resolved Hardware IR compiler: circuit-model.json → ir.v1 (EDA-independent)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .schema_versions import IR_SCHEMA_VERSION


def build_ir(model: dict[str, Any]) -> dict[str, Any]:
    """Compile a circuit-model dict into a Resolved Hardware IR dict.

    The IR is a pure-hardware-facts view: no lib_id, no KiCad footprint paths,
    no schematic coordinates.  It is the single source of truth for downstream
    backends (KiCad, SPICE, BOM, docs).
    """
    request_id = str(model.get("request_id", ""))
    project_id = str(model.get("project_id", request_id))
    topology = str(model.get("topology", project_id))

    # 1.  Resolve nets into per-component pin lists.
    pin_entries = _collect_pin_entries(model)

    # 2.  Build component list with resolved pins.
    components = _build_components(model, pin_entries)

    # 3.  Build net list (normalised members).
    nets = _build_nets(model)

    # 4.  Copy sheets as-is (pure hardware grouping).
    sheets = _snapshot_list(model.get("sheets", []))

    # 5.  Resolve pinmap into structured dict.
    pinmap_dict = _build_pinmap(model)

    # 6.  Build power tree from power_rails.
    power_tree = _build_power_tree(model)

    # 7.  Extract interfaces from constraints.
    interfaces = _build_interfaces(model)

    # 8.  Validate references (net members must reference existing components).
    _validate_references(components, nets)

    return {
        "schema_version": IR_SCHEMA_VERSION,
        "request_id": request_id,
        "project_id": project_id,
        "topology": topology,
        "components": components,
        "nets": nets,
        "sheets": sheets,
        "pinmap": pinmap_dict,
        "power_tree": power_tree,
        "interfaces": interfaces,
        "calculations": _snapshot_list(model.get("calculations", [])),
        "design_decisions": _snapshot_list(model.get("design_decisions", [])),
        "risks": _snapshot_list(model.get("risks", [])),
        "constraints": _snapshot_list(model.get("constraints", [])),
    }


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _collect_pin_entries(model: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Walk nets[].members and build {ref: [pin_entry, ...]}."""
    pin_by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for net in model.get("nets", []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get("name", ""))
        for member in net.get("members", []):
            member_str = str(member).strip()
            if "." not in member_str:
                continue
            ref, pin = member_str.rsplit(".", 1)
            if ref and pin:
                pin_by_ref[ref].append({
                    "number": pin,
                    "name": "",
                    "net": net_name,
                    "direction": "unspecified",
                    "locked": False,
                    "source": "netlist",
                })
    return dict(pin_by_ref)


def _build_components(
    model: dict[str, Any],
    pin_entries: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Assemble IR component list, merging pin entries with pinmap overrides."""
    # Build a pinmap lookup: {ref: {pin_number: pinmap_entry}}
    pinmap_lookup: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", ""))
        pm = component.get("pinmap")
        if isinstance(pm, dict):
            for pin, entry in pm.items():
                if isinstance(entry, dict):
                    pinmap_lookup[ref][str(pin)] = entry

    components: list[dict[str, Any]] = []
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", "")).strip()
        if not ref:
            continue

        # Merge netlist pins with pinmap overrides.
        pins: list[dict[str, Any]] = []
        seen_pins: set[str] = set()
        for entry in pin_entries.get(ref, []):
            pin_num = entry["number"]
            overrides = pinmap_lookup.get(ref, {}).get(pin_num)
            if isinstance(overrides, dict):
                merged = dict(entry)
                if overrides.get("net"):
                    merged["net"] = str(overrides["net"])
                if "locked" in overrides:
                    merged["locked"] = bool(overrides["locked"])
                if overrides.get("role"):
                    merged["name"] = str(overrides.get("role", merged["name"]))
                merged["source"] = "pinmap"
                pins.append(merged)
            else:
                pins.append(dict(entry))
            seen_pins.add(pin_num)

        # Add pinmap-only pins (not in any net).
        for pin_num, overrides in pinmap_lookup.get(ref, {}).items():
            if pin_num in seen_pins:
                continue
            net_val = str(overrides.get("net", ""))
            pins.append({
                "number": pin_num,
                "name": str(overrides.get("role", "")),
                "net": net_val,
                "direction": "unspecified",
                "locked": bool(overrides.get("locked", False)),
                "source": "pinmap",
            })

        # Sort by pin number (numeric if possible).
        pins.sort(key=lambda p: _pin_sort_key(p["number"]))

        # selected_part — keep package as hardware fact.
        sp = component.get("selected_part")
        selected_part = dict(sp) if isinstance(sp, dict) else {}

        # Assigned sheet.
        assigned_sheet = str(component.get("sheet", ""))

        components.append({
            "ref": ref,
            "role": str(component.get("role", "")),
            "value": str(component.get("value", "")),
            "selected_part": {
                "part_id": str(selected_part.get("part_id", "")),
                "display_name": str(selected_part.get("display_name", "")),
                "mpn": str(selected_part.get("mpn", "")),
                "manufacturer": str(selected_part.get("manufacturer", "")),
                "lcsc_id": str(selected_part.get("lcsc_id", "")),
                "package": str(selected_part.get("package", "")),
                "mechanical_package": str(selected_part.get("mechanical_package", "")),
                "kicad_footprint_hint": str(selected_part.get("kicad_footprint_hint", "")),
            },
            "pins": pins,
            "assigned_sheet": assigned_sheet,
            "availability_status": str(component.get("availability_status", "unknown")),
            "notes": [str(n) for n in component.get("notes", [])] if isinstance(component.get("notes"), list) else [],
        })

    return components


def _build_nets(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise nets with kind, domain, flags."""
    nets: list[dict[str, Any]] = []
    for net in model.get("nets", []):
        if not isinstance(net, dict):
            continue
        name = str(net.get("name", "")).strip()
        if not name:
            continue
        kind = str(net.get("kind", _infer_net_kind(name)))
        flags = net.get("flags")
        nets.append({
            "name": name,
            "kind": kind,
            "members": [str(m) for m in net.get("members", [])],
            "domain": str(net.get("domain", "")),
            "flags": dict(flags) if isinstance(flags, dict) else {},
        })
    return nets


def _build_pinmap(model: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Collect per-component pin assignments from component.pinmap."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", ""))
        pm = component.get("pinmap")
        if isinstance(pm, dict) and pm:
            result[ref] = {}
            for pin, entry in pm.items():
                if isinstance(entry, dict):
                    result[ref][str(pin)] = {
                        "net": str(entry.get("net", "")),
                        "locked": bool(entry.get("locked", False)),
                        "role": str(entry.get("role", "")),
                    }
    return result


def _build_power_tree(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert power_rails[] into a power_tree[] with parent/child resolution."""
    rails = model.get("power_rails", [])
    if not isinstance(rails, list):
        return []
    rail_names = {
        str(r.get("name", ""))
        for r in rails
        if isinstance(r, dict)
    }
    tree: list[dict[str, Any]] = []
    for rail in rails:
        if not isinstance(rail, dict):
            continue
        name = str(rail.get("name", ""))
        parent = str(rail.get("parent", ""))
        children = [
            str(r.get("name", ""))
            for r in rails
            if isinstance(r, dict) and str(r.get("parent", "")) == name
        ]
        tree.append({
            "rail": name,
            "source_net": str(rail.get("source_net", "")),
            "voltage": float(rail.get("voltage", 0) or 0),
            "current_limit": float(rail.get("current_limit", 0) or 0),
            "parent": parent if parent in rail_names else "",
            "children": children,
            "sequence_order": int(rail.get("sequence_order", 0) or 0),
        })
    return tree


def _build_interfaces(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract interface definitions from constraints and sheets."""
    interfaces: list[dict[str, Any]] = []
    seen: set[str] = set()
    # From constraints of type "interface_definition".
    for c in model.get("constraints", []):
        if isinstance(c, dict) and str(c.get("type", "")) == "interface_definition":
            name = str(c.get("name", ""))
            if name and name not in seen:
                seen.add(name)
                interfaces.append({
                    "name": name,
                    "type": str(c.get("scope", "")),
                    "nets": _as_string_list(c.get("rules", [])),
                    "connector_ref": "",
                })
    # From sheets that represent external connectors.
    for s in model.get("sheets", []):
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", ""))
        if name and ("connector" in name.lower() or "interface" in name.lower()):
            if name not in seen:
                seen.add(name)
                interfaces.append({
                    "name": name,
                    "type": "connector",
                    "nets": _as_string_list(s.get("inputs", [])) + _as_string_list(s.get("outputs", [])),
                    "connector_ref": "",
                })
    return interfaces


def _validate_references(
    components: list[dict[str, Any]],
    nets: list[dict[str, Any]],
) -> None:
    """Raise ValueError if any net member references a non-existent component ref."""
    refs = {c["ref"] for c in components}
    for net in nets:
        for member in net.get("members", []):
            ref = str(member).split(".", 1)[0]
            if ref and ref not in refs:
                raise ValueError(
                    f"IR validation: net '{net['name']}' references missing component '{ref}'"
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_net_kind(name: str) -> str:
    """Heuristic net kind from name (portable, no KiCad dependency)."""
    n = name.upper().lstrip("+")
    if n in ("GND", "AGND", "DGND", "PGND", "VSS"):
        return "ground"
    if any(n.startswith(p) for p in ("VDD", "VCC", "VIO", "VIN", "VBUS", "VREF")):
        return "power"
    if n[0].isdigit() and "V" in n:
        return "power"
    return "signal"


def _pin_sort_key(number: str) -> tuple[int, str]:
    try:
        return (0, str(int(number)).zfill(4))
    except ValueError:
        return (1, number)


def _snapshot_list(items: Any) -> list[Any]:
    if not isinstance(items, list):
        return []
    return [dict(item) if isinstance(item, dict) else item for item in items]


def _as_string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item) for item in items]
