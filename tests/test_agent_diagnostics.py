"""Tests for unified agent diagnostics."""

from __future__ import annotations

import json

from kicad_suite.application_services.agent_diagnostics import build_agent_diagnostics


def _write_model(project_dir, model):
    path = project_dir / "source" / "circuit-model.source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    return path


def test_agent_diagnostics_reports_valid_project(tmp_path) -> None:
    _write_model(tmp_path, {
        "schema_version": "circuit-model.v1",
        "request_id": "demo",
        "project_id": "diag-demo",
        "topology": "diag_board",
        "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
        "nets": [{"name": "VCC", "members": ["U1.1"]}],
        "sheets": [],
        "risks": [],
    })

    payload = build_agent_diagnostics(tmp_path)

    assert payload["schema_version"] == "agent-diagnostics.v1"
    assert payload["stage"] == "diagnose"
    assert payload["ok"] is True
    assert payload["counts"]["must_fix"] == 0


def test_agent_diagnostics_promotes_ir_errors_to_must_fix(tmp_path) -> None:
    _write_model(tmp_path, {
        "schema_version": "circuit-model.v1",
        "request_id": "demo",
        "project_id": "diag-demo",
        "topology": "diag_board",
        "components": [{"ref": "U1", "role": "mcu", "value": "MCU"}],
        "nets": [
            {"name": "VCC", "members": ["U1.1"]},
            {"name": "VCC", "members": ["U1.2"]},
        ],
        "sheets": [],
        "risks": [],
    })

    payload = build_agent_diagnostics(tmp_path)

    assert payload["ok"] is False
    assert payload["counts"]["must_fix"] >= 1
    assert any(item["source"] == "ir_validation" for item in payload["diagnostics"]["must_fix"])
