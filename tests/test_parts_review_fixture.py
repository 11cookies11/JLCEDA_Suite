"""Regression test for a parts workflow fixture that requires review."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.parts.workflow import run_parts_pipeline


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "e2e" / "parts-review"


class TestPartsReviewFixture(unittest.TestCase):
    def test_parts_review_fixture_produces_warning_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURE_ROOT, root, dirs_exist_ok=True)
            model = json.loads((root / "source" / "circuit-model.source.json").read_text(encoding="utf-8"))

            with patch("kicad_suite.parts.workflow.describe_live_backend_status", return_value={"ok": False}):
                result = run_parts_pipeline(model, root / "project", project_name="parts-review-demo")

        self.assertTrue(result["warnings"])
        self.assertIn("Using mock parts resolver results from the circuit model.", result["warnings"])
        self.assertEqual(result["summary"]["needs_review"], 1)
        self.assertTrue(result["lock_file"])
        self.assertTrue(result["risk_report_file"])


if __name__ == "__main__":
    unittest.main()
