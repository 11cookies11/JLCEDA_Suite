"""Tests for adapter helper modules."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.kicad_cli import count_findings, load_schematic_from_plan, resolve_kicad_cli, resolve_schematic_file
from kicad_suite.adapters.jlc_mcp import extract_bridge_results, is_http_backend_reachable, resolve_bridge_script, run_bridge_search
from kicad_suite.adapters.kicad_erc_runner import run as run_erc


class TestKicadCliAdapter(unittest.TestCase):
    def test_resolve_kicad_cli_prefers_env(self):
        with patch("kicad_suite.adapters.kicad_cli.env", side_effect=lambda name, default="": "/custom/kicad-cli.exe" if name == "KICAD_CLI_BIN" else default):
            self.assertEqual(resolve_kicad_cli(), "/custom/kicad-cli.exe")

    def test_load_schematic_from_plan_reads_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "plan.json"
            plan_path.write_text(json.dumps({"target": {"schematic_file": "demo.kicad_sch"}}), encoding="utf-8")
            with patch("kicad_suite.adapters.kicad_cli.env", side_effect=lambda name, default="": str(plan_path) if name == "KICAD_EXECUTION_PLAN_FILE" else default):
                self.assertEqual(load_schematic_from_plan(), "demo.kicad_sch")

    def test_resolve_schematic_file_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            schematic = Path(tmpdir) / "demo.kicad_sch"
            schematic.write_text("(kicad_sch)", encoding="utf-8")
            with patch("kicad_suite.adapters.kicad_cli.env", side_effect=lambda name, default="": str(schematic) if name == "KICAD_SCHEMATIC_FILE" else default):
                self.assertEqual(resolve_schematic_file(), schematic)

    def test_count_findings_counts_nested_violations(self):
        payload = {"sheets": [{"violations": [{"id": 1}, {"id": 2}]}, {"violations": []}], "warnings": [{"id": 3}]}
        self.assertEqual(count_findings(payload), 2)


class TestJlcMcpAdapter(unittest.TestCase):
    def test_resolve_bridge_script_defaults_to_repo_script(self):
        script = resolve_bridge_script()
        self.assertTrue(str(script).endswith("scripts\\jlc_mcp_bridge.mjs") or str(script).endswith("scripts/jlc_mcp_bridge.mjs"))

    def test_extract_bridge_results_filters_dicts(self):
        payload = {"result": {"results": [{"lcsc_id": "C1"}, "ignore", {"lcsc_id": "C2"}]}}
        self.assertEqual(extract_bridge_results(payload), [{"lcsc_id": "C1"}, {"lcsc_id": "C2"}])

    def test_run_bridge_search_returns_results(self):
        fake_proc = SimpleNamespace(returncode=0, stdout=json.dumps({"result": {"results": [{"lcsc_id": "C1"}]}}))
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "bridge.mjs"
            script.write_text("// stub", encoding="utf-8")
            with patch("kicad_suite.adapters.jlc_mcp.subprocess.run", return_value=fake_proc):
                results = run_bridge_search(query="R", bridge_script=script)
        self.assertEqual(results, [{"lcsc_id": "C1"}])

    def test_run_bridge_search_returns_empty_for_missing_script(self):
        self.assertEqual(run_bridge_search(query="R", bridge_script=Path("does-not-exist.mjs")), [])

    def test_run_bridge_search_returns_empty_on_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "bridge.mjs"
            script.write_text("// stub", encoding="utf-8")
            with patch("kicad_suite.adapters.jlc_mcp.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["node"], timeout=1.0)):
                self.assertEqual(run_bridge_search(query="R", bridge_script=script), [])

    def test_run_bridge_search_returns_empty_on_bad_json(self):
        fake_proc = SimpleNamespace(returncode=0, stdout="not-json")
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "bridge.mjs"
            script.write_text("// stub", encoding="utf-8")
            with patch("kicad_suite.adapters.jlc_mcp.subprocess.run", return_value=fake_proc):
                self.assertEqual(run_bridge_search(query="R", bridge_script=script), [])

    def test_run_bridge_search_returns_empty_on_nonzero_exit(self):
        fake_proc = SimpleNamespace(returncode=1, stdout=json.dumps({"result": {"results": [{"lcsc_id": "C1"}]}}))
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "bridge.mjs"
            script.write_text("// stub", encoding="utf-8")
            with patch("kicad_suite.adapters.jlc_mcp.subprocess.run", return_value=fake_proc):
                self.assertEqual(run_bridge_search(query="R", bridge_script=script), [])

    def test_is_http_backend_reachable_false_on_error(self):
        with patch("kicad_suite.adapters.jlc_mcp.urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertFalse(is_http_backend_reachable("http://localhost:3847"))


class TestErcRunnerStructuredFailure(unittest.TestCase):
    def test_erc_runner_reports_missing_cli_structurally(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            schematic = Path(tmpdir) / "demo.kicad_sch"
            schematic.write_text("(kicad_sch)", encoding="utf-8")
            with patch("kicad_suite.adapters.kicad_erc_runner.resolve_schematic_file", return_value=schematic):
                with patch("kicad_suite.adapters.kicad_erc_runner.resolve_kicad_cli", return_value=""):
                    summary = run_erc(emit=False)
        self.assertFalse(summary["success"])
        self.assertEqual(summary["error"], "KICAD_CLI_NOT_FOUND")
        self.assertTrue(summary["warnings"])
