"""Regression test for an ERC-success fixture that still has findings."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.application_services.artifact_validator import validate_artifacts


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "e2e" / "erc-findings"


class TestErcFindingsFixture(unittest.TestCase):
    def test_erc_success_with_findings_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURE_ROOT, root, dirs_exist_ok=True)

            report = validate_artifacts(root / "run-summary.json")

        self.assertTrue(report.ok)
        self.assertTrue(report.stats.get("erc_success"))
        self.assertEqual(report.stats.get("erc_finding_count"), 2)
        self.assertTrue(any("ERC: success with 2 finding(s)" in item for item in report.checks))


if __name__ == "__main__":
    unittest.main()
