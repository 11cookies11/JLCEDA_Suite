"""Regression tests that exercise representative end-to-end fixtures."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.application_services.artifact_validator import validate_artifacts
from kicad_suite.shared.validation.common import load_json


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "e2e" / "complete-run"


def _copy_fixture_tree(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        target = destination / path.relative_to(source)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


class TestEndToEndFixture(unittest.TestCase):
    def test_complete_pipeline_fixture_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture_tree(FIXTURE_ROOT, root)

            summary_path = root / "run-summary.json"
            report = validate_artifacts(summary_path)
            summary = load_json(summary_path)

            self.assertTrue(report.ok)
            self.assertEqual(report.stats.get("summary_schema"), "kicad-project-write-result.v1")
            self.assertTrue(report.stats.get("erc_success"))
            self.assertEqual(report.stats.get("shared_node_labels"), 0)
            self.assertTrue(any("stale paths: none found" in item for item in report.checks))
            self.assertEqual(summary["counts"]["symbols"], 3)
            self.assertEqual(summary["counts"]["nets"], 4)
            self.assertEqual(len(summary["warnings"]), 0)

            part_lock = root / "project" / "part.lock.yaml"
            risk_report = root / "project" / "part-risk-report.md"
            self.assertIn("schema_version: part-lock.v1", part_lock.read_text(encoding="utf-8"))
            self.assertIn("# Part Risk Report", risk_report.read_text(encoding="utf-8"))

    def test_complete_pipeline_fixture_with_warnings_fails_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_fixture_tree(FIXTURE_ROOT, root)

            summary_path = root / "run-summary.json"
            summary = load_json(summary_path)
            warning_summary = copy.deepcopy(summary)
            warning_summary["warnings"] = [
                "Using mock parts resolver results from the circuit model.",
                "ERC: disabled or unavailable",
            ]
            warning_summary["erc"] = copy.deepcopy(summary["erc"])
            warning_summary["erc"]["enabled"] = False
            warning_summary["erc"]["attempted"] = False
            warning_summary["erc"]["success"] = False
            warning_summary["erc"]["error"] = "KICAD_CLI_NOT_FOUND"
            warning_summary["postprocess"] = copy.deepcopy(summary["postprocess"])
            warning_summary["postprocess"]["library_registration"] = {
                "attempted": True,
                "success": False,
                "stderr": "bridge unavailable",
            }
            summary_path.write_text(json.dumps(warning_summary, indent=2), encoding="utf-8")

            report = validate_artifacts(summary_path, strict=True)

            self.assertFalse(report.ok)
            self.assertTrue(any("strict mode" in item for item in report.errors))
            self.assertTrue(any("mock parts resolver" in item for item in report.warnings))
            self.assertTrue(any("ERC: disabled or unavailable" in item for item in report.warnings))

if __name__ == "__main__":
    unittest.main()
