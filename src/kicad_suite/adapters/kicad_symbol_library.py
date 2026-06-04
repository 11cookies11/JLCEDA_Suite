"""Symbol library parsing for explicit KiCad symbol references."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..shared.env_utils import env, repo_root

REPO_ROOT = repo_root()
SYMBOL_PIN_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
SYMBOL_UNIT_CACHE: dict[str, list[int]] = {}

H618_MINIMAL_PINS: tuple[str, ...] = (
    "GND",
    "VDD1",
    "VDD2",
    "VDDQ",
    "PMIC_SCL",
    "PMIC_SDA",
    "PMIC_INT_N",
    "XIN",
    "XOUT",
    "RTC_XIN",
    "RTC_XOUT",
    "PH0",
    "PH1",
    "RESET_N",
    "BOOT0",
    "SD_CLK",
    "SD_CMD",
    "SD_D0",
    "SD_D1",
    "SD_D2",
    "SD_D3",
    "SPI0_CLK",
    "SPI0_MOSI",
    "SPI0_MISO",
    "SPI0_CS0",
    "RGMII_MDC",
    "RGMII_MDIO",
    "RGMII_TXD0",
    "RGMII_TXD1",
    "RGMII_TXD2",
    "RGMII_TXD3",
    "RGMII_RXD0",
    "RGMII_RXD1",
    "RGMII_RXD2",
    "RGMII_RXD3",
    "RGMII_TXC",
    "RGMII_RXC",
    "RGMII_TXCTL",
    "RGMII_RXCTL",
    "RGMII_RESET_N",
    "USB0_DM",
    "USB0_DP",
    "USB_HUB_RESET_N",
    "HDMI_TX0_P",
    "HDMI_TX0_N",
    "HDMI_TX1_P",
    "HDMI_TX1_N",
    "HDMI_TX2_P",
    "HDMI_TX2_N",
    "HDMI_CLK_P",
    "HDMI_CLK_N",
    "PH5",
    "PH4",
    "PC9",
    "PH2",
    "PH3",
    "PC6",
    "PC11",
    "PC5",
    "PC8",
    "PC15",
    "PC14",
    "PH7",
    "PH8",
    "PH6",
    "PH9",
    "PC7",
    "PC10",
    "DQ0",
    "DQ1",
    "DQ2",
    "DQ3",
    "DQ4",
    "DQ5",
    "DQ6",
    "DQ7",
    "DQS0_P",
    "DQS0_N",
    "CKE",
)


def q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt(value: float) -> str:
    text = f"{float(value):.3f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def local_symbol_library(symbols: list[dict[str, Any]]) -> str:
    lib_ids = sorted({str(symbol.get("lib_id", "")).strip() for symbol in symbols})
    if any(not lib_id for lib_id in lib_ids):
        raise ValueError("Every KiCad symbol instance must provide an explicit lib_id.")
    footprints_by_lib_id: dict[str, str] = {}
    for symbol in symbols:
        lib_id = str(symbol.get("lib_id", "")).strip()
        footprint = str(symbol.get("footprint", "")).strip()
        if footprint and lib_id not in footprints_by_lib_id:
            footprints_by_lib_id[lib_id] = footprint
    blocks = ["  (lib_symbols"]
    for lib_id in lib_ids:
        blocks.append(symbol_block_with_default_footprint(symbol_block_for_lib_id(lib_id), footprints_by_lib_id.get(lib_id, "")))
    blocks.append("  )")
    return "\n".join(blocks)


def kicad_symbol_roots() -> list[Path]:
    """Return ordered list of directories searched for .kicad_sym library files."""
    roots: list[Path] = []

    def _add_if_exists(path: Path) -> None:
        if path.exists() and path not in roots:
            roots.append(path)

    source_project = env("KICAD_SOURCE_PROJECT_DIR", "")
    if source_project:
        _add_if_exists(Path(source_project) / "libraries" / "symbols")

    output_root = env("KICAD_OUTPUT_DIR", "")
    if output_root:
        _add_if_exists(Path(output_root).parent / "libraries" / "symbols")
        _add_if_exists(Path(output_root) / "libs")
        try:
            for subdir in Path(output_root).iterdir():
                if subdir.is_dir():
                    _add_if_exists(subdir / "libraries" / "symbols")
        except OSError:
            pass

    _add_if_exists(REPO_ROOT / "resources" / "kicad" / "symbols")

    try:
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents)[:4]:
            _add_if_exists(parent / "libraries" / "symbols")
    except OSError:
        pass

    for base in (Path("D:/Program Files/KiCad"), Path("C:/Program Files/KiCad")):
        if base.exists():
            for path in sorted(base.glob("*"), reverse=True):
                _add_if_exists(path / "share" / "kicad" / "symbols")

    return roots


def find_matching_paren(text: str, start: int) -> int:
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


def tokenize_sexpr(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            escaped = False
            while index < len(text):
                current = text[index]
                index += 1
                if escaped:
                    value.append(current)
                    escaped = False
                    continue
                if current == "\\":
                    escaped = True
                    continue
                if current == '"':
                    break
                value.append(current)
            tokens.append("".join(value))
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in "()":
            index += 1
        tokens.append(text[start:index])
    return tokens


def parse_sexpr_tokens(tokens: list[str]) -> Any:
    def parse_at(index: int) -> tuple[Any, int]:
        if tokens[index] != "(":
            return tokens[index], index + 1
        index += 1
        items: list[Any] = []
        while index < len(tokens) and tokens[index] != ")":
            item, index = parse_at(index)
            items.append(item)
        return items, index + 1

    parsed, final_index = parse_at(0)
    if final_index != len(tokens):
        raise ValueError("Unexpected trailing tokens in S-expression.")
    return parsed


def parse_sexpr(text: str) -> Any:
    return parse_sexpr_tokens(tokenize_sexpr(text))


def sexpr_head(node: Any) -> str:
    if isinstance(node, list) and node:
        return str(node[0])
    return ""


def normalize_embedded_symbol_name(block: str, library: str, symbol_name: str) -> str:
    safe_symbol_name = _sanitize_symbol_name(symbol_name)
    if safe_symbol_name != symbol_name:
        block = block.replace(symbol_name, safe_symbol_name)
    block = block.replace(f'(symbol "{safe_symbol_name}"', f'(symbol "{library}:{safe_symbol_name}"', 1)
    return strip_symbol_lib_id(block)


def strip_symbol_lib_id(block: str) -> str:
    lines = block.splitlines()
    filtered = [line for line in lines if "(lib_id " not in line]
    return "\n".join(filtered)


def sanitize_lib_symbols_section(text: str) -> str:
    lib_start = text.find("(lib_symbols")
    if lib_start < 0:
        return text
    lib_end = find_matching_paren(text, lib_start)
    if lib_end < 0:
        return text
    section = text[lib_start:lib_end + 1]
    cleaned = strip_symbol_lib_id(section)
    return text[:lib_start] + cleaned + text[lib_end + 1:]


def _sanitize_symbol_name(name: str) -> str:
    cleaned = name.replace(" ", "_").replace(":", "_").replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", cleaned)
    return cleaned.strip("._-") or "UNKNOWN"


def sanitize_symbol_block(text: str) -> str:
    cleaned = text
    for bad_token in ("NaN", "nan", "INF", "Inf"):
        while bad_token in cleaned:
            bad_index = cleaned.find(bad_token)
            start = max(
                cleaned.rfind(f"({head}", 0, bad_index)
                for head in ("arc", "circle", "polyline", "rectangle", "bezier")
            )
            if start < 0:
                cleaned = cleaned.replace(bad_token, "0", 1)
                continue
            end = find_matching_paren(cleaned, start)
            if end < 0:
                cleaned = cleaned[:bad_index] + "0" + cleaned[bad_index + len(bad_token):]
                continue
            while start > 0 and cleaned[start - 1] in " \t":
                start -= 1
            if start > 0 and cleaned[start - 1] == "\n":
                start -= 1
            cleaned = cleaned[:start] + cleaned[end + 1:]
    return cleaned


def _candidate_symbol_library_files(root: Path, library: str) -> list[Path]:
    files: list[Path] = []
    exact = root / f"{library}.kicad_sym"
    if exact.exists():
        files.append(exact)
    if library == "JLC-MCP":
        for extra in sorted(root.glob("JLC-MCP*.kicad_sym")):
            if extra not in files:
                files.append(extra)
    return files


def load_installed_symbol(library: str, symbol_name: str) -> str:
    needle = f'(symbol "{symbol_name}"'
    for root in kicad_symbol_roots():
        candidate_files = _candidate_symbol_library_files(root, library)
        for symbol_file in candidate_files:
            if not symbol_file.exists():
                continue
            text = symbol_file.read_text(encoding="utf-8")
            start = text.find(needle)
            if start < 0:
                continue
            end = find_matching_paren(text, start)
            if end < 0:
                continue
            block = sanitize_symbol_block(text[start:end + 1])
            block = normalize_embedded_symbol_name(block, library, symbol_name)
            return "\n".join(f"    {line}" if line.strip() else line for line in block.splitlines())
    return ""


def installed_symbol_block(library: str, symbol_name: str) -> str:
    needle = f'(symbol "{symbol_name}"'
    for root in kicad_symbol_roots():
        for symbol_file in _candidate_symbol_library_files(root, library):
            if not symbol_file.exists():
                continue
            text = symbol_file.read_text(encoding="utf-8")
            start = text.find(needle)
            if start < 0:
                continue
            end = find_matching_paren(text, start)
            if end >= 0:
                return strip_symbol_lib_id(text[start:end + 1])
    return ""


def normalize_connector_pin_types(block: str, symbol_name: str) -> str:
    upper_name = symbol_name.upper()
    if upper_name in {
        "USB2514B-AEZC-TR",
        "AXP313A_C5365290",
        "GD25Q16ETIGR",
        "RTL8211F-CG",
        "322524M12PF10PPM",
        "H9HCNNNBKUMLXR-NEE",
    }:
        return re.sub(r"\(pin\s+unspecified\s+line", "(pin passive line", block)
    connector_tokens = (
        "HEADER",
        "HDR-",
        "CONN_",
        "PINHEADER",
        "XKTF",
        "TF-",
        "MICROSD",
        "SDCARD",
        "USB-",
        "USB_",
        "TYPE-C",
        "RJ45",
        "HDMI",
        "467650301",
        "DS1021",
    )
    if not any(token in upper_name for token in connector_tokens):
        return block
    return re.sub(r"\(pin\s+(input|output|bidirectional|tri_state|passive|power_in|power_out|open_collector|open_emitter|unspecified)\s+line", "(pin passive line", block)


def local_h618_minimal_symbol(lib_id: str) -> str:
    symbol_name = lib_id.split(":", 1)[-1]
    half_count = (len(H618_MINIMAL_PINS) + 1) // 2
    half_height = max(10.16, half_count * 1.27 + 2.54)
    pins: list[str] = []
    for index, pin_name in enumerate(H618_MINIMAL_PINS):
        left = index < half_count
        row = index if left else index - half_count
        y = (half_count - 1) * 1.27 - row * 2.54
        x = -22.86 if left else 22.86
        rotation = 0 if left else 180
        pins.append(f'''        (pin passive line (at {fmt(x)} {fmt(y)} {rotation}) (length 2.54)
          (name {q(pin_name)} (effects (font (size 1.27 1.27))))
          (number {q(pin_name)} (effects (font (size 1.27 1.27))))
        )''')
    return f'''    (symbol {q(lib_id)}
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (duplicate_pin_numbers_are_jumpers no)
      (property "Reference" "U" (at 0 {fmt(half_height + 2.54)} 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" {q(symbol_name)} (at 0 {fmt(-half_height - 2.54)} 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (hide yes)
        (effects (font (size 1.27 1.27)))
      )
      (symbol "{symbol_name}_0_1"
        (rectangle (start -17.78 {fmt(half_height)}) (end 17.78 {fmt(-half_height)} )
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
{chr(10).join(pins)}
      )
      (embedded_fonts no)
    )'''


def symbol_block_for_lib_id(lib_id: str) -> str:
    if ":" in lib_id:
        library, symbol_name = lib_id.split(":", 1)
        installed = load_installed_symbol(library, symbol_name)
        if installed and symbol_name == "ALLWINNERH618" and "(pin " not in installed:
            return local_h618_minimal_symbol(lib_id)
        if installed:
            return strip_symbol_lib_id(normalize_connector_pin_types(installed, symbol_name))
        system_block = installed_symbol_block(library, symbol_name)
        if system_block:
            if symbol_name == "ALLWINNERH618" and "(pin " not in system_block:
                return local_h618_minimal_symbol(lib_id)
            normalized = normalize_embedded_symbol_name(system_block, library, symbol_name)
            normalized = normalize_connector_pin_types(normalized, symbol_name)
            return "\n".join(f"    {line}" if line.strip() else line for line in strip_symbol_lib_id(normalized).splitlines())

    raise ValueError(f"KiCad symbol not found: {lib_id}")


def symbol_block_with_default_footprint(block: str, footprint: str) -> str:
    if not footprint:
        return block
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if '(property "Footprint"' in line:
            lines[index] = re.sub(r'\(property "Footprint" "([^"]*)"', f'(property "Footprint" {q(footprint)}', line, count=1)
            return "\n".join(lines)
    result: list[str] = []
    depth = 0
    in_value = False
    inserted_after: int = -1
    for index, line in enumerate(lines):
        if not in_value and '(property "Value"' in line:
            in_value = True
            depth = 1
        elif in_value:
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                inserted_after = index
                in_value = False
        result.append(line)
        if inserted_after == index:
            indent = line[:len(line) - len(line.lstrip())] if line.strip() else "      "
            result.append(f'{indent}(property "Footprint" {q(footprint)} (at 0 0 0)')
            result.append(f"{indent}  (hide yes)")
            result.append(f"{indent}  (effects (font (size 1.27 1.27)))")
            result.append(f"{indent})")
            inserted_after = -1
    return "\n".join(result)


def parse_symbol_pin_map(lib_id: str) -> dict[str, dict[str, Any]]:
    if lib_id in SYMBOL_PIN_CACHE:
        return SYMBOL_PIN_CACHE[lib_id]
    if ":" not in lib_id:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    library, symbol_name = lib_id.split(":", 1)
    block = symbol_block_for_lib_id(lib_id) or installed_symbol_block(library, symbol_name)
    if not block:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}
    try:
        tree = parse_sexpr(block)
    except Exception:
        SYMBOL_PIN_CACHE[lib_id] = {}
        return {}

    pins: dict[str, dict[str, Any]] = {}

    def pin_aliases(number: str, name: str) -> set[str]:
        aliases = {number, number.upper()}
        clean_name = name.strip()
        if clean_name:
            name_upper = clean_name.upper()
            aliases.add(clean_name)
            aliases.add(name_upper)
            normalized = re.sub(r"[^A-Z0-9]+", "_", name_upper).strip("_")
            if normalized:
                aliases.add(normalized)
                aliases.add(normalized.replace("_T", "_P").replace("_C", "_N"))
                match = re.fullmatch(r"(.+?)[AB]", normalized)
                if match:
                    aliases.add(match.group(1))
                match = re.fullmatch(r"(CKE\d+)[AB]", normalized)
                if match:
                    aliases.add(match.group(1))
                    aliases.add(match.group(1).replace("0", "", 1))
                match = re.fullmatch(r"(DQ\d+)[AB]", normalized)
                if match:
                    aliases.add(match.group(1))
                match = re.fullmatch(r"(DQS\d+)_[TC][AB]", normalized)
                if match:
                    aliases.add(match.group(1))
        return {alias for alias in aliases if alias}

    def visit(node: Any, current_unit: int = 1) -> None:
        if not isinstance(node, list) or not node:
            return
        node_unit = current_unit
        if sexpr_head(node) == "symbol" and len(node) >= 2 and isinstance(node[1], str):
            unit_match = re.fullmatch(rf"{re.escape(symbol_name)}_(\d+)_\d+", node[1])
            if unit_match:
                parsed_unit = int(unit_match.group(1))
                if parsed_unit > 0:
                    node_unit = parsed_unit
        if sexpr_head(node) == "pin":
            at_data = next((child for child in node if sexpr_head(child) == "at"), None)
            length_data = next((child for child in node if sexpr_head(child) == "length"), None)
            number_data = next((child for child in node if sexpr_head(child) == "number"), None)
            name_data = next((child for child in node if sexpr_head(child) == "name"), None)
            if isinstance(at_data, list) and len(at_data) >= 4 and isinstance(number_data, list) and len(number_data) >= 2:
                try:
                    number = str(number_data[1])
                    name = str(name_data[1]) if isinstance(name_data, list) and len(name_data) >= 2 else ""
                    pin_info = {
                        "x": float(at_data[1]),
                        "y": float(at_data[2]),
                        "rotation": float(at_data[3]),
                        "length": float(length_data[1]) if isinstance(length_data, list) and len(length_data) >= 2 else 0.0,
                        "electrical_type": str(node[1]) if len(node) >= 2 else "",
                        "name": name,
                        "number": number,
                        "unit": node_unit,
                    }
                    for alias in pin_aliases(number, name):
                        pins.setdefault(alias, pin_info)
                except (TypeError, ValueError):
                    pass
        for child in node:
            visit(child, node_unit)

    visit(tree)
    if not pins:
        extends = next((child[1] for child in tree if isinstance(child, list) and sexpr_head(child) == "extends"), None)
        if isinstance(extends, str) and extends:
            parent_pins = parse_symbol_pin_map(f"{library}:{extends}")
            pins.update(parent_pins)
    SYMBOL_PIN_CACHE[lib_id] = pins
    return pins


def symbol_unit_numbers(lib_id: str) -> list[int]:
    if lib_id in SYMBOL_UNIT_CACHE:
        return SYMBOL_UNIT_CACHE[lib_id]
    if ":" not in lib_id:
        SYMBOL_UNIT_CACHE[lib_id] = [1]
        return [1]
    symbol_name = lib_id.split(":", 1)[1]
    block = symbol_block_for_lib_id(lib_id)
    units = sorted({int(match.group(1)) for match in re.finditer(rf'\(symbol "{re.escape(symbol_name)}_(\d+)_', block)})
    if not units:
        units = [1]
    SYMBOL_UNIT_CACHE[lib_id] = units
    return units


def symbol_real_pin_numbers(lib_id: str, unit: int | None = None) -> list[str]:
    real_pins: dict[str, dict[str, Any]] = {}
    for alias, pin_info in parse_symbol_pin_map(lib_id).items():
        number = str(pin_info.get("number", alias)).strip()
        if not number:
            continue
        if unit is not None and int(pin_info.get("unit", 1) or 1) != unit:
            continue
        real_pins.setdefault(number, pin_info)
    return sorted(real_pins, key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value)))


def symbol_pin_unit(lib_id: str, pin_number: str) -> int:
    raw = str(pin_number).strip()
    pin_map = parse_symbol_pin_map(lib_id)
    pin_info = pin_map.get(raw) or pin_map.get(raw.upper())
    if isinstance(pin_info, dict):
        try:
            return int(pin_info.get("unit", 1) or 1)
        except (TypeError, ValueError):
            return 1
    return 1
