from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.kicad_project_writer import render_project
from kicad_suite.pipeline_postprocess import pin_project_libraries


class TestKicadProjectWriter(unittest.TestCase):
    def test_render_project_includes_default_erc_settings(self) -> None:
        project = json.loads(render_project())

        erc = project["erc"]
        self.assertEqual(erc["meta"]["version"], 0)
        self.assertEqual(len(erc["pin_map"]), 12)
        self.assertEqual(erc["rule_severities"]["unconnected_wire_endpoint"], "warning")
        self.assertEqual(erc["rule_severities"]["lib_symbol_issues"], "warning")
        self.assertEqual(erc["rule_severities"]["single_global_label"], "ignore")

    def test_pin_project_libraries_restores_default_erc_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            project_file = project_dir / "demo.kicad_pro"
            project_file.write_text(json.dumps({"libraries": {}}), encoding="utf-8")

            result = pin_project_libraries(project_dir)
            project = json.loads(project_file.read_text(encoding="utf-8"))

        self.assertTrue(result["success"])
        self.assertEqual(project["erc"]["rule_severities"]["unconnected_wire_endpoint"], "warning")
        self.assertEqual(len(project["erc"]["pin_map"]), 12)


if __name__ == "__main__":
    unittest.main()
