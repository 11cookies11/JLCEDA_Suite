"""Tests for the S-expression parser."""

from __future__ import annotations

from pathlib import Path

from kicad_suite.shared.sexpr_parser import (
    SExprNode,
    parse,
    symbols_in_library,
    pins_of_symbol,
)


# ── Unit tests ────────────────────────────────────────────────────────


def test_parse_simple() -> None:
    tree = parse("(kicad_symbol_lib (version 2024))")
    assert len(tree.children) == 1
    lib = tree.children[0]
    assert lib.tag == "kicad_symbol_lib"
    ver = lib.children[0]
    assert ver.tag == "version"
    assert ver.values == ["2024"]


def test_parse_nested() -> None:
    # Real KiCad format: pin type comes first as a bare value
    tree = parse('(pin bidirectional line (name "PA11") (number "32"))')
    pins = tree.find_all("pin")
    assert len(pins) == 1
    pin = pins[0]
    assert pin.get("name") == "PA11"
    assert pin.get("number") == "32"
    assert pin.values == ["bidirectional", "line"]


def test_parse_alphanumeric_pin() -> None:
    tree = parse('(pin (name "DP1") (number "A6") (type unspecified))')
    pin = tree.find_all("pin")[0]
    assert pin.get("number") == "A6"
    assert pin.get("name") == "DP1"


def test_parse_compound_pin() -> None:
    tree = parse('(pin (name "GND") (number "A1B12") (type unspecified))')
    pin = tree.find_all("pin")[0]
    # "A1B12" MUST be preserved as a single token — not split
    assert pin.get("number") == "A1B12"


def test_parse_quoted_string_with_spaces() -> None:
    tree = parse('(property "Value" "STM32F103C8T6")')
    prop = tree.find_all("property")[0]
    assert prop.values == ["Value", "STM32F103C8T6"]


def test_parse_comments_ignored() -> None:
    tree = parse("(symbol RP2040 ; this is a comment\n)")
    sym = tree.find_all("symbol")[0]
    assert sym.values == ["RP2040"]


def test_emit_simple() -> None:
    node = SExprNode("pin")
    node.values = ["bidirectional"]
    n1 = SExprNode("name"); n1.values = ["PA11"]
    n2 = SExprNode("number"); n2.values = ["32"]
    node.children = [n1, n2]
    text = node.emit()
    assert "(pin" in text
    assert "PA11" in text
    assert "32" in text


def test_round_trip() -> None:
    original = '(pin (name "A6") (number "A6") (type bidirectional))'
    tree = parse(original)
    reparsed = parse(tree.emit())
    pin = reparsed.find_all("pin")[0]
    assert pin.get("number") == "A6"
    assert pin.get("name") == "A6"


def test_find_vs_find_all() -> None:
    tree = parse("(lib (symbol A) (symbol (unit (pin B))))")
    lib = tree.children[0]
    assert len(lib.find("symbol")) == 2  # direct children: A and (symbol ...)
    assert len(tree.find_all("pin")) == 1  # recursive


def test_set_existing_property() -> None:
    tree = parse('(property "Footprint" "old")')
    prop = tree.find_all("property")[0]
    prop.set("Footprint", "new")
    assert prop.get("Footprint") == "new"


def test_set_new_property() -> None:
    node = SExprNode("symbol")
    node.set("Footprint", "SOIC-8")
    assert node.get("Footprint") == "SOIC-8"


def test_empty_node() -> None:
    tree = parse("()")
    # Parser wraps empty list as a node with tag "" — acceptable
    assert len(tree.children) <= 1


# ── Integration tests with real KiCad files ────────────────────────────

_REPO = Path(__file__).resolve().parent.parent


def _find_symbol_lib() -> Path | None:
    for candidate in [
        _REPO / "tmp" / "nexdap-mini" / "libraries" / "symbols" / "JLC-MCP.kicad_sym",
        _REPO / "packs" / "symbols" / "JLC-MCP-Connectors.kicad_sym",
    ]:
        if candidate.exists():
            return candidate
    return None


def test_symbols_in_library() -> None:
    lib_path = _find_symbol_lib()
    if lib_path is None:
        return  # skip if no library available
    symbols = symbols_in_library(lib_path.read_text(encoding="utf-8"))
    assert len(symbols) > 0
    # Verify no sub-symbols
    for name in symbols:
        assert not name.endswith("_0_1"), f"Sub-symbol leaked: {name}"


def test_pins_of_symbol_integration() -> None:
    lib_path = _find_symbol_lib()
    if lib_path is None:
        return
    symbols = symbols_in_library(lib_path.read_text(encoding="utf-8"))
    for sym_name in symbols:
        sym = symbols[sym_name]
        pins = pins_of_symbol(sym)
        # Every symbol should have at least 1 pin
        assert len(pins) > 0, f"{sym_name} has 0 pins"
        # Every pin should have a number
        for p in pins:
            assert p["number"], f"{sym_name} pin has empty number"


def test_alphanumeric_pins_preserved() -> None:
    lib_path = _find_symbol_lib()
    if lib_path is None:
        return
    symbols = symbols_in_library(lib_path.read_text(encoding="utf-8"))
    # If TYPE-C16PIN is available, verify A6, A1B12 preserved
    tc = symbols.get("TYPE-C16PIN")
    if tc is None:
        return
    pins = pins_of_symbol(tc)
    nums = {p["number"] for p in pins}
    assert "A6" in nums, "A6 not found in TYPE-C16PIN pins"
    assert "A1B12" in nums, "A1B12 not found in TYPE-C16PIN pins"
    assert "B6" in nums, "B6 not found in TYPE-C16PIN pins"
