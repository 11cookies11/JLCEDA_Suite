"""Tests for the Symbol/Footprint Resolver."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.symbol_footprint_resolver import (
    load_symbol_map,
    resolve_footprint,
    symbol_mapping_for,
)


def test_load_symbol_map_returns_dict():
    sm = load_symbol_map()
    assert isinstance(sm, dict)
    assert "mappings" in sm
    assert isinstance(sm["mappings"], list)


def test_symbol_mapping_for_resistor():
    comp = {"ref": "R1", "role": "resistor", "value": "10k",
            "selected_part": {"package": "0603"}}
    lib_id, footprint, notes = symbol_mapping_for(comp)
    assert lib_id
    assert ":" in lib_id
    assert footprint or lib_id


def test_symbol_mapping_for_capacitor():
    comp = {"ref": "C1", "role": "capacitor", "value": "100nF",
            "selected_part": {"package": "0603"}}
    lib_id, footprint, notes = symbol_mapping_for(comp)
    assert lib_id
    assert ":" in lib_id


def test_symbol_mapping_for_unknown_role_returns_fallback():
    comp = {"ref": "X1", "role": "mystery_chip", "value": "???",
            "selected_part": {}}
    lib_id, footprint, notes = symbol_mapping_for(comp)
    assert lib_id
    assert ":" in lib_id


def test_resolve_footprint_uses_mapping_when_library_prefix():
    result = resolve_footprint("BGA-484", "Package_BGA:BGA-484_23x23mm_P1.0mm")
    assert result == "Package_BGA:BGA-484_23x23mm_P1.0mm"


def test_resolve_footprint_falls_back_to_package():
    result = resolve_footprint("JLC-MCP:C0603", "")
    assert result
    assert "0603" in result


def test_footprint_exists_checks_cache():
    from kicad_suite.symbol_footprint_resolver import (
        footprint_exists,
        clear_footprint_cache,
    )
    clear_footprint_cache()
    # A well-known KiCad resistor footprint should exist.
    exists = footprint_exists("Resistor_SMD:R_0603_1608Metric")
    assert exists is True or exists is None
