"""Tests for the unified Report System."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.report_system import (
    FORMAT_JSON,
    FORMAT_MARKDOWN,
    FORMAT_TEXT,
    build_report,
    format_report,
)


def _make_project(tmp_path):
    model = {
        "schema_version": "circuit-model.v1",
        "request_id": "test",
        "project_id": "test-board",
        "topology": "test_topology",
        "components": [
            {"ref": "U1", "role": "mcu", "value": "H618",
             "selected_part": {"part_id": "h618", "mpn": "H618", "package": "BGA-484"}},
        ],
        "nets": [
            {"name": "+3V3", "members": ["U1.VDD"]},
            {"name": "GND", "members": ["U1.GND"]},
        ],
        "risks": [{"key": "ddr", "title": "DDR review", "status": "open", "severity": "high"}],
        "sheets": [], "calculations": [], "design_decisions": [], "constraints": [],
    }
    model_path = tmp_path / "circuit-model.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_build_report_produces_schema_version(tmp_path):
    path = _make_project(tmp_path)
    report = build_report(path)
    assert report["schema_version"] == "report.v1"
    assert "generated_at" in report
    assert report["overall_status"] in ("ok", "warning", "error", "info")


def test_build_report_has_all_sections(tmp_path):
    path = _make_project(tmp_path)
    report = build_report(path)
    keys = {s["key"] for s in report["sections"]}
    expected = {"project", "summary", "dsl", "build", "diagnostics", "ir", "risks", "history"}
    assert expected.issubset(keys), f"Missing sections: {expected - keys}"


def test_build_report_detects_open_risks(tmp_path):
    path = _make_project(tmp_path)
    report = build_report(path)
    risk_section = next(s for s in report["sections"] if s["key"] == "risks")
    assert risk_section["status"] == "warning"
    assert risk_section["data"]["open"] >= 1


def test_format_report_json(tmp_path):
    path = _make_project(tmp_path)
    report = build_report(path)
    out = format_report(report, FORMAT_JSON)
    assert out.startswith("{")
    parsed = json.loads(out)
    assert parsed["schema_version"] == "report.v1"


def test_format_report_text(tmp_path):
    path = _make_project(tmp_path)
    report = build_report(path)
    out = format_report(report, FORMAT_TEXT)
    assert "test_topology" in out or "test-board" in out
    assert "Report:" in out
    assert "-- " in out


def test_format_report_markdown(tmp_path):
    path = _make_project(tmp_path)
    report = build_report(path)
    out = format_report(report, FORMAT_MARKDOWN)
    assert "# Report:" in out
    assert "| Section | Status |" in out
    assert "## Risks" in out


def test_build_report_with_erc(tmp_path):
    path = _make_project(tmp_path)
    erc = {"attempted": True, "success": True, "finding_count": 0, "warnings": []}
    report = build_report(path, erc_result=erc)
    keys = {s["key"] for s in report["sections"]}
    assert "erc" in keys


def test_build_report_with_simulation(tmp_path):
    path = _make_project(tmp_path)
    sim = {"plan_file": "sim.json", "plan": {"summary": {"scenario_count": 3}}}
    report = build_report(path, simulation_result=sim)
    keys = {s["key"] for s in report["sections"]}
    assert "simulation" in keys
