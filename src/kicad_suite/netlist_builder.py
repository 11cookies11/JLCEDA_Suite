"""Build netlist payloads from circuit-model data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .compile_kicad_execution_plan import normalize_net_kind


def build_netlist(model: dict[str, Any]) -> dict[str, Any]:
    """Build a netlist dict from the circuit model's nets and components."""
    request_id = str(model.get("request_id", ""))
    project_id = str(model.get("project_id", request_id))
    pin_by_ref: dict[str, list[dict[str, str]]] = defaultdict(list)
    for net in model.get("nets", []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get("name", ""))
        for member in net.get("members", []):
            member_str = str(member).strip()
            if "." in member_str:
                ref, pin = member_str.rsplit(".", 1)
                if ref and pin:
                    pin_by_ref[ref].append({"pin": pin, "pin_name": "", "net": net_name})

    components: list[dict[str, Any]] = []
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        ref = str(component.get("ref", "")).strip()
        if not ref:
            continue
        selected_part = component.get("selected_part", {})
        part = selected_part if isinstance(selected_part, dict) else {}
        components.append(
            {
                "ref": ref,
                "role": str(component.get("role", "")),
                "value": str(component.get("value", "")),
                "part": {
                    "part_id": str(part.get("part_id", "")),
                    "display_name": str(part.get("display_name", "")),
                    "library_uuid": str(part.get("library_uuid", "")),
                    "symbol_uuid": str(part.get("symbol_uuid", "")),
                    "pin_count": int(part.get("pin_count", 0) or 0),
                    "named_pin_count": int(part.get("named_pin_count", 0) or 0),
                },
                "pins": sorted(pin_by_ref.get(ref, []), key=lambda item: item.get("pin", "")),
                "availability_status": str(component.get("availability_status", "unknown")),
            }
        )

    nets: list[dict[str, Any]] = []
    for net in model.get("nets", []):
        if not isinstance(net, dict):
            continue
        net_name = str(net.get("name", "")).strip()
        if not net_name:
            continue
        nets.append(
            {
                "name": net_name,
                "kind": str(net.get("kind", normalize_net_kind(net_name))),
                "members": [str(member) for member in net.get("members", [])],
            }
        )

    return {
        "schema_version": "netlist.v1",
        "request_id": request_id,
        "project_id": project_id,
        "source_model": {
            "schema_version": str(model.get("schema_version", "")),
            "request_id": request_id,
        },
        "components": components,
        "nets": nets,
    }
