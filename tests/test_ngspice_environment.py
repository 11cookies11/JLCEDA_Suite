"""Tests for ngspice environment discovery and diagnostics."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.orchestration.circuit_pipeline import diagnose_ngspice_environment, resolve_ngspice_executable


class TestNgspiceEnvironment(unittest.TestCase):
    def test_resolve_ngspice_uses_explicit_bin(self):
        with patch.dict(os.environ, {"NGSPICE_BIN": r"C:\\tools\\ngspice\\ngspice.exe"}, clear=False):
            with patch("kicad_suite.orchestration.circuit_pipeline.shutil.which", return_value=None):
                with patch("pathlib.Path.exists", return_value=False):
                    resolved = resolve_ngspice_executable()
        self.assertEqual(resolved, r"C:\\tools\\ngspice\\ngspice.exe")

    def test_doctor_reports_missing_ngspice(self):
        with patch.dict(os.environ, {"NGSPICE_BIN": "", "NGSPICE_ENABLED": "true"}, clear=False):
            with patch("kicad_suite.orchestration.circuit_pipeline.shutil.which", return_value=None):
                with patch("pathlib.Path.exists", return_value=False):
                    report = diagnose_ngspice_environment()
        self.assertFalse(report["found"])
        self.assertIn("Install ngspice", " ".join(report["recommendations"]))

    def test_resolve_ngspice_prefers_repo_bundle(self):
        repo_bundle = Path(__file__).resolve().parents[1] / "tools" / "ngspice-46_64" / "Spice64" / "bin" / "ngspice.exe"
        self.assertTrue(repo_bundle.exists(), f"Missing bundled ngspice at {repo_bundle}")
        with patch.dict(os.environ, {"NGSPICE_BIN": ""}, clear=False):
            with patch("kicad_suite.orchestration.circuit_pipeline.shutil.which", return_value=None):
                resolved = resolve_ngspice_executable()
        self.assertEqual(Path(resolved), repo_bundle)
