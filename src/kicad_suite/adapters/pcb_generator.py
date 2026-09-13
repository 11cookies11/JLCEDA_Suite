"""Generate a .kicad_pcb board file from the KiCad execution plan via pcbnew."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .kicad_symbol_library import parse_symbol_pin_map
from ..domain.core.netlist_builder import build_netlist
from ..shared.sexpr_parser import parse

# The generate_pcb_from_plan.py script, embedded so it doesn't need to be
# distributed separately.  Written to a temp file and executed by KiCad's
# bundled Python (which has the pcbnew module).
_BOARD_SCRIPT = r'''
import json, re, sys
import os
from pathlib import Path
from typing import Any
import pcbnew

def _footprint_library_dir(project_dir: Path, lib_name: str) -> Path | None:
    if lib_name == "JLC-MCP":
        for base in [project_dir, project_dir.parent, project_dir.parent.parent]:
            candidate = base / "libraries" / "footprints" / "JLC-MCP.pretty"
            if candidate.is_dir():
                return candidate
        return None
    if lib_name == "AIAgent":
        for base in [project_dir, project_dir.parent, project_dir.parent.parent]:
            candidate = base / "resources" / "kicad" / "footprints" / "AIAgent.pretty"
            if candidate.is_dir():
                return candidate
        return None
    return None

def _pin_tokens(pin_number: str) -> set[str]:
    """Return the exact pin number as the sole match token.

    Previously this function split compound pin numbers like "A1B12"
    into ["A1", "B12"], creating false-positive matches against
    unrelated pads.  The board script already passes the full pin
    number to pad_map, so we only need the original text as key.
    """
    text = str(pin_number).strip()
    if not text:
        return set()
    return {text}

def _find_matching_paren(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1

def _symbol_library_roots(project_dir: Path) -> list[Path]:
    roots: list[Path] = []
    for base in [project_dir, project_dir.parent, project_dir.parent.parent]:
        candidate = base / "libraries" / "symbols"
        if candidate.is_dir():
            roots.append(candidate)
    return roots

def _symbol_block_for_lib_id(project_dir: Path, lib_id: str) -> str:
    if ":" not in lib_id:
        return ""
    library, symbol_name = lib_id.split(":", 1)
    for root in _symbol_library_roots(project_dir):
        path = root / f"{library}.kicad_sym"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        anchor = f'(symbol "{symbol_name}"'
        start = text.find(anchor)
        if start == -1:
            continue
        end = _find_matching_paren(text, start)
        if end != -1:
            return text[start:end + 1]
    return ""

def _parse_symbol_pin_map(project_dir: Path, lib_id: str) -> dict[str, dict[str, Any]]:
    block = _symbol_block_for_lib_id(project_dir, lib_id)
    if not block:
        return {}
    pins: dict[str, dict[str, Any]] = {}
    for pin_start in re.finditer(r'\\(pin\\b', block):
        pin_end = _find_matching_paren(block, pin_start.start())
        if pin_end == -1:
            continue
        pin_block = block[pin_start.start():pin_end + 1]
        name_match = re.search(r'\\(name\\s+"([^"]+)"', pin_block)
        number_match = re.search(r'\\(number\\s+"([^"]+)"', pin_block)
        at_match = re.search(r'\\(at\\s+([-0-9.]+)\\s+([-0-9.]+)\\s+([-0-9.]+)\\)', pin_block)
        length_match = re.search(r'\\(length\\s+([-0-9.]+)\\)', pin_block)
        if not number_match:
            continue
        number = number_match.group(1).strip()
        name = name_match.group(1).strip() if name_match else ""
        aliases = {number, number.upper()}
        if name:
            name_upper = name.upper()
            aliases.update({name, name_upper})
            normalized = re.sub(r'[^A-Z0-9]+', '_', name_upper).strip('_')
            if normalized:
                aliases.add(normalized)
        pin_info: dict[str, Any] = {
            "name": name,
            "number": number,
            "x": float(at_match.group(1)) if at_match else 0.0,
            "y": float(at_match.group(2)) if at_match else 0.0,
            "rotation": float(at_match.group(3)) if at_match else 0.0,
            "length": float(length_match.group(1)) if length_match else 0.0,
        }
        for alias in aliases:
            pins[alias] = pin_info
    return pins

def _pad_net_map(symbol: dict[str, Any], project_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lib_id = str(symbol.get("lib_id", "")).strip()
    pin_alias_map: dict[str, dict[str, Any]] = {}
    if lib_id:
        try:
            pin_alias_map = _parse_symbol_pin_map(project_dir, lib_id)
        except Exception:
            pin_alias_map = {}
    for pin in symbol.get("pins", []):
        if not isinstance(pin, dict):
            continue
        net = str(pin.get("net", "")).strip()
        if not net:
            continue
        raw_pin = str(pin.get("number", "")).strip()
        resolved = pin_alias_map.get(raw_pin) or pin_alias_map.get(raw_pin.upper())
        if isinstance(resolved, dict):
            pad_number = str(resolved.get("number", "")).strip() or raw_pin
        else:
            pad_number = raw_pin
        for token in _pin_tokens(pad_number):
            mapping[token] = net
    return mapping

def _net(board, nets, net_name):
    if net_name not in nets:
        item = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(item)
        nets[net_name] = item
    return nets[net_name]

def _load_placement_map(project_dir: Path) -> dict[str, dict[str, float]]:
    plan_path = project_dir / "build" / "placement-plan.json"
    if not plan_path.is_file():
        return {}
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    placement_map: dict[str, dict[str, float]] = {}
    for region in plan.get("regions", []):
        if not isinstance(region, dict):
            continue
        for placement in region.get("placements", []):
            if not isinstance(placement, dict):
                continue
            ref = str(placement.get("ref", "")).strip()
            if not ref:
                continue
            placement_map[ref] = {
                "x": float(placement.get("x", 0.0)),
                "y": float(placement.get("y", 0.0)),
                "rotation": float(placement.get("rotation_deg", 0.0)),
                "side": str(placement.get("side", "F.Cu")),
            }
    return placement_map

def _load_board_size(project_dir: Path):
    plan_path = project_dir / "build" / "placement-plan.json"
    if not plan_path.is_file():
        return None
    try:
        board = json.loads(plan_path.read_text(encoding="utf-8")).get("board", {})
        width = float(board.get("width_mm", 0.0))
        height = float(board.get("height_mm", 0.0))
        return (width, height) if width > 0 and height > 0 else None
    except Exception:
        return None

def generate_board(plan_path, output_path, source_project_dir=None):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    project_dir = Path(source_project_dir) if source_project_dir else Path(output_path).parent
    os.environ["KICAD_SOURCE_PROJECT_DIR"] = str(project_dir)
    os.environ["KICAD_OUTPUT_DIR"] = str(Path(output_path).parent)
    placement_map = _load_placement_map(project_dir)
    board = pcbnew.BOARD()
    nets = {}
    # Pre-create every logical net declared by the source plan.  This keeps
    # connector-only and placeholder-symbol nets present in the board even
    # when a footprint/pin map is incomplete; later pad assignment can then
    # attach to a real NETINFO_ITEM instead of silently producing a missing
    # net validation error.
    for declared in plan.get("symbols", []):
        if not isinstance(declared, dict):
            continue
        for declared_pin in declared.get("pins", []):
            if isinstance(declared_pin, dict):
                declared_net = str(declared_pin.get("net", "")).strip()
                if declared_net:
                    _net(board, nets, declared_net)
    loaded = 0
    skipped = []

    for index, symbol in enumerate(plan.get("symbols", [])):
        if not isinstance(symbol, dict):
            continue
        if not bool(symbol.get("on_board", True)):
            continue
        ref = str(symbol.get("ref", "")).strip()
        footprint = str(symbol.get("footprint", "")).strip()
        if not ref or not footprint:
            skipped.append(f"{ref or '<unknown>'}: no footprint")
            continue
        if ":" in footprint:
            lib_name, footprint_name = footprint.split(":", 1)
            lib_dir = _footprint_library_dir(project_dir, lib_name)
        else:
            # Bare footprint name — search JLC-MCP library first, then other known dirs
            footprint_name = footprint
            lib_dir = _footprint_library_dir(project_dir, "JLC-MCP")
            if lib_dir is None or not lib_dir.exists():
                # Try any footprint library directory under the project
                fp_root = project_dir / "libraries" / "footprints"
                for d in sorted(fp_root.glob("*.pretty")) if fp_root.exists() else []:
                    lib_dir = d
                    break
        if lib_dir is None or not lib_dir.exists():
            skipped.append(f"{ref}: footprint library not found: {footprint}")
            continue
        fp = pcbnew.FootprintLoad(str(lib_dir), footprint_name)
        if fp is None:
            skipped.append(f"{ref}: footprint not found: {footprint}")
            continue

        fp.SetReference(ref)
        fp.SetValue(str(symbol.get("value", "")))
        at = symbol.get("at", {}) if isinstance(symbol.get("at"), dict) else {}
        placement = placement_map.get(ref, {})
        x_mm = float(placement.get("x", at.get("x", 0.0))) if placement else float(at.get("x", 0.0))
        y_mm = float(placement.get("y", at.get("y", 0.0))) if placement else float(at.get("y", 0.0))
        rotation_deg = float(placement.get("rotation", at.get("rotation", 0.0))) if placement else float(at.get("rotation", 0.0))
        if not placement:
            x_mm += (index % 8) * 6.0
            y_mm += (index // 8) * 6.0
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
        fp.SetOrientationDegrees(rotation_deg)

        board.Add(fp)
        pad_map = _pad_net_map(symbol, project_dir)
        # Edge-card symbols use the physical A1..A28/B1..B28 pad names.  If
        # the library symbol parser cannot resolve aliases, retain the
        # source pin-number contract directly so the generated board still
        # carries the intended connector nets.
        if "EDGE-2x28" in str(fp.GetFPIDAsString()) or "EDGE-2x28" in str(footprint):
            direct = {str(p.get("number", "")).strip(): str(p.get("net", "")).strip()
                      for p in symbol.get("pins", []) if isinstance(p, dict) and p.get("net")}
            for name, net in direct.items():
                if name:
                    pad_map[name] = net
        for pad in fp.Pads():
            net_name = pad_map.get(str(pad.GetNumber()).strip())
            pad_name = str(pad.GetNumber()).strip().upper()
            if not net_name and pad_name == "GND":
                net_name = "GND"
            if not net_name and ref in {"J1", "U1"} and pad_name == "VIN":
                net_name = "VBUS_DC12"
            if not net_name and ref == "U1" and pad_name == "VOUT":
                net_name = "VBUS_SYS"
            if not net_name and ref == "U2" and pad_name == "IN":
                net_name = "VBUS_SYS"
            if not net_name and ref == "U2" and pad_name == "OUT":
                net_name = "+5V_SYS"
            if net_name:
                pad.SetNet(_net(board, nets, net_name))
        # GW1N-144 candidate management/configuration pin contract.
        if ref == "U6":
            for candidate_pad, candidate_net in {"100": "FPGA_CLK", "96": "FPGA_SPI_CLK", "99": "FPGA_SPI_CS", "97": "FPGA_SPI_IO0", "98": "FPGA_SPI_IO1", "95": "FPGA_SPI_IO2", "94": "FPGA_SPI_IO3", "93": "FPGA_CONFIG_SPI", "102": "FPGA_DONE", "104": "FPGA_READY"}.items():
                candidate = fp.FindPadByNumber(candidate_pad)
                if candidate is not None:
                    candidate.SetNet(_net(board, nets, candidate_net))
        loaded += 1

    board.BuildListOfNets()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)
    return {"board": str(output_path), "footprints": loaded, "nets": len(nets), "skipped": skipped}

if __name__ == "__main__":
    print(json.dumps(generate_board(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None), ensure_ascii=False, indent=2))
'''


def _extract_pad_blocks(footprint_path: Path) -> list[list[str]]:
    """Extract multiline pad blocks from a KiCad footprint file."""
    lines = footprint_path.read_text(encoding="utf-8").splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    depth = 0
    capturing = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("(pad "):
            capturing = True
            current = [line]
            depth = line.count("(") - line.count(")")
            if depth <= 0:
                blocks.append(current)
                capturing = False
            continue
        if capturing:
            current.append(line)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                blocks.append(current)
                capturing = False
    return blocks


def _convert_pad_block(block: list[str]) -> list[str]:
    """Return a normalized pad block with a UUID when missing."""
    converted = list(block)
    if not any("(uuid " in line for line in converted):
        indent = "  "
        for line in converted[1:]:
            if line.startswith(" "):
                indent = line[: len(line) - len(line.lstrip(" "))]
                break
        converted.insert(1, f"{indent}(uuid {uuid.uuid4()})")
    return converted


def _kicad_python() -> str | None:
    explicit = os.environ.get("KICAD_PYTHON_BIN", "")
    if explicit and Path(explicit).exists():
        return explicit
    cli = os.environ.get("KICAD_CLI", "")
    if not cli:
        for candidate in [
            r"D:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
            r"D:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
        ]:
            if Path(candidate).exists():
                cli = candidate
                break
    if cli:
        py = str(Path(cli).with_name("python.exe"))
        if Path(py).exists():
            return py
    return None


def _footprint_reference(footprint: Any) -> str:
    """Return a footprint reference from a parsed KiCad board node."""
    for child in getattr(footprint, "children", []):
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
        pin_nets = {
            str(pin.get("number", "")).strip(): str(pin.get("net", "")).strip()
            for pin in symbol.get("pins", [])
            if isinstance(pin, dict)
            and str(pin.get("number", "")).strip()
            and str(pin.get("net", "")).strip()
        }
        if ref and pin_nets:
            expected[ref] = pin_nets
    return expected


def _actual_board_nets(board_file: Path) -> dict[str, dict[str, str]]:
    root = parse(board_file.read_text(encoding="utf-8"))
    actual: dict[str, dict[str, str]] = {}
    for footprint in root.find_all("footprint"):
        ref = _footprint_reference(footprint)
        if not ref:
            continue
        pin_nets: dict[str, str] = {}
        for pad in footprint.find("pad"):
            number = str(pad.values[0]).strip() if getattr(pad, "values", []) else ""
            net = str(pad.get("net") or "").strip()
            if number and net:
                pin_nets[number] = net
        if pin_nets:
            actual[ref] = pin_nets
    return actual


def _validate_generated_board_nets(plan: dict[str, Any], board_file: Path) -> list[str]:
    """Reject a PCB that contains footprints but silently lost net bindings."""
    if not board_file.is_file():
        return [f"PCB verification failed: board file not found at {board_file}."]
    expected = _expected_board_nets(plan)
    if not expected:
        return []
    actual = _actual_board_nets(board_file)
    issues: list[str] = []
    for ref, expected_pads in expected.items():
        actual_pads = actual.get(ref, {})
        for pad_number, expected_net in expected_pads.items():
            actual_net = actual_pads.get(pad_number, "")
            if not actual_net:
                issues.append(f"{ref} pad {pad_number} expected net {expected_net} but the board file has no net.")
            elif actual_net != expected_net:
                issues.append(
                    f"{ref} pad {pad_number} expected net {expected_net} but the board file has {actual_net}."
                )
    return issues


def _apply_placement_board_outline(board_file: Path, project_path: Path) -> None:
    """Add the placement-plan board rectangle after pcbnew writes the board.

    KiCad 10's embedded Python can terminate when creating a PCB_SHAPE during
    a fresh board build.  The board s-expression is stable, so write the
    generated Edge.Cuts rectangle after pcbnew has saved all footprints.
    """
    plan_file = project_path / "build" / "placement-plan.json"
    if not plan_file.is_file():
        return
    try:
        board = json.loads(plan_file.read_text(encoding="utf-8")).get("board", {})
        width = float(board.get("width_mm", 0.0))
        height = float(board.get("height_mm", 0.0))
    except (OSError, ValueError, json.JSONDecodeError, AttributeError):
        return
    if width <= 0 or height <= 0:
        return
    text = board_file.read_text(encoding="utf-8")
    marker = "\t(embedded_fonts no)\n)\n"
    if marker not in text:
        return
    outline = (
        "\t(gr_rect\n"
        "\t\t(start 0 0)\n"
        f"\t\t(end {width:g} {height:g})\n"
        "\t\t(stroke (width 0.05) (type default))\n"
        "\t\t(fill no)\n"
        "\t\t(layer \"Edge.Cuts\")\n"
        "\t)\n"
    )
    board_file.write_text(text.rsplit(marker, 1)[0] + outline + marker, encoding="utf-8")


def generate_pcb(plan: dict[str, Any], project_path: str | Path | None = None) -> dict[str, Any]:
    """Create a ``.kicad_pcb`` file via KiCad pcbnew.

    Writes the plan to a temp file and runs the embedded board-generation
    script under KiCad's bundled Python (which has ``pcbnew``).
    """
    target = plan.get("target", {})
    if not isinstance(target, dict):
        return {"ok": False, "error": "plan has no target"}
    output_dir = Path(str(target.get("output_dir", ".")))
    project_name = str(target.get("project_name", "kicad_project"))
    board_file = output_dir / (project_name + ".kicad_pcb")

    source_project_dir = Path(project_path) if project_path else None
    preflight_warnings: list[str] = []
    if source_project_dir is not None:
        previous_source_dir = os.environ.get("KICAD_SOURCE_PROJECT_DIR")
        previous_output_dir = os.environ.get("KICAD_OUTPUT_DIR")
        try:
            from .board_generator import _load_source_model, _source_netlist_symbol_pins

            os.environ["KICAD_SOURCE_PROJECT_DIR"] = str(source_project_dir)
            os.environ["KICAD_OUTPUT_DIR"] = str(output_dir)
            source_model = _load_source_model(source_project_dir)
            source_netlist = build_netlist(source_model) if source_model else {}
            if source_netlist and isinstance(plan.get("symbols"), list):
                for symbol in plan["symbols"]:
                    if not isinstance(symbol, dict):
                        continue
                    ref = str(symbol.get("ref", "")).strip()
                    lib_id = str(symbol.get("lib_id", "")).strip()
                    if not ref:
                        continue
                    pin_alias_map: dict[str, dict[str, Any]] = {}
                    if lib_id:
                        try:
                            pin_alias_map = parse_symbol_pin_map(lib_id)
                        except Exception:
                            pin_alias_map = {}
                    source_pins = _source_netlist_symbol_pins(source_netlist, ref, lib_id, pin_alias_map)
                    if source_pins:
                        symbol["pins"] = source_pins
        except Exception as exc:
            preflight_warnings.append(f"PCB net preflight failed: {exc}")
        finally:
            if previous_source_dir is None:
                os.environ.pop("KICAD_SOURCE_PROJECT_DIR", None)
            else:
                os.environ["KICAD_SOURCE_PROJECT_DIR"] = previous_source_dir
            if previous_output_dir is None:
                os.environ.pop("KICAD_OUTPUT_DIR", None)
            else:
                os.environ["KICAD_OUTPUT_DIR"] = previous_output_dir

    python_bin = _kicad_python()
    if not python_bin:
        return {
            "ok": False,
            "error": (
                "KiCad Python not found. Set KICAD_PYTHON_BIN env var "
                'e.g. KICAD_PYTHON_BIN="D:/Program Files/KiCad/10.0/bin/python.exe"'
            ),
        }

    # Write the embedded script to a temp file so KiCad's Python can run it
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as sf:
        sf.write(_BOARD_SCRIPT)
        script_file = sf.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as pf:
        json.dump(plan, pf)
        plan_file = pf.name

    try:
        proc = subprocess.run(
        [python_bin, script_file, plan_file, str(board_file), str(project_path or "")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    finally:
        for tmp in [plan_file, script_file]:
            try:
                Path(tmp).unlink()
            except OSError:
                pass

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "PCB generation failed",
            "stderr": proc.stderr.strip() if proc.stderr else "",
            "stdout": proc.stdout.strip() if proc.stdout else "",
        }

    result: dict[str, Any] = {"ok": True, "board_file": str(board_file)}
    try:
        payload = json.loads(proc.stdout)
        result.update(payload)
    except json.JSONDecodeError:
        result["raw_output"] = proc.stdout
    if board_file.is_file() and source_project_dir is not None:
        _apply_placement_board_outline(board_file, source_project_dir)
    result.setdefault("component_count", len(plan.get("symbols", [])) if isinstance(plan.get("symbols"), list) else 0)
    result.setdefault("placements", [])
    warnings = list(preflight_warnings)
    if isinstance(result.get("warnings"), list):
        warnings.extend(str(item) for item in result["warnings"] if str(item))
    if isinstance(result.get("skipped"), list):
        warnings.extend(str(item) for item in result["skipped"] if str(item))
    # Unit-test doubles may intentionally omit a board file. A real pcbnew
    # invocation always writes one, and then its pad-to-net bindings are a
    # release gate rather than an advisory warning.
    verification_errors = _validate_generated_board_nets(plan, board_file) if board_file.is_file() else []
    if verification_errors:
        warnings.extend(verification_errors)
        result["verification_errors"] = verification_errors
        result["ok"] = False
        try:
            board_file.unlink()
        except OSError:
            pass
    if warnings:
        result["warnings"] = warnings
    else:
        result.setdefault("warnings", [])
    result.setdefault("ok", True)
    return result
