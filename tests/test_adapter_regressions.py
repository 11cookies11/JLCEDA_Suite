"""Regression tests for representative adapter failure fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.jlc_mcp import run_bridge_search
from kicad_suite.adapters.kicad_erc_runner import run as run_erc


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "adapters"


class TestAdapterFailureFixtures(unittest.TestCase):
    def test_erc_missing_cli_fixture(self) -> None:
        fixture = json.loads((FIXTURE_DIR / "erc-missing-cli.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schematic = root / fixture["schematic_file"]
            schematic.write_text("(kicad_sch)", encoding="utf-8")
            with patch("kicad_suite.adapters.kicad_erc_runner.resolve_schematic_file", return_value=schematic):
                with patch("kicad_suite.adapters.kicad_erc_runner.resolve_kicad_cli", return_value=""):
                    summary = run_erc(emit=False)

        expected = fixture["expected"]
        self.assertEqual(summary["enabled"], expected["enabled"])
        self.assertEqual(summary["attempted"], expected["attempted"])
        self.assertEqual(summary["success"], expected["success"])
        self.assertEqual(summary["error"], expected["error"])
        self.assertTrue(any(expected["warning_contains"] in warning for warning in summary["warnings"]))

    def test_jlc_bridge_timeout_fixture(self) -> None:
        fixture = json.loads((FIXTURE_DIR / "jlc-bridge-timeout.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "bridge.mjs"
            script.write_text("// stub", encoding="utf-8")
            with patch("kicad_suite.adapters.jlc_mcp.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["node"], timeout=fixture["timeout_sec"])):
                results = run_bridge_search(
                    query=fixture["query"],
                    limit=fixture["limit"],
                    source=fixture["source"],
                    bridge_script=script,
                    timeout=fixture["timeout_sec"],
                )

        self.assertEqual(len(results), fixture["expected_result_count"])


if __name__ == "__main__":
    unittest.main()
