"""Generate KiCad PCB boards from execution plans."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import copy
from pathlib import Path
from typing import Any

from .kicad_cli import resolve_kicad_cli
from .kicad_symbol_library import parse_symbol_pin_map
from ..shared.env_utils import is_truthy_env
from ..shared.sexpr_parser import parse
from ..domain.core.netlist_builder import build_netlist


def _resolve_kicad_python() -> str:
    explicit = os.environ.get("KICAD_PYTHON_BIN", "")
    if explicit:
        return explicit
    cli = resolve_kicad_cli()
    if cli:
        candidate = Path(cli).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return ""


def _load_source_model(source_project_dir: str | Path | None) -> dict[str, Any]:
    if not source_project_dir:
        return {}
    root = Path(source_project_dir)
    for candidate in [
        root / "source" / "circuit-model.source.json",
        root / "circuit-model.source.json",
    ]:
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def _normalize_pin_key(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


def _semantic_pin_aliases(lib_id: str, pin_name: str) -> set[str]:
    normalized = _normalize_pin_key(pin_name)
    aliases = {normalized}
    if normalized in {"GND", "VSS"}:
        aliases.update({"GND", "VSS"})
    elif normalized in {"VCC", "VDD"}:
        aliases.update({"VCC", "VDD"})
    elif normalized in {"CS", "CE"}:
        aliases.update({"CS", "CE"})
    elif normalized in {"IO1", "I1"}:
        aliases.update({"IO1", "I1"})
    elif normalized in {"IO2", "I2"}:
        aliases.update({"IO2", "I2"})

    if lib_id.endswith("APS6404L-3SQR-SN_C5333729"):
        if normalized == "CS":
            aliases.update({"CE", "CE#"})
        elif normalized in {"VCC", "VDD"}:
            aliases.update({"VCC", "VDD"})
        elif normalized in {"GND", "VSS"}:
            aliases.update({"GND", "VSS"})
    return aliases


def _resolve_physical_pin_number(
    pin_name: str,
    pin_alias_map: dict[str, dict[str, Any]],
    lib_id: str,
) -> str:
    raw = str(pin_name).strip()
    if not raw:
        return ""
    if raw.isdigit():
        return raw
    resolved = pin_alias_map.get(raw) or pin_alias_map.get(raw.upper())
    if isinstance(resolved, dict):
        number = str(resolved.get("number", "")).strip()
        if number:
            return number
    raw_norm = _normalize_pin_key(raw)
    for alias in _semantic_pin_aliases(lib_id, raw):
        candidate = pin_alias_map.get(alias) or pin_alias_map.get(alias.upper())
        if isinstance(candidate, dict):
            number = str(candidate.get("number", "")).strip()
            if number:
                return number
    for info in pin_alias_map.values():
        if not isinstance(info, dict):
            continue
        number = str(info.get("number", "")).strip()
        name = str(info.get("name", "")).strip()
        if not number or not name:
            continue
        if _normalize_pin_key(name) == raw_norm:
            return number
        for alias in _semantic_pin_aliases(lib_id, raw):
            if _normalize_pin_key(name) == alias:
                return number
    return raw


def _source_netlist_symbol_pins(
    source_netlist: dict[str, Any],
    ref: str,
    lib_id: str,
    pin_alias_map: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    source_component = None
    for component in source_netlist.get("components", []):
        if isinstance(component, dict) and str(component.get("ref", "")).strip() == ref:
            source_component = component
            break
    if not isinstance(source_component, dict):
        return []
    resolved_pins: list[dict[str, str]] = []
    for pin in source_component.get("pins", []):
        if not isinstance(pin, dict):
            continue
        raw_pin = str(pin.get("pin", "")).strip()
        if not raw_pin:
            continue
        number = _resolve_physical_pin_number(raw_pin, pin_alias_map, lib_id)
        if not number:
            continue
        resolved_pins.append(
            {
                "number": number,
                "name": str(pin.get("pin_name", "")).strip(),
                "net": str(pin.get("net", "")).strip(),
            }
        )
    return resolved_pins


def _footprint_reference(footprint: Any) -> str:
    if not hasattr(footprint, "children"):
        return ""
    for child in footprint.children:
        if getattr(child, "tag", "") != "property":
            continue
        values = list(getattr(child, "values", []))
        if len(values) >= 2 and values[0] == "Reference":
            return str(values[1]).strip()
    return ""


def _expected_board_nets(plan: dict[str, Any]) -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for symbol in plan.get("symbols", []):
        if not isinstance(symbol, dict):
            continue
        ref = str(symbol.get("ref", "")).strip()
        if not ref:
            continue
        pad_map: dict[str, str] = {}
        for pin in symbol.get("pins", []):
            if not isinstance(pin, dict):
                continue
            net = str(pin.get("net", "")).strip()
            number = str(pin.get("number", "")).strip()
            if not net or not number:
                continue
            pad_map[number] = net
        if pad_map:
            expected[ref] = pad_map
    return expected


def _actual_board_nets(board_file: Path) -> dict[str, dict[str, str]]:
    board_text = board_file.read_text(encoding="utf-8")
    root = parse(board_text)
    actual: dict[str, dict[str, str]] = {}
    for footprint in root.find_all("footprint"):
        ref = _footprint_reference(footprint)
        if not ref:
            continue
        pad_map: dict[str, str] = {}
        for pad in footprint.find("pad"):
            pad_number = str(pad.values[0]).strip() if getattr(pad, "values", []) else ""
            if not pad_number:
                continue
            net_name = str(pad.get("net") or "").strip()
            if net_name:
                pad_map[pad_number] = net_name
        if pad_map:
            actual[ref] = pad_map
    return actual


def _validate_generated_board_nets(plan: dict[str, Any], board_file: Path) -> list[str]:
    if not board_file.is_file():
        return [f"PCB verification failed: board file not found at {board_file}."]

    expected = _expected_board_nets(plan)
    actual = _actual_board_nets(board_file)
    issues: list[str] = []

    for ref, expected_pads in expected.items():
        actual_pads = actual.get(ref, {})
        for pad_number, expected_net in expected_pads.items():
            actual_net = str(actual_pads.get(pad_number, "")).strip()
            if not actual_net:
                issues.append(f"{ref} pad {pad_number} expected net {expected_net} but the board file has no net.")
            elif actual_net != expected_net:
                issues.append(
                    f"{ref} pad {pad_number} expected net {expected_net} but the board file has {actual_net}."
                )
    return issues


def generate_board_from_plan(
    plan_file: str,
    project_dir: Path,
    source_project_dir: str | Path | None = None,
) -> dict[str, Any]:
    if not is_truthy_env("KICAD_GENERATE_PCB", "true"):
        return {"attempted": False, "enabled": False}
    python_bin = _resolve_kicad_python()
    if not python_bin:
        return {
            "attempted": True,
            "success": False,
            "warnings": ["KiCad Python was not found; PCB was not generated."],
        }
    try:
        plan_payload: dict[str, Any] = json.loads(Path(plan_file).read_text(encoding="utf-8"))
    except Exception:
        plan_payload = {}
    source_model = _load_source_model(source_project_dir)
    source_netlist = build_netlist(source_model) if source_model else {}
    board_plan = copy.deepcopy(plan_payload)
    if source_netlist and isinstance(board_plan.get("symbols"), list):
        previous_source_dir = os.environ.get("KICAD_SOURCE_PROJECT_DIR")
        previous_output_dir = os.environ.get("KICAD_OUTPUT_DIR")
        if source_project_dir:
            os.environ["KICAD_SOURCE_PROJECT_DIR"] = str(source_project_dir)
        os.environ["KICAD_OUTPUT_DIR"] = str(project_dir)
        for symbol in board_plan["symbols"]:
            if not isinstance(symbol, dict):
                continue
            ref = str(symbol.get("ref", "")).strip()
            lib_id = str(symbol.get("lib_id", "")).strip()
            pin_alias_map: dict[str, dict[str, Any]] = {}
            if lib_id:
                try:
                    pin_alias_map = parse_symbol_pin_map(lib_id)
                except Exception:
                    pin_alias_map = {}
            source_pins = _source_netlist_symbol_pins(source_netlist, ref, lib_id, pin_alias_map)
            if source_pins:
                symbol["pins"] = source_pins
        if previous_source_dir is None:
            os.environ.pop("KICAD_SOURCE_PROJECT_DIR", None)
        else:
            os.environ["KICAD_SOURCE_PROJECT_DIR"] = previous_source_dir
        if previous_output_dir is None:
            os.environ.pop("KICAD_OUTPUT_DIR", None)
        else:
            os.environ["KICAD_OUTPUT_DIR"] = previous_output_dir
    from .pcb_generator import _BOARD_SCRIPT

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as temp_script:
        temp_script.write(_BOARD_SCRIPT)
        script = temp_script.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as temp_plan:
        json.dump(board_plan, temp_plan)
        temp_plan_path = temp_plan.name
    try:
        board_file = project_dir / f"{project_dir.name}.kicad_pcb"
        source_project_arg = str(source_project_dir or "")
        process = subprocess.run(
            [python_bin, script, temp_plan_path, str(board_file), source_project_arg],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    finally:
        try:
            Path(script).unlink()
        except OSError:
            pass
        try:
            Path(temp_plan_path).unlink()
        except OSError:
            pass
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(process.stdout)
    except Exception:
        payload = {}
    warnings: list[str] = []
    if process.stderr:
        warnings.append(process.stderr.strip())
    if process.returncode != 0:
        warnings.append(process.stdout.strip() or "PCB generation failed.")
    if payload.get("skipped"):
        warnings.extend(str(item) for item in payload.get("skipped", []))
    verification_errors = _validate_generated_board_nets(board_plan, board_file) if process.returncode == 0 else []
    if verification_errors:
        warnings.extend(verification_errors)
    return {
        "attempted": True,
        "success": process.returncode == 0 and not verification_errors,
        "return_code": process.returncode,
        "python": python_bin,
        "board_file": payload.get("board", str(board_file)),
        "footprints": int(payload.get("footprints", 0) or 0),
        "nets": int(payload.get("nets", 0) or 0),
        "verification_errors": verification_errors,
        "warnings": warnings,
    }
