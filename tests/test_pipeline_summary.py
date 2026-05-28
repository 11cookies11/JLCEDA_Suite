"""Tests for pipeline summary building."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.pipeline_summary import build_run_pipeline_summary


class TestRunPipelineSummary(unittest.TestCase):
    def test_summary_collects_key_files_and_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            summary = build_run_pipeline_summary(
                project_name="demo",
                output_dir=output_dir,
                model_path="model.json",
                plan_file="plan.json",
                write_result={
                    "project_file": "project.kicad_pro",
                    "schematic_file": "project.kicad_sch",
                    "summary_file": "write-summary.json",
                    "symbol_count": 12,
                    "net_count": 9,
                },
                erc_result={
                    "schema_version": "kicad-erc.v1",
                    "enabled": True,
                    "attempted": True,
                    "success": True,
                    "return_code": 0,
                    "finding_count": 3,
                    "executable": "kicad-cli",
                    "summary_file": "erc-summary.json",
                    "output_file": "erc.json",
                    "error": "",
                    "warnings": ["erc ran with fallback"],
                },
                parts_result={
                    "lock_file": "part.lock.yaml",
                    "risk_report_file": "part-risk-report.md",
                },
                plan_diagnostics={"warnings": 1},
                project_resolution_result=None,
                postprocess={"symbols_injected": True},
                simulation_result={
                    "profile_file": "simulation-profile.json",
                    "plan_file": "simulation-plan.json",
                    "task_plan_file": "simulation-task-plan.json",
                    "event_log_file": "pipeline-events.jsonl",
                    "profile": {"schema_version": "simulation-profile.v1"},
                    "plan": {"schema_version": "simulation-plan.v1"},
                    "task_plan": {"schema_version": "simulation-task-plan.v1"},
                },
            )

            self.assertEqual(summary["project_name"], "demo")
            self.assertEqual(summary["files"]["project"], "project.kicad_pro")
            self.assertEqual(summary["files"]["part_lock"], "part.lock.yaml")
            self.assertEqual(summary["files"]["simulation_profile"], "simulation-profile.json")
            self.assertEqual(summary["files"]["simulation_plan"], "simulation-plan.json")
            self.assertEqual(summary["files"]["simulation_task_plan"], "simulation-task-plan.json")
            self.assertEqual(summary["files"]["event_log"], "pipeline-events.jsonl")
            self.assertEqual(summary["counts"]["symbols"], 12)
            self.assertEqual(summary["counts"]["nets"], 9)
            self.assertTrue(summary["symbols_injected"])
            self.assertEqual(summary["diagnostics"]["warnings"], 1)
            self.assertTrue(summary["erc"]["success"])
            self.assertTrue(summary["warnings"])
