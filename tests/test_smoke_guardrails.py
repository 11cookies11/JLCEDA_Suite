"""Small guardrail tests for the most important public paths.

These are intentionally lightweight. They are meant to catch accidental
breakage in the CLI, core model API, parts workflow, and the top-level
pipeline wiring before larger refactors remove code that still matters.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite import cli
from kicad_suite.domain.core.compile_kicad_execution_plan import KiCadDiagnostics, KiCadExecutionPlan, KiCadNet, KiCadTarget
from kicad_suite.model_api import ModelApiService
from kicad_suite.domain.core.parts.workflow import run_parts_pipeline
from kicad_suite.pipeline_coordinator import run_pipeline as run_pipeline_core
from kicad_suite.shared.schema_contracts import CANONICAL_FIELD_CONTRACT_SCHEMAS
from kicad_suite.shared.schema_versions import KICAD_EXECUTION_PLAN_SCHEMA_VERSION


def _minimal_model() -> dict[str, object]:
    return {
        "schema_version": "circuit-model.v1",
        "request_id": "smoke-req",
        "project_id": "smoke-project",
        "topology": "smoke_topology",
        "components": [],
        "nets": [],
    }


def _model_request(operation: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "dsl-api-request.v1",
        "request_id": f"smoke-{operation}",
        "project_id": "smoke-project",
        "topology": "smoke_topology",
        "operation": operation,
        "payload": payload,
    }


class TestCoreGuardrails(unittest.TestCase):
    def test_cli_parser_exposes_core_entrypoints(self) -> None:
        parser = cli.build_parser()
        subcommands = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]

        for name in ("pipeline", "model-api", "agent", "validate-artifacts", "erc", "ngspice-doctor"):
            self.assertIn(name, subcommands)

    def test_model_api_can_add_component(self) -> None:
        service = ModelApiService()
        result = service.handle_dict(
            _model_request(
                "add_component",
                {
                    "ref": "U1",
                    "role": "mcu",
                    "value": "RP2040",
                    "selected_part": {"part_id": "demo-part"},
                },
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(service.model["components"][0]["ref"], "U1")

    def test_parts_workflow_handles_empty_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_parts_pipeline({"components": []}, Path(tmp_dir))

        self.assertIn("warning", result)
        self.assertEqual(result["selections"], [])

    def test_pipeline_coordinator_smoke_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            model_path = tmp_path / "source" / "circuit-model.source.json"
            output_dir = tmp_path / "output"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(json.dumps(_minimal_model()), encoding="utf-8")

            fake_plan = KiCadExecutionPlan(
                schema_version=KICAD_EXECUTION_PLAN_SCHEMA_VERSION,
                request_id="smoke-req",
                target=KiCadTarget(
                    project_name="smoke_topology",
                    output_dir=str(output_dir / "smoke_topology"),
                    schematic_file=str(output_dir / "smoke_topology" / "smoke_topology.kicad_sch"),
                    project_file=str(output_dir / "smoke_topology" / "smoke_topology.kicad_pro"),
                ),
                symbols=[],
                nets=[KiCadNet(name="GND", kind="ground", members=[])],
                diagnostics=KiCadDiagnostics(),
            )

            fake_write_result = {
                "project_file": str(output_dir / "smoke_topology" / "smoke_topology.kicad_pro"),
                "schematic_file": str(output_dir / "smoke_topology" / "smoke_topology.kicad_sch"),
                "summary_file": str(output_dir / "smoke_topology" / "write-summary.json"),
                "symbol_count": 0,
                "net_count": 0,
            }

            fake_summary = {
                "files": {"summary": str(output_dir / "smoke_topology" / "pipeline-summary.json")},
                "counts": {"components": 0, "nets": 0},
            }

            with patch("kicad_suite.pipeline_coordinator.is_truthy_env", return_value=False):
                with patch("kicad_suite.pipeline_coordinator.write_simulation_artifacts", return_value={"profile_file": "", "plan_file": "", "task_plan_file": "", "profile": {}, "plan": {}, "task_plan": {}}):
                    with patch("kicad_suite.pipeline_coordinator.build_ir", return_value={"components": [], "nets": []}) as build_ir:
                        with patch("kicad_suite.pipeline_coordinator.ir_to_kicad", return_value=fake_plan) as ir_to_kicad:
                            with patch("kicad_suite.pipeline_coordinator.write_output", return_value=str(output_dir / "smoke_topology" / "kicad-plan.json")) as write_output:
                                with patch("kicad_suite.pipeline_coordinator.write_project", return_value=fake_write_result) as write_project:
                                    with patch("kicad_suite.pipeline_coordinator.write_hierarchical_project", return_value=fake_write_result) as write_hierarchical_project:
                                        with patch("kicad_suite.pipeline_coordinator.generate_board_from_plan", return_value={"attempted": False, "enabled": False}) as generate_board:
                                            with patch("kicad_suite.pipeline_coordinator.apply_postprocess", return_value={"symbols_injected": False}) as postprocess:
                                                with patch("kicad_suite.pipeline_coordinator.run_erc", return_value={"enabled": False, "attempted": True, "success": True, "finding_count": 0, "summary_file": "", "output_file": ""}) as run_erc:
                                                    with patch("kicad_suite.pipeline_coordinator.pin_project_libraries", return_value={"symbol_pins": 0}) as pin_project_libraries:
                                                        with patch("kicad_suite.pipeline_coordinator.write_project_resolution", return_value={"path": str(output_dir / "smoke_topology" / "build" / "project-resolution.json"), "manifest": {"summary": {"component_count": 0, "verified_count": 0, "needs_reselection_count": 0}}}) as write_project_resolution:
                                                            with patch("kicad_suite.pipeline_coordinator.build_run_pipeline_summary", return_value=fake_summary) as build_summary:
                                                                summary = run_pipeline_core(str(model_path), str(output_dir))

        self.assertEqual(summary["files"]["summary"], fake_summary["files"]["summary"])
        build_ir.assert_called_once()
        ir_to_kicad.assert_called_once()
        write_output.assert_called_once()
        write_project.assert_called()
        write_hierarchical_project.assert_called()
        generate_board.assert_called_once()
        postprocess.assert_called_once()
        run_erc.assert_called_once()
        pin_project_libraries.assert_called_once()
        write_project_resolution.assert_called_once()
        build_summary.assert_called_once()

    def test_schema_contracts_cover_core_execution_plan_schema(self) -> None:
        self.assertIn(KICAD_EXECUTION_PLAN_SCHEMA_VERSION, CANONICAL_FIELD_CONTRACT_SCHEMAS)


if __name__ == "__main__":
    unittest.main()
