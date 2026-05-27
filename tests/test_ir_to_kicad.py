"""Tests for the IR → KiCad backend."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.ir_compiler import build_ir


def _make_model():
    return {
        "schema_version": "circuit-model.v1",
        "request_id": "test",
        "project_id": "test-board",
        "topology": "test",
        "components": [
            {"ref": "U1", "role": "mcu", "value": "H618",
             "selected_part": {"part_id": "h618", "mpn": "H618", "package": "BGA-484"}},
        ],
        "nets": [
            {"name": "+3V3", "members": ["U1.VDD"]},
            {"name": "GND", "members": ["U1.GND"]},
        ],
        "sheets": [], "risks": [], "calculations": [], "design_decisions": [], "constraints": [],
    }


def _kiCad_available():
    """ir_to_kicad requires a KiCad environment with symbol maps and libs."""
    try:
        from kicad_suite.compile_kicad_execution_plan import load_symbol_map
        load_symbol_map()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _kiCad_available(), reason="KiCad symbol map not configured")
def test_ir_to_kicad_produces_plan():
    from kicad_suite.ir_to_kicad import ir_to_kicad
    ir = build_ir(_make_model())
    plan = ir_to_kicad(ir)
    assert plan.schema_version == "kicad-execution-plan.v1"
    assert len(plan.symbols) == 1
    assert plan.symbols[0].ref == "U1"
    assert len(plan.nets) == 2


@pytest.mark.skipif(not _kiCad_available(), reason="KiCad symbol map not configured")
def test_ir_to_kicad_symbols_have_lib_id_and_footprint():
    from kicad_suite.ir_to_kicad import ir_to_kicad
    ir = build_ir(_make_model())
    plan = ir_to_kicad(ir)
    sym = plan.symbols[0]
    assert sym.lib_id, "KiCad symbol should have lib_id"
    assert sym.at is not None, "KiCad symbol should have position"


@pytest.mark.skipif(not _kiCad_available(), reason="KiCad symbol map not configured")
def test_ir_to_kicad_symbols_have_position():
    from kicad_suite.ir_to_kicad import ir_to_kicad
    ir = build_ir(_make_model())
    plan = ir_to_kicad(ir)
    assert plan.symbols[0].at.x != 0 or plan.symbols[0].at.y != 0


def test_ir_to_kicad_module_imports():
    """Verify the module can be imported without error."""
    from kicad_suite.ir_to_kicad import ir_to_kicad
    assert callable(ir_to_kicad)
