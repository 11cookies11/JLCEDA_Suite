"""Tests for project state management."""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.project_state import (
    ProjectState,
    is_mutating_operation,
    is_validate_operation,
    is_build_operation,
)


def _write_model(project_dir, model=None):
    if model is None:
        model = {
            "schema_version": "circuit-model.v1",
            "request_id": "test",
            "project_id": "test-board",
            "topology": "test_topology",
            "components": [{"ref": "U1", "role": "mcu", "value": "H618"}],
            "nets": [{"name": "+3V3", "members": ["U1.VDD"]}],
            "risks": [{"key": "ddr", "title": "DDR review", "status": "open"}],
            "sheets": [],
            "calculations": [],
            "design_decisions": [],
            "constraints": [],
            "power_rails": [],
        }
    model_path = project_dir / "source" / "circuit-model.source.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    return model_path


def test_initial_status_is_init(tmp_path):
    ps = ProjectState(tmp_path)
    ps.load()
    assert ps.get_status() == "INIT"


def test_mark_dirty_changes_status(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_dirty("modified components")
    assert ps.get_status() == "DIRTY"
    assert ps.state_path.exists()


def test_mark_valid_after_dirty(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_dirty()
    ps.mark_valid()
    assert ps.get_status() == "VALID"
    assert ps.state["dsl"]["valid"] is True


def test_mark_invalid_records_errors(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_invalid({
        "errors": ["net +3V3 references missing component U1"],
        "warnings": ["risk ddr has no status"],
    })
    assert ps.get_status() == "INVALID"
    assert ps.state["dsl"]["valid"] is False
    assert ps.state["diagnostics"]["errors"] == 1
    assert ps.state["diagnostics"]["warnings"] == 1


def test_mark_built_records_hash(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_built({"kicad_project": "output/test.kicad_pro"})
    assert ps.get_status() == "BUILT"
    assert ps.state["build"]["last_build_ok"] is True
    assert len(ps.state["build"]["input_dsl_hash"]) == 8
    assert ps.state["build"]["outputs"]["kicad_project"] == "output/test.kicad_pro"


def test_mark_build_failed_records_diagnostics(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_build_failed({"errors": ["ERC failed: pin_not_connected x3"]})
    assert ps.get_status() == "BUILD_FAILED"
    assert ps.state["build"]["last_build_ok"] is False
    assert ps.state["diagnostics"]["errors"] == 1


def test_is_stale_after_model_change(tmp_path):
    model_path = _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_built()

    # Modify the model file
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["components"].append({"ref": "U2", "role": "pmic", "value": "AXP313A"})
    model_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")

    assert ps.is_stale() is True


def test_mark_built_then_stale(tmp_path):
    model_path = _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.mark_built()
    assert ps.get_status() == "BUILT"

    # Change model
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["nets"].append({"name": "+5V", "members": []})
    model_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")

    # After model change, staleness is detectable
    assert ps.is_stale() is True


def test_append_and_read_history(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.append_operation({"op": "add_component", "ref": "U1", "ok": True})
    ps.append_operation({"op": "connect_member", "net": "+3V3", "member": "U1.VDD", "ok": True})

    history = ps.get_history()
    assert len(history) == 2
    assert history[0]["op"] == "add_component"
    assert history[1]["op"] == "connect_member"
    assert "time" in history[0]


def test_recompute_from_files(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.recompute()
    assert ps.get_status() in ("DIRTY", "VALID", "INIT")
    assert len(ps.state["dsl"]["hash"]) == 8
    assert ps.state["dsl"]["path"] == "source/circuit-model.source.json"


def test_summary_counts(tmp_path):
    model = {
        "schema_version": "circuit-model.v1",
        "request_id": "test",
        "project_id": "test-board",
        "topology": "test_topology",
        "components": [{"ref": "U1", "role": "mcu", "value": "H618"}],
        "nets": [{"name": "+3V3", "members": ["U1.VDD"]}],
        "risks": [{"key": "ddr", "title": "DDR review", "status": "open"}],
        "sheets": [],
        "calculations": [],
        "design_decisions": [],
        "constraints": [],
        "power_rails": [{"name": "+3V3"}, {"name": "+1V8"}],
    }
    _write_model(tmp_path, model)
    ps = ProjectState(tmp_path)
    ps.load()
    ps.recompute()
    s = ps.get_summary()
    assert s["component_count"] == 1
    assert s["net_count"] == 1
    assert s["risk_count"] == 1
    assert s["power_rail_count"] == 2


def test_explain_returns_string(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    text = ps.get_explain()
    assert "test_topology" in text or "test-board" in text
    assert "Components:" in text
    assert "Nets:" in text
    assert "Risks:" in text


def test_state_file_persists_across_instances(tmp_path):
    _write_model(tmp_path)
    ps1 = ProjectState(tmp_path)
    ps1.load()
    ps1.mark_dirty("edit")

    ps2 = ProjectState(tmp_path)
    ps2.load()
    assert ps2.get_status() == "DIRTY"


def test_history_limit(tmp_path):
    _write_model(tmp_path)
    ps = ProjectState(tmp_path)
    ps.load()
    for i in range(10):
        ps.append_operation({"op": f"test_op_{i}", "ok": True})

    assert len(ps.get_history(limit=3)) == 3
    assert ps.get_history(limit=3)[-1]["op"] == "test_op_9"


def test_mutating_operation_classifier():
    assert is_mutating_operation("add_component") is True
    assert is_mutating_operation("update_net") is True
    assert is_mutating_operation("set_component_ref") is True
    assert is_mutating_operation("mark_risk_resolved") is True
    assert is_mutating_operation("get_component") is False
    assert is_mutating_operation("list_components") is False
    assert is_mutating_operation("validate_model") is False
    assert is_mutating_operation("compile_netlist") is False


def test_validate_operation_classifier():
    assert is_validate_operation("validate_model") is True
    assert is_validate_operation("validate_readiness") is True
    assert is_validate_operation("add_component") is False


def test_build_operation_classifier():
    assert is_build_operation("compile_netlist") is False
    assert is_build_operation("compile_kicad_execution_plan") is False
    assert is_build_operation("export_kicad_project") is True
    assert is_build_operation("validate_model") is False
