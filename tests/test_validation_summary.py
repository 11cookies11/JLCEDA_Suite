"""Tests for artifact validation summary handling."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.shared.validation.common import ValidationReport
from kicad_suite.domain.core.validation.summary import validate_summary


class TestValidateSummary(unittest.TestCase):
    def test_validate_summary_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = Path(tmpdir) / "summary.json"
            summary_path.write_text(
                """
{
  "files": {
    "project": "missing.kicad_pro",
    "schematic": "missing.kicad_sch",
    "execution_plan": "missing-plan.json"
  }
}
""".strip(),
                encoding="utf-8",
            )
            report = ValidationReport()
            validate_summary(report, {"files": {"project": "missing.kicad_pro", "schematic": "missing.kicad_sch", "execution_plan": "missing-plan.json"}}, summary_path)
            self.assertFalse(report.ok)
            self.assertTrue(any("missing file" in err for err in report.errors))

    def test_validate_summary_accepts_existing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "demo.kicad_pro"
            schematic = root / "demo.kicad_sch"
            plan = root / "plan.json"
            project.write_text("{}", encoding="utf-8")
            schematic.write_text("{}", encoding="utf-8")
            plan.write_text("{}", encoding="utf-8")
            summary_path = root / "summary.json"
            summary_path.write_text("{}", encoding="utf-8")

            report = ValidationReport()
            summary = {
                "files": {"project": str(project), "schematic": str(schematic), "execution_plan": str(plan)},
                "warnings": ["mock warning"],
            }
            validate_summary(report, summary, summary_path)

            self.assertTrue(report.ok)
            self.assertIn("mock warning", report.warnings)
            self.assertTrue(any("stale paths" in item for item in report.checks))

    def test_validate_summary_accepts_hierarchical_sheet_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "demo.kicad_pro"
            schematic = root / "demo.kicad_sch"
            plan = root / "plan.json"
            project.write_text("{}", encoding="utf-8")
            schematic.write_text("{}", encoding="utf-8")
            plan.write_text("{}", encoding="utf-8")
            summary_path = root / "summary.json"
            summary_path.write_text("{}", encoding="utf-8")

            report = ValidationReport()
            summary = {
                "hierarchical_sheets": {
                    "root_schematic_file": str(schematic),
                    "sheet_files": [str(schematic)],
                },
                "execution_plan": str(plan),
            }
            validate_summary(report, summary, summary_path)

            self.assertTrue(report.ok)
            self.assertTrue(any("stale paths" in item for item in report.checks))
