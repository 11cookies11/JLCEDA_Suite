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
from kicad_suite.pcb_generator import _convert_pad_block, _extract_pad_blocks, generate_pcb


class TestKicadProjectWriter(unittest.TestCase):
    def test_render_project_includes_default_erc_settings(self) -> None:
        project = json.loads(render_project())

        erc = project["erc"]
        self.assertEqual(erc["meta"]["version"], 0)
        self.assertEqual(len(erc["pin_map"]), 12)
        self.assertEqual(erc["rule_severities"]["unconnected_wire_endpoint"], "ignore")
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
        self.assertEqual(project["erc"]["rule_severities"]["unconnected_wire_endpoint"], "ignore")
        self.assertEqual(len(project["erc"]["pin_map"]), 12)

    def test_extract_pad_blocks_preserves_multiline_kicad_10_pads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fp_file = Path(tmpdir) / "demo.kicad_mod"
            fp_file.write_text(
                "\n".join(
                    [
                        '(footprint "demo"',
                        '  (pad "1" smd rect',
                        '    (at 0 0)',
                        '    (size 1 1)',
                        '    (layers "F.Cu" "F.Paste" "F.Mask")',
                        '  )',
                        ')',
                    ]
                ),
                encoding="utf-8",
            )

            blocks = _extract_pad_blocks(fp_file)
            converted = _convert_pad_block(blocks[0])

        self.assertEqual(len(blocks), 1)
        self.assertGreater(len(blocks[0]), 1)
        self.assertTrue(any("(uuid " in line for line in converted))
        self.assertTrue(any('(layers "F.Cu" "F.Paste" "F.Mask")' in line for line in converted))

    def test_generate_pcb_reports_missing_footprint_without_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            plan = {
                "target": {
                    "output_dir": str(output_dir),
                    "project_name": "demo",
                },
                "symbols": [
                    {
                        "ref": "U1",
                        "footprint": "LQFP-48",
                        "value": "MCU",
                        "at": {"x": 10.0, "y": 20.0, "rotation": 0.0},
                    }
                ],
                "nets": [],
            }

            result = generate_pcb(plan, project_path=tmpdir)

        self.assertTrue(result["ok"])
        self.assertEqual(result["component_count"], 1)
        self.assertEqual(result["placements"], [])
        self.assertTrue(any("U1: no footprint" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
