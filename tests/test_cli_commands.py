"""Tests for the unified CLI entrypoint."""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite import cli


class TestCliParser(unittest.TestCase):
    def test_parser_exposes_expected_subcommands(self):
        parser = cli.build_parser()
        subparsers = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
        self.assertIn("pipeline", subparsers)
        self.assertIn("validate-artifacts", subparsers)
        self.assertIn("erc", subparsers)
        self.assertIn("ngspice-doctor", subparsers)
        self.assertIn("simulation-plan", subparsers)

    def test_main_without_args_prints_help(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main([])
        self.assertEqual(code, 0)
        self.assertIn("Unified command-line entrypoint", buffer.getvalue())


class TestCliDispatch(unittest.TestCase):
    def test_pipeline_command_delegates_to_run_pipeline(self):
        with patch("kicad_suite.cli.run_pipeline", return_value={"ok": True}) as run_pipeline:
            code = cli.main(["pipeline", "model.json", "out"])
        self.assertEqual(code, 0)
        run_pipeline.assert_called_once_with("model.json", "out")

    def test_validate_artifacts_forwards_flags(self):
        with patch("kicad_suite.cli.validate_artifacts_main", return_value=0) as validate:
            code = cli.main(["validate-artifacts", "--summary", "summary.json", "--strict", "--require-erc", "--json"])
        self.assertEqual(code, 0)
        validate.assert_called_once()
        forwarded = validate.call_args.args[0]
        self.assertEqual(forwarded, ["--summary", "summary.json", "--strict", "--require-erc", "--json"])

    def test_ngspice_doctor_prints_environment_report(self):
        report = {"found": False, "recommendations": ["install ngspice"]}
        with patch("kicad_suite.cli.diagnose_ngspice_environment", return_value=report) as diagnose:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["ngspice-doctor"])
        self.assertEqual(code, 0)
        diagnose.assert_called_once()
        self.assertIn("install ngspice", buffer.getvalue())

    def test_simulation_plan_command_delegates(self):
        model = {"request_id": "r1", "project_id": "p1", "topology": "demo", "components": [], "nets": []}
        with patch("kicad_suite.cli.load_circuit_model", return_value=model) as load_model:
            with patch("kicad_suite.cli.build_simulation_plan", return_value={"schema_version": "simulation-plan.v1"}) as build_plan:
                with patch("kicad_suite.cli.simulation_plan_to_dict", return_value={"schema_version": "simulation-plan.v1"}) as to_dict:
                    buffer = io.StringIO()
                    with redirect_stdout(buffer):
                        code = cli.main(["simulation-plan", "model.json"])
        self.assertEqual(code, 0)
        load_model.assert_called_once()
        build_plan.assert_called_once()
        to_dict.assert_called_once()
