"""Circuit sanity gate — catch obviously-wrong connections in DSL models.

This is a pure-data checker.  It does NOT use an LLM — it walks the
structured ``components`` + ``nets`` + ``members`` data and applies
simple electrical rules.
"""

from __future__ import annotations

from typing import Any

from ....shared.validation.common import ValidationReport


_POWER_NET_KINDS = {"power", "ground"}
_PASSIVE_KINDS = {"resistor", "capacitor", "inductor", "ferrite_bead", "fuse", "jumper"}


def run(components: list[dict[str, Any]], nets: list[dict[str, Any]]) -> ValidationReport:
    """Check *components* and *nets* for basic electrical mistakes.

    Returns a ``ValidationReport`` whose ``errors`` list is non-empty
    when hard faults (short-circuits, bypassed passives) are found.
    """
    report = ValidationReport()

    net_by_name, pin_to_nets = _index_nets(nets)
    errors_found = 0

    # ---- 1. Pin assigned to multiple different nets (short circuit) ----
    for pin_ref, assigned_nets in pin_to_nets.items():
        unique = list(dict.fromkeys(assigned_nets))
        if len(unique) > 1:
            report.add_error(
                f"SHORT CIRCUIT: {pin_ref} is connected to multiple nets: "
                f"{', '.join(unique)}. Remove it from all but one net."
            )
            errors_found += 1

    # ---- 2. Passive two-pin component sanity ----
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ref = str(comp.get("ref", ""))
        role = str(comp.get("role", "")).lower()
        value = str(comp.get("value", "")).lower()

        if not _looks_like_passive(ref, role):
            continue

        comp_pins = _component_pin_nets(ref, net_by_name)
        nets_on_comp = list(comp_pins.values())
        unique_nets = list(dict.fromkeys(nets_on_comp))

        # 2a. All pins on the same net → component is bypassed
        if len(nets_on_comp) >= 2 and len(unique_nets) == 1:
            report.add_error(
                f"BYPASSED {ref}: all pins connected to the same net "
                f"[{unique_nets[0]}]. The component is electrically meaningless."
            )
            errors_found += 1

        # 2b. Resistor between two power/ground nets with no signal path
        if _should_check_power_short(ref, role, unique_nets):
            net_kinds = [
                str(net_by_name.get(n, {}).get("kind", "")).lower()
                for n in unique_nets
            ]
            both_power = all(k in _POWER_NET_KINDS for k in net_kinds if k)
            if both_power and len(unique_nets) == 2 and not _is_intentional_link(value, role):
                report.add_warning(
                    f"SUSPICIOUS {ref} ({role}): connects {unique_nets[0]} directly "
                    f"to {unique_nets[1]} with no signal path. "
                    f"If intended as pull-up/down, one pin must go to a signal net."
                )

        # 2c. Pullup / pulldown role sanity
        if "pullup" in role:
            if not _any_pin_on_kind(comp_pins, net_by_name, "power"):
                report.add_warning(
                    f"PULLUP WITHOUT POWER: {ref} role is pullup but "
                    f"neither pin is on a power net."
                )
        if "pulldown" in role:
            if not _any_pin_on_kind(comp_pins, net_by_name, "ground"):
                report.add_warning(
                    f"PULLDOWN WITHOUT GND: {ref} role is pulldown but "
                    f"neither pin is on a ground net."
                )

    # ---- 3. Done ----
    if errors_found == 0:
        report.add_check("circuit sanity ok")
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index_nets(
    nets: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Build ``net_by_name`` and ``pin_to_nets`` lookup tables."""
    net_by_name: dict[str, dict[str, Any]] = {}
    pin_to_nets: dict[str, list[str]] = {}
    for net in nets:
        if not isinstance(net, dict):
            continue
        name = str(net.get("name", ""))
        if not name:
            continue
        net_by_name[name] = net
        for member in net.get("members", []):
            member_str = str(member)
            if "." not in member_str:
                continue
            pin_to_nets.setdefault(member_str, []).append(name)
    return net_by_name, pin_to_nets


def _looks_like_passive(ref: str, role: str) -> bool:
    """Return True if the component is probably a two-pin passive."""
    if any(kw in role for kw in _PASSIVE_KINDS):
        return True
    if ref and ref[0] in "RCL":
        return True
    return False


def _component_pin_nets(
    ref: str, net_by_name: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Return ``{pin_number: net_name}`` for *ref*."""
    pins: dict[str, str] = {}
    prefix = f"{ref}."
    for net_name, net in net_by_name.items():
        for member in net.get("members", []):
            if str(member).startswith(prefix):
                pin = str(member).split(".", 1)[1]
                pins[pin] = net_name
    return pins


def _should_check_power_short(
    ref: str, role: str, unique_nets: list[str]
) -> bool:
    """Return True if this resistor's connections warrant a power-short check."""
    if len(unique_nets) != 2:
        return False
    if "pullup" in role or "pulldown" in role:
        return True
    if ref.startswith("R"):
        return True
    return False


def _any_pin_on_kind(
    comp_pins: dict[str, str],
    net_by_name: dict[str, dict[str, Any]],
    kind: str,
) -> bool:
    """Return True if any pin of the component is on a net of *kind*."""
    for net_name in comp_pins.values():
        net_kind = str(net_by_name.get(net_name, {}).get("kind", "")).lower()
        if net_kind == kind:
            return True
    return False


def _is_intentional_link(value: str, role: str) -> bool:
    """Return True if a two-pin passive between power rails is intentional."""
    value_lower = value.lower()
    role_lower = role.lower()
    if value_lower in {"0r", "0ω", "0 ohm", "0ohm", "0r0", "0"}:
        return True
    for keyword in ("link", "jumper", "current_meas", "current-meas", "isolation"):
        if keyword in role_lower:
            return True
    return False
