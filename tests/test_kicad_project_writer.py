from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kicad_suite.adapters.kicad_project_writer import render_project
from kicad_suite.orchestration.pipeline_postprocess import pin_project_libraries
from kicad_suite.adapters.board_generator import (
    _load_source_model,
    _source_netlist_symbol_pins,
    generate_board_from_plan,
)
from kicad_suite.adapters.kicad_symbol_library import parse_symbol_pin_map
from kicad_suite.domain.core.netlist_builder import build_netlist
from kicad_suite.adapters.pcb_generator import _BOARD_SCRIPT, _convert_pad_block, _extract_pad_blocks, generate_pcb


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

            with patch("kicad_suite.adapters.pcb_generator._kicad_python", return_value="fake-kicad-python"):
                with patch("kicad_suite.adapters.pcb_generator.subprocess.run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = json.dumps(
                        {
                            "board": str(output_dir / "demo.kicad_pcb"),
                            "footprints": 0,
                            "nets": 0,
                            "skipped": ["U1: no footprint"],
                        }
                    )
                    run.return_value.stderr = ""

                    result = generate_pcb(plan, project_path=tmpdir)

        self.assertTrue(result["ok"])
        self.assertEqual(result["component_count"], 1)
        self.assertEqual(result["placements"], [])
        self.assertTrue(any("U1: no footprint" in warning for warning in result["warnings"]))

    def test_generate_board_rejects_missing_pad_nets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "output" / "demo"
            project_dir.mkdir(parents=True, exist_ok=True)
            board_file = project_dir / "demo.kicad_pcb"
            plan_file = Path(tmpdir) / "plan.json"
            plan = {
                "target": {
                    "output_dir": str(project_dir),
                    "project_name": "demo",
                },
                "symbols": [
                    {
                        "ref": "U1",
                        "footprint": "JLC-MCP:QFN-56_L7.0-W7.0-P0.40-TL-EP4.0",
                        "value": "ESP32-S3",
                        "pins": [
                            {"number": "17", "net": "I2S_BCLK"},
                            {"number": "49", "net": "UART0_TX"},
                        ],
                    }
                ],
            }
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            board_file.write_text(
                """
(kicad_pcb
  (version 20260206)
  (generator "pcbnew")
  (footprint "JLC-MCP:QFN-56_L7.0-W7.0-P0.40-TL-EP4.0"
    (layer "F.Cu")
    (property "Reference" "U1" (at 0 0 0))
    (pad "17" smd rect
      (at 0 0)
      (size 1 1)
      (layers "F.Cu")
    )
    (pad "49" smd rect
      (at 1 0)
      (size 1 1)
      (layers "F.Cu")
      (net "UART0_TX")
    )
  )
)
""".strip(),
                encoding="utf-8",
            )

            def _run_side_effect(*args, **kwargs):
                class _Proc:
                    returncode = 0
                    stdout = json.dumps({"board": str(board_file), "footprints": 1, "nets": 1, "skipped": []})
                    stderr = ""

                return _Proc()

            with patch("kicad_suite.adapters.board_generator._resolve_kicad_python", return_value="fake-kicad-python"):
                with patch("kicad_suite.adapters.board_generator.subprocess.run", side_effect=_run_side_effect):
                    result = generate_board_from_plan(str(plan_file), project_dir, tmpdir)

        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertTrue(any("U1 pad 17" in warning for warning in result["warnings"]))
        self.assertTrue(result["verification_errors"])

    def test_source_netlist_symbol_pins_resolve_semantic_and_numeric_pins(self) -> None:
        project_dir = Path("examples/ai-memory-badge-v1")
        source_model = _load_source_model(project_dir)
        source_netlist = build_netlist(source_model)

        u5_lib_id = "JLC-MCP:APS6404L-3SQR-SN_C5333729"
        u6_lib_id = "JLC-MCP:USBLC6-2SC6"
        with patch.dict(
            os.environ,
            {
                "KICAD_SOURCE_PROJECT_DIR": str(project_dir),
                "KICAD_OUTPUT_DIR": str(project_dir / "output" / "ai_memory_badge_v1"),
            },
            clear=False,
        ):
            u5_pins = _source_netlist_symbol_pins(
                source_netlist,
                "U5",
                u5_lib_id,
                parse_symbol_pin_map(u5_lib_id),
            )
            u6_pins = _source_netlist_symbol_pins(
                source_netlist,
                "U6",
                u6_lib_id,
                parse_symbol_pin_map(u6_lib_id),
            )

        self.assertEqual([pin["number"] for pin in u5_pins], ["1", "4", "8"])
        self.assertEqual([pin["number"] for pin in u6_pins], ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(u5_pins[0]["net"], "PSRAM_CS")
        self.assertEqual(u6_pins[1]["net"], "GND")

    def test_board_script_does_not_depend_on_repo_src_imports(self) -> None:
        self.assertNotIn("src.kicad_suite", _BOARD_SCRIPT)
        self.assertNotIn("from src ", _BOARD_SCRIPT)
        self.assertNotIn("from src.", _BOARD_SCRIPT)


if __name__ == "__main__":
    unittest.main()
