#!/usr/bin/env python3
"""Hardware semantic gate for KiCad Agent Suite projects.

This script is intentionally conservative: it does not try to replace KiCad ERC.
It derives sidecar artifacts from source/circuit-model.source.json and blocks
export when common hardware-topology mistakes are detected before KiCad is built.

Generated artifacts:
  build/net-intents.v1.json
  build/pin-contracts.v1.json
  build/hardware-erc.v1.json
  build/export-gate.v1.json

Usage:
  python scripts/hardware_semantic_gate.py --project .
  python scripts/hardware_semantic_gate.py --project . --no-fail
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    component: str | None = None
    pin: str | None = None
    net: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "component": self.component,
            "pin": self.pin,
            "net": self.net,
            "suggestion": self.suggestion,
        }.items() if v is not None}


@dataclass
class ModelIndex:
    model: dict[str, Any]
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    nets: dict[str, dict[str, Any]] = field(default_factory=dict)
    member_to_net: dict[tuple[str, str], str] = field(default_factory=dict)
    ref_members: dict[str, dict[str, str]] = field(default_factory=dict)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _member_parts(member: str) -> tuple[str, str] | None:
    if not isinstance(member, str) or "." not in member:
        return None
    ref, pin = member.split(".", 1)
    ref = ref.strip()
    pin = pin.strip()
    if not ref or not pin:
        return None
    return ref, pin


def build_index(model: dict[str, Any]) -> ModelIndex:
    idx = ModelIndex(model=model)
    for comp in model.get("components", []) or []:
        ref = str(comp.get("ref", "")).strip()
        if ref:
            idx.components[ref] = comp
            idx.ref_members.setdefault(ref, {})
    for net in model.get("nets", []) or []:
        name = str(net.get("name", "")).strip()
        if not name:
            continue
        idx.nets[name] = net
        for member in net.get("members", []) or []:
            parsed = _member_parts(str(member))
            if not parsed:
                continue
            ref, pin = parsed
            idx.member_to_net[(ref, pin)] = name
            idx.ref_members.setdefault(ref, {})[pin] = name
    return idx


def _text(comp: dict[str, Any]) -> str:
    selected = comp.get("selected_part") if isinstance(comp.get("selected_part"), dict) else {}
    fields = [
        comp.get("ref"), comp.get("role"), comp.get("value"), comp.get("package"),
        selected.get("display_name"), selected.get("mpn"), selected.get("lcsc_id"),
    ]
    return " ".join(str(x or "") for x in fields).lower()


def classify_component(comp: dict[str, Any]) -> str | None:
    t = _text(comp)
    if "tps22918" in t or "load_switch" in t or "power_switch" in t:
        return "load_switch"
    if "bq24074" in t or "bq2407" in t or "power_path" in t or "liion_charger" in t or "charger" in t:
        return "charger_power_path"
    if ("usb" in t and "type" in t and "c" in t) or "usb-c" in t or "usbc" in t:
        return "usb_c_sink_usb2"
    if "epd" in t or "epaper" in t or "e-paper" in t or "e paper" in t or "e_ink" in t:
        return "epaper_spi_connector"
    return None


def _component_pin_net(idx: ModelIndex, ref: str, pin: str) -> str | None:
    return idx.ref_members.get(ref, {}).get(pin)


def _has_pin(idx: ModelIndex, ref: str, pin: str) -> bool:
    return _component_pin_net(idx, ref, pin) is not None


def _net_members(idx: ModelIndex, net_name: str) -> list[str]:
    net = idx.nets.get(net_name, {})
    return list(net.get("members", []) or [])


def _is_gnd(net_name: str | None) -> bool:
    return bool(net_name) and net_name.upper() in {"GND", "GNDA", "DGND", "AGND", "VSS"}


def _is_resistor(comp: dict[str, Any]) -> bool:
    t = _text(comp)
    ref = str(comp.get("ref", ""))
    return ref.startswith("R") or "resistor" in t or "pull" in t or "5.1k" in t or "5k1" in t


def _is_capacitor(comp: dict[str, Any]) -> bool:
    t = _text(comp)
    ref = str(comp.get("ref", ""))
    return ref.startswith("C") or "capacitor" in t or "cap" in t or "decoupling" in t


def _is_test_point(comp: dict[str, Any]) -> bool:
    t = _text(comp)
    ref = str(comp.get("ref", ""))
    return ref.startswith("TP") or "test_point" in t or "test point" in t


def _is_real_load_member(idx: ModelIndex, member: str, source_ref: str, source_pin: str) -> bool:
    parsed = _member_parts(member)
    if not parsed:
        return False
    ref, pin = parsed
    if ref == source_ref and pin == source_pin:
        return False
    comp = idx.components.get(ref, {})
    if _is_resistor(comp) or _is_capacitor(comp) or _is_test_point(comp):
        return False
    return True


def _resistor_to_gnd(idx: ModelIndex, net_name: str) -> bool:
    for member in _net_members(idx, net_name):
        parsed = _member_parts(member)
        if not parsed:
            continue
        ref, pin = parsed
        comp = idx.components.get(ref, {})
        if not _is_resistor(comp):
            continue
        for other_pin, other_net in idx.ref_members.get(ref, {}).items():
            if other_pin != pin and _is_gnd(other_net):
                return True
    return False


def add(f: list[Finding], severity: str, code: str, message: str, **kwargs: Any) -> None:
    f.append(Finding(severity=severity, code=code, message=message, **kwargs))


def contract_pin(ref: str, pin: str, name: str, pin_type: str, net: str | None, required: bool, *,
                 allowed_nc: bool = False, rationale: str = "", checks: list[str] | None = None,
                 default_state: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pin": pin,
        "name": name,
        "pin_type": pin_type,
        "required": required,
        "connection": "net" if net else "unresolved",
        "allowed_nc": allowed_nc,
        "rationale": rationale,
    }
    if net:
        payload["net"] = net
    if checks:
        payload["checks"] = checks
    if default_state:
        payload["default_state"] = default_state
    return payload


def check_load_switch(idx: ModelIndex, comp: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    ref = comp["ref"]
    pin_defs = {
        "1": ("VIN", "power_input", True, False, "load switch upstream power input"),
        "2": ("GND", "ground", True, False, "device ground"),
        "3": ("ON", "enable_input", True, False, "logic enable; must not float"),
        "4": ("CT", "config_pin", False, True, "optional slew-rate control; explicit NC or capacitor to GND"),
        "5": ("QOD", "config_pin", False, True, "optional quick output discharge strategy"),
        "6": ("VOUT", "power_output", True, False, "switched load output"),
    }
    pins = []
    for pin, (name, ptype, required, allowed_nc, rationale) in pin_defs.items():
        net = _component_pin_net(idx, ref, pin)
        pins.append(contract_pin(ref, pin, name, ptype, net, required, allowed_nc=allowed_nc, rationale=rationale))
        if required and not net:
            add(findings, "BLOCKER", "LOAD_SWITCH_REQUIRED_PIN_UNRESOLVED",
                f"{ref}.{name} must be connected.", component=ref, pin=pin,
                suggestion=f"Connect {ref}.{name} according to the load-switch topology.")
    vin = _component_pin_net(idx, ref, "1")
    vout = _component_pin_net(idx, ref, "6")
    on = _component_pin_net(idx, ref, "3")
    if vin and vout and vin == vout:
        add(findings, "BLOCKER", "LOAD_SWITCH_VIN_VOUT_SHORTED",
            f"{ref}.VIN and {ref}.VOUT are on the same net {vin}; this bypasses the load switch.", component=ref, net=vin)
    if vout:
        external_loads = [m for m in _net_members(idx, vout) if _is_real_load_member(idx, m, ref, "6")]
        if not external_loads:
            add(findings, "BLOCKER", "LOAD_SWITCH_OUTPUT_WITHOUT_LOAD",
                f"{ref}.VOUT net {vout} has no real downstream load.", component=ref, pin="6", net=vout)
    if on:
        add(findings, "WARNING", "ENABLE_DEFAULT_STATE_REVIEW_REQUIRED",
            f"{ref}.ON is connected to {on}; ensure reset default state is defined, usually with a pulldown.",
            component=ref, pin="3", net=on,
            suggestion="Add a 100k pulldown or document MCU reset state.")
    return {"component_ref": ref, "part": comp.get("value"), "category": "load_switch", "pins": pins}


def check_charger(idx: ModelIndex, comp: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    ref = comp["ref"]
    pin_defs = {
        "1": ("TS", "temperature_sense", True, False, "battery NTC or fixed valid temperature strategy"),
        "2": ("BAT", "battery_power", True, False, "battery positive terminal"),
        "3": ("BAT", "battery_power", True, False, "battery positive terminal"),
        "4": ("CE", "enable_input", True, False, "charge enable default state"),
        "5": ("EN2", "mode_select", True, False, "input current mode select"),
        "6": ("EN1", "mode_select", True, False, "input current mode select"),
        "7": ("PGOOD", "open_drain_status", False, True, "power-good status; pull up if used"),
        "8": ("VSS", "ground", True, False, "device ground"),
        "9": ("CHG", "open_drain_status", False, True, "charge status; pull up if used"),
        "10": ("OUT", "system_power_output", True, False, "system output"),
        "11": ("OUT", "system_power_output", True, False, "system output"),
        "12": ("ILIM", "program_pin", True, False, "input current limit resistor to VSS"),
        "13": ("IN", "power_input", True, False, "USB or adapter input"),
        "14": ("TMR", "timer_config", False, True, "timer strategy"),
        "15": ("ITERM", "program_pin", False, True, "termination current strategy"),
        "16": ("ISET", "program_pin", True, False, "charge current setting resistor to VSS"),
        "17": ("EP", "thermal_pad", True, False, "exposed pad tied to VSS/GND copper"),
        "EP": ("EP", "thermal_pad", True, False, "exposed pad tied to VSS/GND copper"),
    }
    pins = []
    for pin, (name, ptype, required, allowed_nc, rationale) in pin_defs.items():
        net = _component_pin_net(idx, ref, pin)
        # Accept either numeric 17 or symbolic EP for the exposed pad.
        if pin == "17" and not net:
            net = _component_pin_net(idx, ref, "EP")
        if pin == "EP" and _component_pin_net(idx, ref, "17"):
            continue
        pins.append(contract_pin(ref, pin, name, ptype, net, required, allowed_nc=allowed_nc, rationale=rationale))
        if required and not net:
            add(findings, "BLOCKER", "CHARGER_REQUIRED_PIN_UNRESOLVED",
                f"{ref}.{name} pin {pin} must be connected or explicitly configured.", component=ref, pin=pin)
    bat2 = _component_pin_net(idx, ref, "2")
    bat3 = _component_pin_net(idx, ref, "3")
    if bat2 and bat3 and bat2 != bat3:
        add(findings, "BLOCKER", "CHARGER_BAT_PINS_NOT_COMMONED",
            f"{ref}.BAT pins 2 and 3 must be on the same battery net.", component=ref)
    if bool(bat2) != bool(bat3):
        add(findings, "BLOCKER", "CHARGER_BAT_DUPLICATE_PIN_MISSING",
            f"{ref}.BAT pins 2 and 3 must both be connected.", component=ref)
    out10 = _component_pin_net(idx, ref, "10")
    out11 = _component_pin_net(idx, ref, "11")
    if out10 and out11 and out10 != out11:
        add(findings, "BLOCKER", "CHARGER_OUT_PINS_NOT_COMMONED",
            f"{ref}.OUT pins 10 and 11 must be on the same system rail.", component=ref)
    if bool(out10) != bool(out11):
        add(findings, "BLOCKER", "CHARGER_OUT_DUPLICATE_PIN_MISSING",
            f"{ref}.OUT pins 10 and 11 must both be connected.", component=ref)
    ep = _component_pin_net(idx, ref, "17") or _component_pin_net(idx, ref, "EP")
    if ep and not _is_gnd(ep):
        add(findings, "BLOCKER", "CHARGER_EP_NOT_GND",
            f"{ref}.EP is on {ep}; exposed pad should be tied to VSS/GND unless the datasheet says otherwise.", component=ref, net=ep)
    return {"component_ref": ref, "part": comp.get("value"), "category": "charger_power_path", "pins": pins}


def check_usb_c_sink(idx: ModelIndex, comp: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    ref = comp["ref"]
    pins = []
    groups = {
        "VBUS": ["A4", "A9", "B4", "B9"],
        "GND": ["A1", "A12", "B1", "B12"],
        "D+": ["A6", "B6"],
        "D-": ["A7", "B7"],
    }
    for name, pin_list in groups.items():
        nets = [_component_pin_net(idx, ref, pin) for pin in pin_list]
        for pin, net in zip(pin_list, nets):
            pins.append(contract_pin(ref, pin, name, "connector_pin", net, True, rationale=f"USB-C {name} pin"))
            if not net:
                add(findings, "BLOCKER", "USB_C_REQUIRED_PIN_UNRESOLVED",
                    f"{ref}.{pin} ({name}) must be connected.", component=ref, pin=pin)
        present = [n for n in nets if n]
        if present and len(set(present)) > 1:
            add(findings, "BLOCKER", "USB_C_DUPLICATE_PINS_NOT_COMMONED",
                f"{ref} {name} pins must be tied to the same net.", component=ref)
    for pin, name in [("A5", "CC1"), ("B5", "CC2")]:
        net = _component_pin_net(idx, ref, pin)
        pins.append(contract_pin(ref, pin, name, "configuration_channel", net, True, rationale="USB-C sink Rd detect"))
        if not net:
            add(findings, "BLOCKER", "USB_C_CC_UNCONNECTED",
                f"{ref}.{name} must be connected to an Rd pulldown network.", component=ref, pin=pin)
        elif not _resistor_to_gnd(idx, net):
            add(findings, "BLOCKER", "USB_C_CC_MISSING_RD",
                f"{ref}.{name} net {net} does not show a resistor path to GND.", component=ref, pin=pin, net=net,
                suggestion="Add 5.1kΩ Rd from CC1/CC2 to GND for a USB-C Sink/UFP.")
    for pin, name in [("A8", "SBU1"), ("B8", "SBU2")]:
        net = _component_pin_net(idx, ref, pin)
        pins.append(contract_pin(ref, pin, name, "sideband", net, False, allowed_nc=True,
                                 rationale="SBU may be explicit NC for USB2-only designs"))
    return {"component_ref": ref, "part": comp.get("value"), "category": "usb_c_sink_usb2", "pins": pins}


def check_epaper(idx: ModelIndex, comp: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    ref = comp["ref"]
    expected = {
        "1": ("SCLK", "spi_clock"),
        "2": ("MOSI", "spi_mosi"),
        "3": ("CS", "chip_select"),
        "4": ("DC", "gpio_output"),
        "5": ("RST", "reset"),
        "6": ("BUSY", "status_input"),
        "7": ("VCC", "power_input"),
        "8": ("GND", "ground"),
    }
    pins = []
    for pin, (name, ptype) in expected.items():
        net = _component_pin_net(idx, ref, pin)
        pins.append(contract_pin(ref, pin, name, ptype, net, True, rationale=f"e-paper SPI connector {name}"))
        if not net:
            add(findings, "BLOCKER", "EPAPER_REQUIRED_PIN_UNRESOLVED",
                f"{ref}.{name} pin {pin} must be connected for the SPI e-paper interface.", component=ref, pin=pin)
    for pin, name in [("9", "PWR_EN"), ("10", "MODE")]:
        net = _component_pin_net(idx, ref, pin)
        pins.append(contract_pin(ref, pin, name, "optional_or_module_specific", net, False, allowed_nc=True,
                                 rationale="Module-specific pin; requires explicit strategy when present in the symbol."))
        if name == "MODE" and not net and any(_has_pin(idx, ref, p) for p in ["1", "2", "3", "4", "5", "6", "7", "8", "9"]):
            add(findings, "WARNING", "EPAPER_MODE_STRATEGY_REVIEW_REQUIRED",
                f"{ref}.MODE is not connected; confirm the module datasheet says it may be left NC.", component=ref, pin=pin)
    vcc = _component_pin_net(idx, ref, "7")
    if vcc and not ("3V3" in vcc.upper() or "VCC" in vcc.upper() or "EPD" in vcc.upper()):
        add(findings, "WARNING", "EPAPER_SUPPLY_REVIEW_REQUIRED",
            f"{ref}.VCC is on {vcc}; confirm voltage is compatible, typically 3.3V.", component=ref, pin="7", net=vcc)
    return {"component_ref": ref, "part": comp.get("value"), "category": "epaper_spi_connector", "pins": pins}


def derive_pin_contracts(idx: ModelIndex, findings: list[Finding]) -> list[dict[str, Any]]:
    contracts = []
    for ref, comp in idx.components.items():
        comp = dict(comp)
        comp["ref"] = ref
        category = classify_component(comp)
        if category == "load_switch":
            contracts.append(check_load_switch(idx, comp, findings))
        elif category == "charger_power_path":
            contracts.append(check_charger(idx, comp, findings))
        elif category == "usb_c_sink_usb2":
            contracts.append(check_usb_c_sink(idx, comp, findings))
        elif category == "epaper_spi_connector":
            contracts.append(check_epaper(idx, comp, findings))
    return contracts


def derive_net_intents(idx: ModelIndex) -> list[dict[str, Any]]:
    intents = []
    for name, net in idx.nets.items():
        members = list(net.get("members", []) or [])
        kind = str(net.get("kind", "") or "unknown")
        source_candidates = []
        load_candidates = []
        for member in members:
            parsed = _member_parts(member)
            if not parsed:
                continue
            ref, pin = parsed
            comp = idx.components.get(ref, {})
            category = classify_component(comp)
            if category == "load_switch" and pin == "6":
                source_candidates.append({"component": ref, "pin": pin, "role": "load_switch_output"})
            elif category == "charger_power_path" and pin in {"10", "11"}:
                source_candidates.append({"component": ref, "pin": pin, "role": "charger_system_output"})
            elif category == "load_switch" and pin == "1":
                load_candidates.append({"component": ref, "pin": pin, "role": "load_switch_input"})
            else:
                load_candidates.append({"component": ref, "pin": pin})
        intent: dict[str, Any] = {
            "name": name,
            "kind": kind,
            "members": members,
            "source_candidates": source_candidates,
            "load_candidates": load_candidates,
        }
        if name.upper() in {"GND", "VSS", "AGND", "DGND"}:
            intent["net_intent"] = "ground_reference"
        elif kind == "power" or re.search(r"(^|_)(3V3|5V|VSYS|VBUS|BAT|VCC|VIN|VOUT)(_|$)", name.upper()):
            intent["net_intent"] = "power_distribution"
        else:
            intent["net_intent"] = "signal_or_configuration"
        intents.append(intent)
    return intents


def build_outputs(project_path: Path, no_fail: bool = False) -> int:
    source_path = project_path / "source" / "circuit-model.source.json"
    build_path = project_path / "build"
    if not source_path.exists():
        print(f"source model not found: {source_path}", file=sys.stderr)
        return 2
    model = _read_json(source_path)
    idx = build_index(model)
    findings: list[Finding] = []
    pin_contracts = derive_pin_contracts(idx, findings)
    net_intents = derive_net_intents(idx)

    blockers = [f.to_dict() for f in findings if f.severity == "BLOCKER"]
    warnings = [f.to_dict() for f in findings if f.severity == "WARNING"]
    infos = [f.to_dict() for f in findings if f.severity == "INFO"]

    project_id = str(model.get("project_id") or project_path.name)
    topology = str(model.get("topology") or project_id.replace("-", "_"))

    _write_json(build_path / "pin-contracts.v1.json", {
        "schema_version": "pin-contracts.v1",
        "project_id": project_id,
        "topology": topology,
        "source_model": "source/circuit-model.source.json",
        "contracts": pin_contracts,
    })
    _write_json(build_path / "net-intents.v1.json", {
        "schema_version": "net-intents.v1",
        "project_id": project_id,
        "topology": topology,
        "source_model": "source/circuit-model.source.json",
        "nets": net_intents,
    })
    erc_payload = {
        "schema_version": "hardware-erc.v1",
        "project_id": project_id,
        "topology": topology,
        "ok": len(blockers) == 0,
        "summary": {"blockers": len(blockers), "warnings": len(warnings), "infos": len(infos)},
        "blockers": blockers,
        "warnings": warnings,
        "infos": infos,
    }
    _write_json(build_path / "hardware-erc.v1.json", erc_payload)
    decision = "allow_export_kicad" if not blockers else "block_export_kicad"
    _write_json(build_path / "export-gate.v1.json", {
        "schema_version": "export-gate.v1",
        "project_id": project_id,
        "topology": topology,
        "inputs": {
            "source_model": "source/circuit-model.source.json",
            "pin_contracts": "build/pin-contracts.v1.json",
            "net_intents": "build/net-intents.v1.json",
            "hardware_erc": "build/hardware-erc.v1.json",
        },
        "gate": {"hardware_erc_blockers": len(blockers), "hardware_erc_warnings": len(warnings)},
        "decision": decision,
    })

    print(json.dumps({"ok": not blockers, "decision": decision, "blockers": len(blockers), "warnings": len(warnings)}, ensure_ascii=False, indent=2))
    return 0 if no_fail or not blockers else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Hardware Semantic Gate v0.1")
    parser.add_argument("--project", default=".", help="Project directory containing source/circuit-model.source.json")
    parser.add_argument("--no-fail", action="store_true", help="Write reports but return zero even when blockers exist")
    args = parser.parse_args(argv)
    return build_outputs(Path(args.project).resolve(), no_fail=args.no_fail)


if __name__ == "__main__":
    raise SystemExit(main())
