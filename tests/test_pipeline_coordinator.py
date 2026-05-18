"""Tests for the top-level pipeline coordinator."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.compile_kicad_execution_plan import (
    KiCadDiagnostics,
    KiCadExecutionPlan,
    KiCadNet,
    KiCadPoint,
    KiCadSymbol,
    KiCadTarget,
)
from kicad_suite.pipeline_coordinator import build_netlist, run_pipeline


class TestBuildNetlist(unittest.TestCase):
    def test_build_netlist_uses_model_fields(self):
        model = {
            "schema_version": "circuit-model.v1",
            "request_id": "req-1",
            "project_id": "proj-1",
            "topology": "demo",
            "components": [
                {
                    "ref": "U1",
                    "role": "ldo",
                    "value": "3.3V LDO",
                    "selected_part": {
                        "part_id": "P1",
                        "display_name": "AMS1117-3.3",
                        "package": "SOT-223",
                        "pin_count": 3,
                        "named_pin_count": 0,
                        "availability_status": "ready",
                    },
                    "availability_status": "ready",
                }
            ],
            "nets": [
                {"name": "GND", "members": ["U1-1"], "notes": ["ground"]},
            ],
        }

        netlist = build_netlist(model)
        self.assertEqual(netlist["schema_version"], "netlist.v1")
        self.assertEqual(netlist["components"][0]["ref"], "U1")
        self.assertEqual(netlist["components"][0]["part"]["part_id"], "P1")
        self.assertEqual(netlist["components"][0]["part"]["display_name"], "AMS1117-3.3")
        self.assertEqual(netlist["nets"][0]["name"], "GND")


class TestRunPipeline(unittest.TestCase):
    def test_run_pipeline_calls_parts_pipeline_when_enabled(self):
        model = {
            "request_id": "req-1",
            "project_id": "proj-1",
            "topology": "demo",
            "components": [],
            "nets": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model.json"
            model_path.write_text(json.dumps(model), encoding="utf-8")

            fake_plan = KiCadExecutionPlan(
                schema_version="kicad-execution-plan.v1",
                request_id="req-1",
                target=KiCadTarget(
                    project_name="proj-1",
                    output_dir=str(Path(tmpdir) / "proj-1"),
                    schematic_file=str(Path(tmpdir) / "proj-1" / "proj-1.kicad_sch"),
                    project_file=str(Path(tmpdir) / "proj-1" / "proj-1.kicad_pro"),
                ),
                symbols=[
                    KiCadSymbol(
                        ref="U1",
                        role="ldo",
                        value="3.3V LDO",
                        lib_id="AIAgent:Generic_2Pin",
                        footprint="",
                        at=KiCadPoint(x=0.0, y=0.0, rotation=0.0),
                        pins=[],
                    )
                ],
                nets=[
                    KiCadNet(name="GND", kind="ground", members=[]),
                ],
                diagnostics=KiCadDiagnostics(),
            )
            fake_write_result = {
                "schematic_file": str(Path(tmpdir) / "proj-1" / "proj-1.kicad_sch"),
                "project_file": str(Path(tmpdir) / "proj-1" / "proj-1.kicad_pro"),
                "summary_file": str(Path(tmpdir) / "proj-1" / "write-summary.json"),
                "symbol_count": 1,
                "net_count": 1,
            }

            with patch("kicad_suite.pipeline_coordinator.compile_plan", return_value=fake_plan) as compile_plan:
                with patch("kicad_suite.pipeline_coordinator.write_output", return_value="plan.json") as write_output:
                    with patch("kicad_suite.pipeline_coordinator.write_project", return_value=fake_write_result) as write_project:
                        with patch("kicad_suite.pipeline_coordinator.write_simulation_artifacts", return_value={"profile_file": "simulation-profile.json", "plan_file": "simulation-plan.json", "profile": {}, "plan": {}}) as write_simulation_artifacts:
                            with patch("kicad_suite.pipeline_coordinator.apply_postprocess", return_value={"symbols_injected": True}) as postprocess:
                                with patch("kicad_suite.pipeline_coordinator.run_erc", return_value={"enabled": False, "attempted": True, "success": True, "finding_count": 0, "summary_file": "", "output_file": ""}) as run_erc:
                                    with patch("kicad_suite.pipeline_coordinator.is_truthy_env", side_effect=lambda name, default="false": name == "KICAD_PARTS_PIPELINE"):
                                        with patch("kicad_suite.pipeline_coordinator.run_parts_pipeline", return_value={"lock_file": "part.lock.yaml", "risk_report_file": "part-risk-report.md"}) as run_parts:
                                            summary = run_pipeline(str(model_path), tmpdir)

        compile_plan.assert_called_once()
        write_output.assert_called_once()
        write_project.assert_called_once()
        write_simulation_artifacts.assert_called_once()
        postprocess.assert_called_once()
        run_erc.assert_called_once()
        run_parts.assert_called_once()
        self.assertEqual(summary["files"]["part_lock"], "part.lock.yaml")
        self.assertEqual(summary["files"]["simulation_profile"], "simulation-profile.json")
        self.assertTrue(summary["symbols_injected"])

    def test_run_pipeline_skips_parts_when_disabled(self):
        model = {
            "request_id": "req-1",
            "project_id": "proj-1",
            "topology": "demo",
            "components": [],
            "nets": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model.json"
            model_path.write_text(json.dumps(model), encoding="utf-8")

            fake_plan = KiCadExecutionPlan(
                schema_version="kicad-execution-plan.v1",
                request_id="req-1",
                target=KiCadTarget(
                    project_name="proj-1",
                    output_dir=str(Path(tmpdir) / "proj-1"),
                    schematic_file=str(Path(tmpdir) / "proj-1" / "proj-1.kicad_sch"),
                    project_file=str(Path(tmpdir) / "proj-1" / "proj-1.kicad_pro"),
                ),
                symbols=[],
                nets=[],
                diagnostics=KiCadDiagnostics(),
            )
            fake_write_result = {
                "schematic_file": str(Path(tmpdir) / "proj-1" / "proj-1.kicad_sch"),
                "project_file": str(Path(tmpdir) / "proj-1" / "proj-1.kicad_pro"),
                "summary_file": str(Path(tmpdir) / "proj-1" / "write-summary.json"),
                "symbol_count": 1,
                "net_count": 1,
            }

            with patch("kicad_suite.pipeline_coordinator.compile_plan", return_value=fake_plan):
                with patch("kicad_suite.pipeline_coordinator.write_output", return_value="plan.json"):
                    with patch("kicad_suite.pipeline_coordinator.write_project", return_value=fake_write_result):
                        with patch("kicad_suite.pipeline_coordinator.write_simulation_artifacts", return_value={"profile_file": "simulation-profile.json", "plan_file": "simulation-plan.json", "profile": {}, "plan": {}}) as write_simulation_artifacts:
                            with patch("kicad_suite.pipeline_coordinator.apply_postprocess", return_value={"symbols_injected": False}):
                                with patch("kicad_suite.pipeline_coordinator.run_erc", return_value={"enabled": False, "attempted": True, "success": True, "finding_count": 0, "summary_file": "", "output_file": ""}):
                                    with patch("kicad_suite.pipeline_coordinator.is_truthy_env", return_value=False):
                                        with patch("kicad_suite.pipeline_coordinator.run_parts_pipeline") as run_parts:
                                            summary = run_pipeline(str(model_path), tmpdir)

        run_parts.assert_not_called()
        write_simulation_artifacts.assert_called_once()
        self.assertEqual(summary["files"]["part_lock"], "")
        self.assertFalse(summary["symbols_injected"])
